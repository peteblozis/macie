"""
Tests for the MACIE agent registry — endpoints and audit logging.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import registry.registry as reg_module
from registry.registry import register_agent, get_agents


# ── Fixtures ────────────────────────────────────────────────────────────────

SEED_DATA = {
    "agents": [
        {
            "caller_id": "INT-FF-001",
            "product": "ForgeFactory",
            "instance": "core",
            "lanes": ["claude", "chatgpt", "gemini"],
            "registered_at": "2026-06-09T00:00:00+00:00",
            "status": "active",
        }
    ]
}


@pytest.fixture()
def registry_file(tmp_path):
    """A temp registry JSON file pre-seeded with one agent."""
    p = tmp_path / "agent-registry.json"
    p.write_text(json.dumps(SEED_DATA), encoding="utf-8")
    return str(p)


@pytest.fixture()
def flask_client(registry_file, monkeypatch):
    """Flask test client with isolated registry path and admin key set."""
    monkeypatch.setenv("MACIE_ADMIN_KEY", "test-admin-key")
    monkeypatch.setenv("MACIE_REGISTRY_PATH", registry_file)

    # Patch the registry path inside the imported module so routes use our temp file
    monkeypatch.setattr(reg_module, "REGISTRY_PATH", Path(registry_file))

    import macie_web
    macie_web.app.config["TESTING"] = True
    with macie_web.app.test_client() as client:
        yield client


ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


# ── POST /macie/register ─────────────────────────────────────────────────────

def test_register_new_agent_succeeds(flask_client, registry_file):
    resp = flask_client.post(
        "/macie/register",
        json={"product": "NewTool", "lanes": ["claude"]},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["product"] == "NewTool"
    assert body["lanes"] == ["claude"]
    assert "caller_id" in body
    assert "registered_at" in body
    assert body["status"] == "active"


def test_register_assigns_correct_caller_id(flask_client, registry_file):
    resp = flask_client.post(
        "/macie/register",
        json={"product": "Spark Engine", "lanes": ["chatgpt"]},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201
    # "Spark Engine" → two words → S + E prefix → SE-001
    assert resp.get_json()["caller_id"] == "SE-001"


def test_register_duplicate_product_rejected(flask_client):
    resp = flask_client.post(
        "/macie/register",
        json={"product": "ForgeFactory", "lanes": ["claude"]},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400
    assert "already registered" in resp.get_json()["error"].lower()


def test_register_invalid_lane_rejected(flask_client):
    resp = flask_client.post(
        "/macie/register",
        json={"product": "BrandNew", "lanes": ["claude", "grok"]},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400
    assert "invalid" in resp.get_json()["error"].lower()


def test_register_requires_admin_key(flask_client):
    resp = flask_client.post(
        "/macie/register",
        json={"product": "AnyTool", "lanes": ["claude"]},
    )
    assert resp.status_code == 401


# ── GET /macie/agents ────────────────────────────────────────────────────────

def test_get_agents_returns_all_agents(flask_client):
    resp = flask_client.get("/macie/agents", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "agents" in body
    assert len(body["agents"]) == 1
    assert body["agents"][0]["caller_id"] == "INT-FF-001"


def test_get_agents_requires_admin_key(flask_client):
    resp = flask_client.get("/macie/agents")
    assert resp.status_code == 401


# ── Audit logging — caller_id ────────────────────────────────────────────────

def test_query_logs_caller_id_when_provided(flask_client, monkeypatch):
    captured = {}

    def fake_log_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("macie_web.log_run", fake_log_run)
    monkeypatch.setattr("macie_web.call_claude", lambda q: ("claude answer", None))
    monkeypatch.setattr("macie_web.call_chatgpt", lambda q: ("chatgpt answer", None))
    monkeypatch.setattr(
        "macie_web.synthesize",
        lambda q, a, b: (
            "SYNTHESIZED ANSWER: test\nCONFIDENCE: high\n"
            "RATIONALE: ok\nAGREEMENTS: both agree\nDIVERGENCES: none"
        ),
    )

    flask_client.post(
        "/macie/query",
        json={"query": "what is 2+2"},
        headers={"X-Caller-ID": "INT-FF-001"},
    )

    assert captured.get("caller_id") == "INT-FF-001"


def test_query_logs_unregistered_when_caller_id_absent(flask_client, monkeypatch):
    captured = {}

    def fake_log_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("macie_web.log_run", fake_log_run)
    monkeypatch.setattr("macie_web.call_claude", lambda q: ("claude answer", None))
    monkeypatch.setattr("macie_web.call_chatgpt", lambda q: ("chatgpt answer", None))
    monkeypatch.setattr(
        "macie_web.synthesize",
        lambda q, a, b: (
            "SYNTHESIZED ANSWER: test\nCONFIDENCE: high\n"
            "RATIONALE: ok\nAGREEMENTS: both agree\nDIVERGENCES: none"
        ),
    )

    flask_client.post(
        "/macie/query",
        json={"query": "what is 2+2"},
    )

    # caller_id=None is passed; audit_log.py converts it to "UNREGISTERED"
    assert captured.get("caller_id") is None
