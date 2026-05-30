"""SageForge AI Router — Python test suite.

Runs fully offline: httpx calls are mocked at the adapter level.
No real API keys, no network.

    pytest tests/test_router.py -v
"""
from __future__ import annotations
import json
import os
import pytest
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sfc_ai_router import (
    AiRouter, RouterRequest, RouterResult,
    OpenRouterAdapter, OpenAiDirectAdapter, AnthropicDirectAdapter,
    scan_customer_facing,
)
from sfc_ai_router.health import ProviderHealth
from sfc_ai_router.types import RouterError


# ── helpers ──────────────────────────────────────────────────────────────

def _or_ok_response():
    """Mock httpx response: OpenRouter success."""
    m = MagicMock()
    m.status_code = 200
    m.text = json.dumps({
        "model": "anthropic/claude-sonnet-4.6",
        "choices": [{"message": {"content": "hello from claude"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })
    return m


def _openai_ok_response():
    m = MagicMock()
    m.status_code = 200
    m.text = json.dumps({
        "model": "gpt-4.1",
        "choices": [{"message": {"content": "hello from gpt"}}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
    })
    return m


def _error_response(status: int, msg: str = "error"):
    m = MagicMock()
    m.status_code = status
    m.text = json.dumps({"error": {"message": msg}})
    return m


def _captured_audit():
    records = []
    def writer(record):
        records.append(record)
    return records, writer


def _clean_env():
    for k in ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
              "AI_GATEWAY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY",
              "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE",
              "ENABLE_ANTHROPIC_DIRECT", "AI_ROUTER_REQUIRE_ZDR",
              "AI_ROUTER_PROVIDER_ORDER"]:
        os.environ.pop(k, None)


# ── Test 2: OpenRouter adapter returns normalized success ─────────────────

@pytest.mark.asyncio
async def test_openrouter_adapter_success():
    _clean_env()
    os.environ["OPENROUTER_API_KEY"] = "sk-test"
    records, writer = _captured_audit()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_or_ok_response())

    adapter = OpenRouterAdapter(http_client=mock_client)
    req = RouterRequest(lane="claude", task_type="general", user_prompt="hi")
    result = await adapter.run(req, "anthropic/claude-sonnet-4.6", "req_test")

    assert result.ok is True
    assert result.provider == "openrouter"
    assert result.text == "hello from claude"
    assert result.usage is not None
    assert result.usage.total_tokens == 15


# ── Test 3: router skips unconfigured providers ───────────────────────────

@pytest.mark.asyncio
async def test_router_skips_unconfigured():
    _clean_env()
    records, writer = _captured_audit()
    router = AiRouter(
        adapters=[OpenRouterAdapter()],
        health=ProviderHealth(),
        audit_writer=writer,
    )
    result = await router.run(RouterRequest(lane="claude", task_type="general", user_prompt="hi"))
    assert result.ok is False
    assert result.provider == "none"
    assert result.fallbacks_attempted == []  # never attempted; key missing


# ── Test 4+5: fallback past a failing provider, path recorded ─────────────

@pytest.mark.asyncio
async def test_router_falls_back_and_records_path():
    _clean_env()
    os.environ["ANTHROPIC_API_KEY"] = "sk-anthropic"
    os.environ["OPENROUTER_API_KEY"] = "sk-openrouter"
    os.environ["ENABLE_ANTHROPIC_DIRECT"] = "true"
    os.environ["AI_ROUTER_PROVIDER_ORDER"] = "anthropic_direct,openrouter"

    records, writer = _captured_audit()

    auth_fail = MagicMock()
    auth_fail.status_code = 402
    auth_fail.text = json.dumps({"error": {"message": "billing: prepaid blocked"}})

    mock_anthropic = AsyncMock()
    mock_anthropic.__aenter__ = AsyncMock(return_value=mock_anthropic)
    mock_anthropic.__aexit__ = AsyncMock(return_value=False)
    mock_anthropic.post = AsyncMock(return_value=auth_fail)

    mock_or = AsyncMock()
    mock_or.__aenter__ = AsyncMock(return_value=mock_or)
    mock_or.__aexit__ = AsyncMock(return_value=False)
    mock_or.post = AsyncMock(return_value=_or_ok_response())

    router = AiRouter(
        adapters=[
            AnthropicDirectAdapter(http_client=mock_anthropic),
            OpenRouterAdapter(http_client=mock_or),
        ],
        health=ProviderHealth(),
        audit_writer=writer,
    )
    result = await router.run(RouterRequest(lane="claude", task_type="general", user_prompt="hi"))
    assert result.ok is True
    assert result.provider == "openrouter"
    assert "anthropic_direct" in result.fallbacks_attempted
    assert "openrouter" in result.fallbacks_attempted

    os.environ.pop("ENABLE_ANTHROPIC_DIRECT", None)
    os.environ.pop("AI_ROUTER_PROVIDER_ORDER", None)


# ── Test 6: two-lane separation — Claude never silently uses ChatGPT ──────

@pytest.mark.asyncio
async def test_claude_lane_never_silently_uses_chatgpt():
    _clean_env()
    os.environ["OPENAI_API_KEY"] = "sk-openai"
    records, writer = _captured_audit()
    mock_oa = AsyncMock()
    mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
    mock_oa.__aexit__ = AsyncMock(return_value=False)
    mock_oa.post = AsyncMock(return_value=_openai_ok_response())

    router = AiRouter(
        adapters=[OpenRouterAdapter(), OpenAiDirectAdapter(http_client=mock_oa)],
        health=ProviderHealth(),
        audit_writer=writer,
    )
    result = await router.run(RouterRequest(lane="claude", task_type="general", user_prompt="hi"))
    assert result.ok is False
    assert result.provider != "openai_direct"


# ── Test 6b: cross-lane fallback works only when policy allows ────────────

@pytest.mark.asyncio
async def test_cross_lane_fallback_when_allowed():
    _clean_env()
    os.environ["OPENAI_API_KEY"] = "sk-openai"
    mock_oa = AsyncMock()
    mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
    mock_oa.__aexit__ = AsyncMock(return_value=False)
    mock_oa.post = AsyncMock(return_value=_openai_ok_response())

    router = AiRouter(
        adapters=[OpenRouterAdapter(), OpenAiDirectAdapter(http_client=mock_oa)],
        health=ProviderHealth(),
        audit_writer=lambda r: None,
    )
    result = await router.run(RouterRequest(
        lane="claude", task_type="general", user_prompt="hi",
        fallback_policy="cross_lane_allowed"
    ))
    assert result.ok is True
    assert result.provider == "openai_direct"


# ── Test 7: normalized output shape across providers ─────────────────────

@pytest.mark.asyncio
async def test_normalized_output_shape():
    _clean_env()
    os.environ["OPENROUTER_API_KEY"] = "k"
    os.environ["OPENAI_API_KEY"] = "k"

    required_fields = ["ok", "provider", "model", "text", "latency_ms", "request_id"]

    mock_or = AsyncMock()
    mock_or.__aenter__ = AsyncMock(return_value=mock_or)
    mock_or.__aexit__ = AsyncMock(return_value=False)
    mock_or.post = AsyncMock(return_value=_or_ok_response())

    mock_oa = AsyncMock()
    mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
    mock_oa.__aexit__ = AsyncMock(return_value=False)
    mock_oa.post = AsyncMock(return_value=_openai_ok_response())

    req = RouterRequest(lane="claude", task_type="general", user_prompt="x")
    or_result = await OpenRouterAdapter(http_client=mock_or).run(req, "m", "r1")
    oa_result = await OpenAiDirectAdapter(http_client=mock_oa).run(req, "m", "r2")

    for f in required_fields:
        assert hasattr(or_result, f), f"openrouter missing {f}"
        assert hasattr(oa_result, f), f"openai missing {f}"


# ── Test 8: audit record contains no API keys ─────────────────────────────

@pytest.mark.asyncio
async def test_audit_no_secrets():
    _clean_env()
    os.environ["OPENROUTER_API_KEY"] = "sk-supersecret-router-key-12345"
    records, writer = _captured_audit()

    mock_or = AsyncMock()
    mock_or.__aenter__ = AsyncMock(return_value=mock_or)
    mock_or.__aexit__ = AsyncMock(return_value=False)
    mock_or.post = AsyncMock(return_value=_or_ok_response())

    router = AiRouter(
        adapters=[OpenRouterAdapter(http_client=mock_or)],
        health=ProviderHealth(),
        audit_writer=writer,
    )
    await router.run(RouterRequest(lane="claude", task_type="general", user_prompt="hi"))

    blob = json.dumps([asdict(r) for r in records])
    assert "sk-supersecret" not in blob, "Secret leaked into audit log"


# ── Test 9: fails safely when no providers configured ─────────────────────

@pytest.mark.asyncio
async def test_fails_safely_no_providers():
    _clean_env()
    router = AiRouter(
        adapters=[OpenRouterAdapter()],
        health=ProviderHealth(),
        audit_writer=lambda r: None,
    )
    result = await router.run(RouterRequest(lane="claude", task_type="general", user_prompt="hi"))
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "no_provider"


# ── Test (ZDR): zdr_required skips non-ZDR-capable providers ─────────────

@pytest.mark.asyncio
async def test_zdr_skips_non_zdr_providers():
    _clean_env()
    os.environ["OPENAI_API_KEY"] = "k"
    records, writer = _captured_audit()

    mock_oa = AsyncMock()
    mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
    mock_oa.__aexit__ = AsyncMock(return_value=False)
    mock_oa.post = AsyncMock(return_value=_openai_ok_response())

    router = AiRouter(
        adapters=[OpenAiDirectAdapter(http_client=mock_oa)],
        health=ProviderHealth(),
        audit_writer=writer,
    )
    result = await router.run(RouterRequest(
        lane="chatgpt", task_type="general", user_prompt="hi",
        privacy="zdr_required"
    ))
    assert result.ok is False
    assert any("skipped_zdr" in a for a in result.fallbacks_attempted)


# ── Test 11: surface guard flags internal SageForge terms ─────────────────

def test_surface_guard_flags_internal_terms():
    clean = scan_customer_facing("Welcome to your dashboard")
    assert clean.clean is True

    bad = scan_customer_facing("Routed via Forge Factory and ForgeShield")
    assert bad.clean is False
    assert "Forge Factory" in bad.hits
    assert "ForgeShield" in bad.hits


# ── Test: stack is Python ─────────────────────────────────────────────────

def test_stack_is_python():
    """Confirms we are running the Python router, not the TS one."""
    import sfc_ai_router
    assert hasattr(sfc_ai_router, "ai_router"), "Python router package loaded correctly"
