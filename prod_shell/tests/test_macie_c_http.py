"""Exercise the real Flask route offline, with provider invocation intercepted."""
import importlib

import pytest


@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setenv("MACIE_C_SMOKE_ON_BOOT", "0")
    monkeypatch.setenv("MACIE_C_ENABLED", "1")
    monkeypatch.setenv("MACIE_C_API_KEY", "offline-test-key")
    module = importlib.import_module("macie_web")
    calls = []

    def review(document, goal):
        calls.append((document, goal))
        return {"status": "FIXTURE_ONLY", "live_acceptance_passed": False}

    monkeypatch.setattr("prod_shell.src.macie_c.review_document", review)
    return module.app.test_client(), calls


def test_disabled_route_denies_even_valid_key(endpoint, monkeypatch):
    client, calls = endpoint
    monkeypatch.delenv("MACIE_C_ENABLED")
    response = client.post("/macie/c/review", json={"document": "test"},
                           headers={"X-MACIE-C-Key": "offline-test-key"})
    assert response.status_code == 503
    assert calls == []


@pytest.mark.parametrize("supplied", [None, "wrong"])
def test_missing_or_wrong_key_never_invokes_provider(endpoint, supplied):
    client, calls = endpoint
    headers = {} if supplied is None else {"X-MACIE-C-Key": supplied}
    assert client.post("/macie/c/review", json={"document": "test"}, headers=headers).status_code == 401
    assert calls == []


def test_unconfigured_server_key_never_invokes_provider(endpoint, monkeypatch):
    client, calls = endpoint
    monkeypatch.delenv("MACIE_C_API_KEY")
    response = client.post("/macie/c/review", json={"document": "test"})
    assert response.status_code == 401
    assert calls == []


@pytest.mark.parametrize("payload", ["[]", "null", "{broken"])
def test_non_object_or_malformed_json_stops_before_review(endpoint, payload):
    client, calls = endpoint
    response = client.post("/macie/c/review", data=payload, content_type="application/json",
                           headers={"X-MACIE-C-Key": "offline-test-key"})
    assert response.status_code == 400
    assert calls == []


def test_oversized_request_never_invokes_provider(endpoint):
    client, calls = endpoint
    response = client.post("/macie/c/review", data="x" * 250001,
                           headers={"X-MACIE-C-Key": "offline-test-key"})
    assert response.status_code == 413
    assert calls == []


def test_remote_adapter_options_are_not_forwarded(endpoint):
    client, calls = endpoint
    response = client.post("/macie/c/review", json={
        "document": "review me", "goal": "find omissions",
        "options": {"adapters": "untrusted-client-value"},
    }, headers={"X-MACIE-C-Key": "offline-test-key"})
    assert response.status_code == 200
    assert calls == [("review me", "find omissions")]
    assert response.json["live_acceptance_passed"] is False


def test_provider_failure_returns_unavailable(endpoint, monkeypatch):
    client, _ = endpoint
    monkeypatch.setattr("prod_shell.src.macie_c.review_document",
                        lambda *args: {"status": "NON-CONSENSUS", "live_acceptance_passed": False})
    response = client.post("/macie/c/review", json={"document": "review me"},
                           headers={"X-MACIE-C-Key": "offline-test-key"})
    assert response.status_code == 503
    assert response.json["live_acceptance_passed"] is False


def test_engine_exception_is_not_exposed_to_caller(endpoint, monkeypatch):
    client, _ = endpoint

    def broken(*args):
        raise RuntimeError("synthetic-internal-detail")

    monkeypatch.setattr("prod_shell.src.macie_c.review_document", broken)
    response = client.post("/macie/c/review", json={"document": "review me"},
                           headers={"X-MACIE-C-Key": "offline-test-key"})
    assert response.status_code == 503
    assert response.json == {"error": "Review engine unavailable"}
