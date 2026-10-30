"""Offline acceptance of real state/transport boundaries, never live consensus."""
import copy
import json
import time

import pytest
from flask import Flask

from core_shell.src.upscan_consensus import (
    ProtocolError, ReviewStore, digest, phase, result, reviewer_request, validate_packet,
)
from core_shell.src.upscan_bridge import configure_upscan, _config


@pytest.fixture
def packet():
    return {"sources": [{"id": "s1", "url": "https://example.org/release", 
                          "retrieved_at": "2026-10-30T15:00:00Z", "excerpt": "Public example."}],
            "candidates": [{"id": "c1", "source_ids": ["s1"], "claim": "A proposed test"}],
            "constraints": "Read-only. No extra spending."}


@pytest.fixture
def store(tmp_path):
    return ReviewStore(tmp_path / "runs.sqlite", test_only=True)


def send(store, job, lane, p, body=None):
    return store.receipt(job["run_id"], lane, p, job["evidence_hash"],
        body or {"findings": "Check this claim against s1", "source_ids": ["s1"]},
        model_version="claude-fixture" if lane == "claude" else "gpt-fixture",
        transport="claude_code_subscription" if lane == "claude" else "chatgpt_dispatcher",
        session_id="session_fixture" if lane == "claude" else "")


def draft_ready(store, packet):
    job = store.create("daily", packet)
    for p in ("review", "challenge"):
        for lane in ("chatgpt", "claude"):
            send(store, job, lane, p)
    store.draft(job["run_id"], {"items": [{"id": "c1", "recommendation": "TEST", "source_ids": ["s1"]}]})
    return store.get(job["run_id"])


def accept(job, *, agree=True, ids=None):
    return {"draft_hash": job["draft_hash"], "accept_report": agree,
            "accepted_ids": ["c1"] if ids is None else ids,
            "disagreements": "" if agree else "Cost remains uncertain"}


def test_complete_fixture_never_certifies_live_consensus(store, packet):
    job = draft_ready(store, packet)
    for lane in ("chatgpt", "claude"):
        send(store, job, lane, "accept", accept(job))
    assert result(store.get(job["run_id"]))["status"] == "FIXTURE_ONLY:CONSENSUS"


def test_partial_acceptance_preserves_disagreement(store, packet):
    job = draft_ready(store, packet)
    send(store, job, "chatgpt", "accept", accept(job))
    send(store, job, "claude", "accept", accept(job, agree=False))
    output = result(store.get(job["run_id"]))
    assert output["status"] == "FIXTURE_ONLY:PARTIAL CONSENSUS"
    assert output["agreed_ids"] == ["c1"]
    assert output["receipts"]["accept"]["claude"]["body"]["disagreements"]


def test_no_agreed_items_is_non_consensus(store, packet):
    job = draft_ready(store, packet)
    send(store, job, "chatgpt", "accept", accept(job))
    send(store, job, "claude", "accept", accept(job, agree=False, ids=[]))
    assert result(store.get(job["run_id"]))["status"] == "FIXTURE_ONLY:NON-CONSENSUS"


def test_final_text_change_invalidates_acceptance(store, packet):
    job = draft_ready(store, packet)
    wrong = accept(job)
    wrong["draft_hash"] = digest({"changed": True})
    with pytest.raises(ProtocolError, match="content hash"):
        send(store, job, "claude", "accept", wrong)


def test_one_lane_is_never_enough(store, packet):
    job = store.create("daily", packet)
    send(store, job, "chatgpt", "review")
    assert phase(store.get(job["run_id"])) == "review"
    with pytest.raises(ProtocolError):
        store.draft(job["run_id"], {"items": []})


def test_duplicate_run_is_idempotent_and_changed_evidence_rejected(store, packet):
    one = store.create("daily", packet)
    assert store.create("daily", packet)["run_id"] == one["run_id"]
    changed = copy.deepcopy(packet)
    changed["sources"][0]["excerpt"] = "Changed"
    with pytest.raises(ProtocolError, match="different evidence"):
        store.create("daily", changed)


def test_duplicate_callback_is_idempotent_but_cannot_replace_review(store, packet):
    job = store.create("daily", packet)
    send(store, job, "claude", "review")
    send(store, job, "claude", "review")
    with pytest.raises(ProtocolError, match="overwritten"):
        send(store, job, "claude", "review", {"findings": "Changed", "source_ids": ["s1"]})


def test_blind_request_has_no_peer_output(store, packet):
    job = store.create("daily", packet)
    send(store, job, "claude", "review")
    work = reviewer_request(store.get(job["run_id"]), "chatgpt")
    assert "independent_reviews" not in work


def test_deadline_prevents_late_completion(store, packet, monkeypatch):
    job = store.create("daily", packet)
    monkeypatch.setattr(time, "time", lambda: job["expires_at"] + 1)
    with pytest.raises(ProtocolError, match="expired"):
        send(store, job, "claude", "review")
    assert result(store.get(job["run_id"]))["status"] == "FIXTURE_ONLY:NON-CONSENSUS"


@pytest.mark.parametrize("mutation", ["too_many", "unknown_source", "duplicate", "no_sources", "unhashable"])
def test_invalid_evidence_rejected(packet, mutation):
    if mutation == "too_many": packet["candidates"] *= 6
    if mutation == "unknown_source": packet["candidates"][0]["source_ids"] = ["invented"]
    if mutation == "duplicate": packet["sources"] *= 2
    if mutation == "no_sources": packet["sources"] = []
    if mutation == "unhashable": packet["candidates"][0]["source_ids"] = [{}]
    with pytest.raises(ProtocolError): validate_packet(packet)


def test_substituted_model_is_rejected(store, packet):
    job = store.create("daily", packet)
    with pytest.raises(ProtocolError, match="identity"):
        store.receipt(job["run_id"], "claude", "review", job["evidence_hash"], {},
            model_version="openai/gpt", transport="claude_code_subscription", session_id="session_a")


def test_dispatch_claim_survives_restart_and_prevents_duplicate_fire(store, packet):
    job = store.create("daily", packet)
    assert store.claim_dispatch(job["run_id"])
    restarted = ReviewStore(store.path, test_only=True)
    assert restarted.claim_dispatch(job["run_id"]) is None


def test_empty_candidate_set_still_requires_both_acceptances(store, packet):
    packet["candidates"] = []
    packet["no_change_reason"] = "No material delta"
    job = store.create("daily", packet)
    for p in ("review", "challenge"):
        for lane in ("chatgpt", "claude"): send(store, job, lane, p)
    store.draft(job["run_id"], {"items": [], "no_change_reason": "No material delta"})
    job = store.get(job["run_id"])
    send(store, job, "chatgpt", "accept", accept(job, ids=[]))
    assert result(store.get(job["run_id"]))["status"] == "PENDING"
    send(store, job, "claude", "accept", accept(job, ids=[]))
    assert result(store.get(job["run_id"]))["status"] == "FIXTURE_ONLY:CONSENSUS"


@pytest.fixture
def bridge(monkeypatch, store):
    config = {"UPSCAN_ENABLED": "1", "MACIE_ADMIN_KEY": "a" * 40,
        "UPSCAN_RECEIPT_SECRET": "r" * 40, "UPSCAN_STORE_PATH": store.path,
        "UPSCAN_CLAUDE_FIRE_URL": "https://api.anthropic.com/v1/claude_code/routines/trig_test/fire",
        "UPSCAN_CLAUDE_FIRE_TOKEN": "sk-ant-oat01-fixture",
        "UPSCAN_RETURN_BASE_URL": "https://private.example.org",
        "UPSCAN_SUBSCRIPTION_VERIFIED": "1", "UPSCAN_NO_OVERAGE_VERIFIED": "1"}
    for k, v in config.items(): monkeypatch.setenv(k, v)
    calls = []
    def fire(url, token, payload):
        calls.append(payload)
        return "session_fixture"
    app = Flask(__name__)
    configure_upscan(app, store=store, fire=fire)
    return app.test_client(), calls, {"X-Admin-Key": "a" * 40}, store


def callback(client, call, body=None):
    return client.post("/internal/upscan/callback", headers={"Authorization": "Bearer " + call["return"]["bearer"]},
        json={"evidence_hash": call["evidence_hash"], "model_version": "claude-fixture",
              "body": body or {"findings": "Independent judgment", "source_ids": ["s1"]}})


def test_http_automates_three_claude_stages_and_returns_real_fixture_status(bridge, packet):
    client, calls, auth, store = bridge
    created = client.post("/internal/upscan/runs", headers=auth, json={"run_key": "one", "packet": packet}).get_json()
    rid, eh = created["run_id"], created["evidence_hash"]
    # Fast Claude must not reveal its independent judgment to ChatGPT yet.
    assert callback(client, calls[0]).status_code == 200
    visible = client.get(f"/internal/upscan/runs/{rid}", headers=auth).get_json()
    assert visible["receipts"]["review"] == {}
    for p in ("review", "challenge"):
        r = client.post(f"/internal/upscan/runs/{rid}/chatgpt", headers=auth,
            json={"phase": p, "evidence_hash": eh, "model_version": "gpt-fixture",
                  "body": {"findings": "My assessment", "source_ids": ["s1"]}})
        assert r.status_code == 200
        if p == "challenge": assert callback(client, calls[1]).status_code == 200
    r = client.post(f"/internal/upscan/runs/{rid}/draft", headers=auth,
        json={"draft": {"items": [{"id": "c1", "recommendation": "TEST", "source_ids": ["s1"]}]}})
    assert r.status_code == 200
    job = store.get(rid)
    assert callback(client, calls[2], accept(job)).status_code == 200
    completed = client.post(f"/internal/upscan/runs/{rid}/chatgpt", headers=auth,
        json={"phase": "accept", "evidence_hash": eh, "model_version": "gpt-fixture", "body": accept(job)})
    assert completed.get_json()["status"] == "FIXTURE_ONLY:CONSENSUS"
    assert [c["phase"] for c in calls] == ["review", "challenge", "accept"]
    assert "independent_reviews" not in calls[0]
    assert "independent_reviews" in calls[1]
    assert "draft_hash" in calls[2]


def test_http_rejects_unauthenticated_and_forged_returns(bridge, packet):
    client, calls, auth, store = bridge
    assert client.post("/internal/upscan/runs", json={"run_key": "x", "packet": packet}).status_code == 401
    client.post("/internal/upscan/runs", headers=auth, json={"run_key": "x", "packet": packet})
    token = calls[0]["return"]["bearer"]
    assert client.post("/internal/upscan/callback", headers={"Authorization": "Bearer " + token + "x"}, json={}).status_code == 409
    assert client.get("/internal/upscan/runs/anything", headers={"X-Admin-Key": token}).status_code == 401


def test_http_duplicate_submission_fires_once(bridge, packet):
    client, calls, auth, store = bridge
    for _ in range(2):
        assert client.post("/internal/upscan/runs", headers=auth, json={"run_key": "x", "packet": packet}).status_code == 200
    assert len(calls) == 1


def test_config_disallows_paid_api_and_requires_no_overage_verification(bridge, monkeypatch):
    monkeypatch.setenv("UPSCAN_CLAUDE_FIRE_TOKEN", "sk-ant-api-not-allowed")
    with pytest.raises(ProtocolError, match="API keys"): _config()
    monkeypatch.setenv("UPSCAN_CLAUDE_FIRE_TOKEN", "sk-ant-oat01-test")
    monkeypatch.setenv("UPSCAN_NO_OVERAGE_VERIFIED", "0")
    with pytest.raises(ProtocolError, match="overage"): _config()


def test_disabled_bridge_has_no_provider_calls(bridge, monkeypatch, packet):
    client, calls, auth, store = bridge
    monkeypatch.setenv("UPSCAN_ENABLED", "0")
    assert client.post("/internal/upscan/runs", headers=auth, json={"run_key": "x", "packet": packet}).status_code == 503
    assert not calls


def test_session_started_is_not_completed_consensus(bridge, packet):
    client, calls, auth, store = bridge
    response = client.post("/internal/upscan/runs", headers=auth, json={"run_key": "x", "packet": packet})
    output = response.get_json()
    assert output["status"] == "PENDING"
    assert output["receipts"]["review"] == {}
    job = store.get(output["run_id"])
    assert job["dispatches"]["review"]["state"] == "awaiting_receipt"


def test_uncertain_fire_is_non_consensus_and_never_refired(bridge, packet):
    _, _, auth, store = bridge
    attempts = []
    def timeout(*args):
        attempts.append(1)
        raise TimeoutError("Simulated lost response after remote session may have started")
    app = Flask("uncertain")
    configure_upscan(app, store=store, fire=timeout)
    client = app.test_client()
    for _ in range(2):
        response = client.post("/internal/upscan/runs", headers=auth, json={"run_key": "x", "packet": packet})
        assert response.get_json()["status"] == "FIXTURE_ONLY:NON-CONSENSUS"
    assert len(attempts) == 1


def test_source_gap_cannot_be_misrepresented_as_verified_review(store, packet):
    job = store.create("daily", packet)
    with pytest.raises(ProtocolError, match="known evidence"):
        send(store, job, "claude", "review", {"findings": "Could not access sources", "source_ids": []})
    assert phase(store.get(job["run_id"])) == "review"
