import hashlib
import json
import os

import pytest

from macie_web import app
from prod_shell.src import macie_b_portal as portal


def _record(password="pilot-password"):
    salt = bytes.fromhex("11" * 16)
    rounds = 260000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("MACIE_B_ENABLED", "1")
    monkeypatch.setenv("MACIE_C_ENABLED", "1")
    monkeypatch.setenv("MACIE_C_SESSION_SECRET", "s" * 48)
    monkeypatch.setenv("MACIE_C_USERS_JSON", json.dumps({"owner@example.com": _record()}))
    app.config.update(TESTING=True, SECRET_KEY="test-secret", SESSION_COOKIE_SECURE=False)
    portal._jobs.clear()
    yield
    portal._jobs.clear()


def test_macie_b_has_its_own_private_product_page():
    with app.test_client() as client:
        response = client.get("/macie/b")
        assert response.status_code == 200
        assert b"MACIE B" in response.data
        assert b"prompt created anywhere" in response.data
        assert b"MACIE A private SageForge context is never loaded" in response.data


def test_macie_b_fails_closed_when_disabled(monkeypatch):
    monkeypatch.setenv("MACIE_B_ENABLED", "0")
    with app.test_client() as client:
        response = client.get("/macie/b")
        assert response.status_code == 503


def test_prompt_submission_requires_authentication():
    with app.test_client() as client:
        response = client.post("/macie/b/enhance", json={"prompt": "Improve this"})
        assert response.status_code == 401


def test_authenticated_prompt_requires_buyer_key():
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["macie_c_email"] = "owner@example.com"
            sess["macie_c_sid"] = "session-1"
            sess["macie_c_csrf"] = "csrf-1"
        response = client.post(
            "/macie/b/enhance",
            json={"prompt": "Improve this"},
            headers={"X-CSRF-Token": "csrf-1"},
        )
        assert response.status_code == 409
        assert b"own OpenRouter" in response.data


def test_prompt_job_status_is_owner_scoped():
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["macie_c_email"] = "owner@example.com"
            sess["macie_c_sid"] = "session-1"
            sess["macie_c_csrf"] = "csrf-1"
        portal._jobs["known-job"] = {
            "owner": "someone-else@example.com",
            "session_id": "session-2",
            "state": "finished",
            "created": __import__("time").monotonic(),
            "result": {"secret": "not visible"},
        }
        response = client.get("/macie/b/enhance/known-job")
        assert response.status_code == 404
