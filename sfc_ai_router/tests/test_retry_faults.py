"""Offline transport faults through the existing adapter and retry policy."""
import json

import httpx
import pytest

from sfc_ai_router.adapters import openrouter
from sfc_ai_router.retry import with_backoff
from sfc_ai_router.types import RouterRequest


class FaultClient:
    def __init__(self, sequence):
        self.sequence = sequence
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        value = self.sequence[min(self.calls, len(self.sequence) - 1)]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        text = json.dumps({"model": "anthropic/claude-fixture", "choices": [
            {"message": {"content": "Synthetic response"}}]}) if value == 200 else "Synthetic fault"
        return type("Response", (), {"status_code": value, "text": text})()


@pytest.fixture
def no_delay(monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    async def policy(fn):
        return await with_backoff(fn, max_attempts=3, _sleep=sleep)

    monkeypatch.setattr(openrouter, "with_backoff", policy)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-placeholder")
    return delays


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [429, 503, httpx.ReadTimeout("Synthetic timeout")])
async def test_retryable_fault_exhausts_at_three_attempts(fault, no_delay):
    client = FaultClient([fault])
    adapter = openrouter.OpenRouterAdapter(http_client=client)
    result = await adapter.run(RouterRequest(lane="claude", task_type="general", user_prompt="test"),
                               "anthropic/claude-fixture", "offline-fault")
    assert result.ok is False
    assert result.text == ""
    assert result.error.retryable is True
    assert client.calls == 3
    assert len(no_delay) == 2


@pytest.mark.asyncio
async def test_recovery_after_rate_limit_stops_retrying(no_delay):
    client = FaultClient([429, 200])
    adapter = openrouter.OpenRouterAdapter(http_client=client)
    result = await adapter.run(RouterRequest(lane="claude", task_type="general", user_prompt="test"),
                               "anthropic/claude-fixture", "offline-recovery")
    assert result.ok is True
    assert result.text == "Synthetic response"
    assert client.calls == 2
    assert len(no_delay) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 402, 403])
async def test_auth_or_billing_failures_are_not_retried(status, no_delay):
    client = FaultClient([status])
    adapter = openrouter.OpenRouterAdapter(http_client=client)
    result = await adapter.run(RouterRequest(lane="claude", task_type="general", user_prompt="test"),
                               "anthropic/claude-fixture", "offline-auth")
    assert result.ok is False
    assert result.error.retryable is False
    assert client.calls == 1
    assert no_delay == []
