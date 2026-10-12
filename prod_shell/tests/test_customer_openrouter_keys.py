"""MACIE C buyer-owned provider key tests. No real keys or external calls."""
import json
from types import SimpleNamespace

import pytest

from prod_shell.src import customer_openrouter_keys as vault
from prod_shell.src.macie_c import review_document
from sfc_ai_router.adapters.openrouter import OpenRouterAdapter


def example_key(letter="x"):
    return "sk-" + "or-v1-" + (letter * 42)


@pytest.fixture(autouse=True)
def isolated_vault(monkeypatch):
    monkeypatch.setenv("MACIE_C_SESSION_SECRET", "test-only-secret-for-local-pilot-" * 3)
    vault.clear_for_testing()
    yield
    vault.clear_for_testing()


def test_customer_key_encrypted_in_memory_and_not_shared():
    key = example_key()
    vault.save_key("buyer-a@example.invalid", "sid-a", key, verify=False)
    assert vault.connected("buyer-a@example.invalid", "sid-a")
    assert vault.get_key("buyer-a@example.invalid", "sid-a") == key
    assert vault.get_key("buyer-b@example.invalid", "sid-a") is None
    assert vault.get_key("buyer-a@example.invalid", "sid-b") is None
    assert key not in repr(vault._KEYS)
    assert b"gAAAA" in repr(vault._KEYS).encode()
    vault.revoke("buyer-a@example.invalid", "sid-a")
    assert vault.get_key("buyer-a@example.invalid", "sid-a") is None


def test_rotation_replaces_old_key_and_expiry_revokes(monkeypatch):
    vault.save_key("buyer", "sid", example_key("a"), verify=False)
    vault.save_key("buyer", "sid", example_key("b"), verify=False)
    assert vault.get_key("buyer", "sid") == example_key("b")
    with vault._LOCK:
        slot = vault._slot("buyer", "sid")
        _expiry, encrypted = vault._KEYS[slot]
        vault._KEYS[slot] = (-100, encrypted)
    assert not vault.connected("buyer", "sid")
    assert vault.get_key("buyer", "sid") is None


def test_key_is_verified_via_official_api_without_logging(monkeypatch):
    requests = []
    class Transport:
        def get(self,url,headers,timeout,follow_redirects):
            requests.append((url,headers,timeout,follow_redirects))
            return SimpleNamespace(status_code=200, json=lambda: {"data":{"is_management_key":False}})
    key = example_key()
    vault.verify_openrouter_key(key, client=Transport())
    assert requests[0][0] == "https://openrouter.ai/api/v1/key"
    assert requests[0][1]["Authorization"] == "Bearer " + key
    assert not requests[0][3]


def test_refuses_admin_key_wrong_format_and_provider_rejection():
    class Management:
        def get(self,*args,**kwargs):
            return SimpleNamespace(status_code=200,json=lambda: {"data":{"is_management_key":True}})
    with pytest.raises(ValueError,match="management"):
        vault.verify_openrouter_key(example_key(),client=Management())
    class Invalid:
        def get(self,*args,**kwargs):
            return SimpleNamespace(status_code=401)
    with pytest.raises(ValueError,match="rejected"):
        vault.verify_openrouter_key(example_key(),client=Invalid())
    with pytest.raises(ValueError):
        vault.save_key("buyer","sid","short",verify=False)


def test_explicit_customer_adapter_never_uses_owner_global_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","fake-owner-key-never-used")
    assert not OpenRouterAdapter(customer_api_key="").is_configured()
    assert OpenRouterAdapter(customer_api_key=example_key()).is_configured()


def test_independent_models_use_single_customer_key_not_owner_key(monkeypatch):
    from sfc_ai_router import adapters as adapters_module
    import httpx

    actual_key = example_key("b")
    monkeypatch.setenv("OPENROUTER_API_KEY","owner-must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY","owner-openai-must-not-be-used")
    used = []
    class ProviderResponse:
        def __init__(self,model,text):
            self.status_code=200
            self.text=json.dumps({
                "model":model,
                "choices":[{"message":{"content":text}}],
                "usage":{"prompt_tokens":10,"completion_tokens":10,"total_tokens":20},
            })
    class FakeSession:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        async def post(self,url,headers,json,timeout):
            used.append((url,headers["Authorization"],json["model"]))
            if json["messages"][-1]["content"].startswith("You are the synthesizer for"):
                answer={"synthesized_answer":"Eliminate unsupported marketing promises, verify facts.",
                        "confidence":"medium","confidence_rationale":"Both recommend fact-checking.",
                        "agreement_map":{"validate claims":["claude","chatgpt"]},
                        "divergences":[]}
                return ProviderResponse(json["model"],__import__("json").dumps(answer))
            return ProviderResponse(json["model"],"Review: verify source of sales figures.")
    monkeypatch.setattr(httpx,"AsyncClient",lambda:FakeSession())
    result=review_document(
        "An example property brochure contains a sales claim without a source.",
        customer_openrouter_key=actual_key,
    )
    assert result["status"] == "CONSENSUS"
    assert result["execution_mode"] == "live_attempt"
    assert sorted(result["models_succeeded"]) == ["chatgpt","claude"]
    assert len(used) == 3
    assert all(url=="https://openrouter.ai/api/v1/chat/completions" for url,auth,model in used)
    assert all(auth=="Bearer "+actual_key for url,auth,model in used)
    assert sorted(set(model.split("/")[0] for url,auth,model in used))==["anthropic","openai"]
    assert actual_key not in json.dumps(result)
    assert "owner" not in json.dumps(used)


def test_live_claim_not_possible_with_synthetic_injected_adapters():
    from engine.src import ModelAdapter, AdapterResponse
    class Fake(ModelAdapter):
        def __init__(self,name): self.model_id=name
        def invoke(self,query,options=None):
            return AdapterResponse(text="fixture",model_version=(
                "anthropic/claude-sonnet-4.6" if self.model_id=="claude" else "openai/gpt-4.1"
            ),latency_ms=1,tokens_in=0,tokens_out=0)
    result=review_document("A sample",options={"adapters":{"claude":Fake("claude"),"chatgpt":Fake("chatgpt")}})
    assert result["live_acceptance_passed"] is False
    with pytest.raises(ValueError,match="Cannot combine"):
        review_document("A sample",customer_openrouter_key=example_key(),options={"adapters":{}})
