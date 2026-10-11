"""End-to-end MACIE C dual-model routing test.

Runs the REAL MACIE consensus and routing code using a fake HTTP client,
NOT real Claude/OpenAI calls. Confirms the one-OpenRouter-key workaround
does not depend on ANTHROPIC_API_KEY or OPENAI_API_KEY.
"""
from __future__ import annotations

import json

from engine.src.adapters.router_adapter import RouterAdapter
from prod_shell.src.macie_c import review_document
from sfc_ai_router import AiRouter, OpenRouterAdapter, OpenRouterChatGPTAdapter
from sfc_ai_router.health import ProviderHealth


class _Response:
    status_code = 200

    def __init__(self, model: str, text: str):
        self.text = json.dumps({
            "model": model,
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        })


class _OpenRouterFakeClient:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers, json, timeout):
        model = json["model"]
        self.calls.append((url, model, json["messages"]))
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        if json["messages"][-1]["content"].startswith("You are the synthesizer for"):
            text = __import__("json").dumps({
                "synthesized_answer": (
                    "Keep pre-flight checks, then add a tested backup, pilot drafts, "
                    "idempotent source IDs, safe resumption, and reconciliation of 100 drafts."
                ),
                "confidence": "medium",
                "confidence_rationale": "Both models reject pre-flight alone.",
                "agreement_map": {"pre-flight alone insufficient": ["claude", "chatgpt"]},
                "divergences": [{
                    "claim": "pilot size",
                    "positions": {"claude": "2", "chatgpt": "5"},
                }],
            })
        elif model.startswith("anthropic/"):
            text = "Claude: use backup and an idempotent two-lesson pilot first."
        elif model.startswith("openai/"):
            text = "ChatGPT: use a five-lesson pilot and a reconciliation ledger."
        else:
            raise AssertionError("Unexpected model family " + model)
        return _Response(model, text)


def test_macie_c_runs_both_models_through_one_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-placeholder-not-valid")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AI_ROUTER_PROVIDER_ORDER", raising=False)

    client = _OpenRouterFakeClient()
    router = AiRouter(
        adapters=[
            OpenRouterAdapter(http_client=client),
            OpenRouterChatGPTAdapter(http_client=client),
        ],
        health=ProviderHealth(),
        audit_writer=lambda record: None,
    )
    result = review_document(
        "A WordPress import runbook proposes 100 fsa_lesson draft lessons with "
        "only a WP-CLI and post-type preflight, and then assumes safe completion.",
        goal="Find material risks and improve the implementation runbook.",
        options={"adapters": {
            "claude": RouterAdapter("claude", router=router),
            "chatgpt": RouterAdapter("chatgpt", router=router),
        }},
    )
    versions = {r["model_id"]: r["model_version"] for r in result["model_outputs"]}
    assert versions["claude"].startswith("anthropic/claude-")
    assert versions["chatgpt"].startswith("openai/gpt-")
    assert [model for _url, model, _msg in client.calls] == [
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-4.1",
        "anthropic/claude-sonnet-4.6",
    ] or sorted(model for _url, model, _msg in client.calls) == sorted([
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-4.1",
        "anthropic/claude-sonnet-4.6",
    ])
    assert result["status"] == "FIXTURE_WITH_DIVERGENCES"
    assert "100 drafts" in result["synthesized_review"]
    assert result["execution_mode"] == "injected_test"
    assert result["live_acceptance_passed"] is False
    assert result["models_succeeded"] == ["chatgpt", "claude"]


def test_chatgpt_openrouter_rejects_wrong_model_family():
    from sfc_ai_router.types import RouterRequest
    from unittest.mock import patch

    adapter = OpenRouterChatGPTAdapter()
    request = RouterRequest(lane="chatgpt", task_type="general", user_prompt="test")
    with patch.dict("os.environ", {"OPENROUTER_CHATGPT_MODEL": "anthropic/claude-sonnet-4.6"}):
        import pytest
        with pytest.raises(ValueError, match="openai/"):
            adapter.resolve_model(request)
