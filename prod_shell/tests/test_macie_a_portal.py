"""Acceptance tests for the owner-only direct MACIE A entrance."""
import hashlib
import json

import pytest

import macie_web
from macie_web import app
from prod_shell.src import macie_a_portal as portal


def password_record(password: str, salt: bytes = b"abcdefghijklmnop"):
    rounds = 260000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("MACIE_A_DIRECT_ENABLED", "1")
    monkeypatch.setenv("MACIE_A_ALLOWED_EMAILS", "owner@example.com")
    monkeypatch.setenv("MACIE_C_ENABLED", "1")
    monkeypatch.setenv("MACIE_C_SESSION_SECRET", "session-secret-for-tests-only-" * 3)
    monkeypatch.setenv("MACIE_C_USERS_JSON", json.dumps({"owner@example.com": password_record("strong-owner-password"), "buyer@example.com": password_record("buyer-password")}))
    app.config.update(TESTING=True, SECRET_KEY="test-secret-not-live-" * 4)
    with app.test_client() as c:
        yield c


def sign_in(client):
    response = client.post("/macie/a/login", json={"email": "owner@example.com", "password": "strong-owner-password"})
    assert response.status_code == 200
    with client.session_transaction() as session:
        return session["macie_a_csrf"]


def test_direct_entrance_requires_signin(client):
    home = client.get("/macie/a")
    assert home.status_code == 200
    assert b"Sign in" in home.data
    assert b"Run MACIE A" not in home.data
    assert client.post("/macie/a/query", json={"query": "private"}).status_code == 401


def test_only_macie_a_allowlist_can_sign_in(client):
    denied = client.post("/macie/a/login", json={"email": "buyer@example.com", "password": "buyer-password"})
    assert denied.status_code == 401
    sign_in(client)
    home = client.get("/macie/a")
    assert b"Run MACIE A" in home.data
    assert b"MACIE B and MACIE C cannot load this context" in home.data


def test_consensus_is_fail_closed(client, monkeypatch):
    csrf = sign_in(client)
    monkeypatch.setattr(macie_web, "call_claude", lambda q: ("Claude result", None))
    monkeypatch.setattr(macie_web, "call_chatgpt", lambda q: ("", "provider failed"))
    response = client.post("/macie/a/query", json={"query": "test"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 503
    assert response.json["consensus_status"] == "NON_CONSENSUS"


def test_consensus_success_and_csrf(client, monkeypatch):
    csrf = sign_in(client)
    monkeypatch.setattr(macie_web, "call_claude", lambda q: ("Claude result", None))
    monkeypatch.setattr(macie_web, "call_chatgpt", lambda q: ("ChatGPT result", None))
    monkeypatch.setattr(macie_web, "synthesize", lambda q, a, b: "SYNTHESIZED ANSWER:\nUse the repaired path.\nCONFIDENCE: high\nRATIONALE: Both agree.\nAGREEMENTS: Secure private access.\nDIVERGENCES: None significant")
    monkeypatch.setattr(macie_web, "log_run", lambda **kwargs: None)
    assert client.post("/macie/a/query", json={"query": "test"}).status_code == 403
    response = client.post("/macie/a/query", json={"query": "test"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.json["confidence"] == "high"
    assert response.json["synthesized_answer"] == "Use the repaired path."


def test_disabled_by_default(client, monkeypatch):
    monkeypatch.setenv("MACIE_A_DIRECT_ENABLED", "0")
    response = client.get("/macie/a")
    assert response.status_code == 503
    assert response.headers["Cache-Control"].startswith("no-store")
