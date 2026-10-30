"""Owner-only UPSCAN HTTP bridge for Claude Code subscription tasks.

Disabled by default. Never uses Console, OpenRouter, or paid API fallback.
The trigger starts a session; only its scoped return receipt advances review.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from urllib import request as http
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request

from .upscan_consensus import ProtocolError, ReviewStore, phase, result, reviewer_request


class NoRedirect(http.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fire(url, token, payload):
    # Redirects must not forward the bearer token to another origin.
    req = http.Request(url, data=json.dumps({"text": json.dumps(payload)}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "anthropic-version": "2026-10-21"}, method="POST")
    with http.build_opener(NoRedirect()).open(req, timeout=20) as response:
        data = json.loads(response.read(65537))
    session_id = data.get("claude_code_session_id", "")
    if data.get("type") != "routine_fire" or not isinstance(session_id, str) or not session_id.startswith("session_"):
        raise ProtocolError("Claude did not return a valid session identifier")
    return session_id


def _config():
    c = {k: os.environ.get(k, "") for k in (
        "MACIE_ADMIN_KEY", "UPSCAN_RECEIPT_SECRET", "UPSCAN_STORE_PATH",
        "UPSCAN_CLAUDE_FIRE_URL", "UPSCAN_CLAUDE_FIRE_TOKEN", "UPSCAN_RETURN_BASE_URL")}
    if os.environ.get("UPSCAN_ENABLED") != "1":
        raise ProtocolError("UPSCAN bridge is disabled")
    if len(c["MACIE_ADMIN_KEY"]) < 32 or len(c["UPSCAN_RECEIPT_SECRET"]) < 32:
        raise ProtocolError("Owner and scoped-receipt authentication are not configured")
    if not Path(c["UPSCAN_STORE_PATH"]).is_absolute():
        raise ProtocolError("Private persistent UPSCAN storage is not configured")
    if not re.fullmatch(r"https://api\.anthropic\.com/v1/claude_code/routines/[A-Za-z0-9_-]+/fire", c["UPSCAN_CLAUDE_FIRE_URL"]):
        raise ProtocolError("Only the Claude Code subscription trigger is allowed")
    if not c["UPSCAN_CLAUDE_FIRE_TOKEN"].startswith("sk-ant-oat01-"):
        raise ProtocolError("A routine-scoped token is required; API keys are not accepted")
    u = urlsplit(c["UPSCAN_RETURN_BASE_URL"])
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ProtocolError("An approved HTTPS private return address is required")
    if (os.environ.get("UPSCAN_SUBSCRIPTION_VERIFIED") != "1" or
            os.environ.get("UPSCAN_NO_OVERAGE_VERIFIED") != "1"):
        raise ProtocolError("Subscription eligibility and disabled metered overage require verification")
    return c


def _capability(c, run_id, dispatch):
    data = {"run_id": run_id, "phase": dispatch["phase"], "nonce": dispatch["nonce"],
            "expires_at": dispatch["expires_at"]}
    payload = base64.urlsafe_b64encode(json.dumps(data, sort_keys=True).encode()).decode()
    signature = hmac.new(c["UPSCAN_RECEIPT_SECRET"].encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def _verify(c, token):
    try:
        if len(token) > 2048:
            raise ValueError()
        payload, supplied = token.split(".")
        expected = hmac.new(c["UPSCAN_RECEIPT_SECRET"].encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload))
        if time.time() >= data["expires_at"]:
            raise ValueError()
        return data
    except (ValueError, TypeError, KeyError):
        raise ProtocolError("Invalid or expired return capability") from None


def configure_upscan(app, *, store=None, fire=None):
    if fire is not None and (store is None or not store.test_only):
        raise ValueError("Injected transports require fixture-only storage")
    bp = Blueprint("private_upscan", __name__, url_prefix="/internal/upscan")
    trigger = fire or _fire
    stores = {}

    def dispatcher_view(job):
        output = result(job)
        if phase(job) in ("review", "challenge", "accept") and "chatgpt" not in job["receipts"][phase(job)]:
            output["chatgpt_work"] = reviewer_request(job, "chatgpt")
        if "chatgpt" not in job["receipts"]["review"]:
            # A fast Claude response must not contaminate ChatGPT's first review.
            output["receipts"] = {**output["receipts"], "review": {}}
        return output

    def current_store(c):
        if store is not None:
            return store
        path = c["UPSCAN_STORE_PATH"]
        if path not in stores:
            stores[path] = ReviewStore(path)
        return stores[path]

    @bp.before_request
    def protect():
        try:
            c = _config()
        except ProtocolError as exc:
            return jsonify(error=str(exc), consensus_status="NON-CONSENSUS"), 503
        # Only the narrow callback accepts a run/phase capability. Everything
        # else needs the existing owner API key; commercial sessions cannot use it.
        if request.endpoint != "private_upscan.callback":
            supplied = request.headers.get("X-Admin-Key", "")
            if not hmac.compare_digest(supplied, c["MACIE_ADMIN_KEY"]):
                return jsonify(error="Owner authentication required"), 401
        if request.content_length and request.content_length > 150000:
            return jsonify(error="Review request exceeds size limit"), 413

    @bp.after_request
    def private_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @bp.errorhandler(ProtocolError)
    def protocol_error(exc):
        return jsonify(error=str(exc), consensus_status="NON-CONSENSUS"), 409

    def advance(c, s, run_id):
        dispatch = s.claim_dispatch(run_id)
        if dispatch:
            payload = dispatch["request"]
            payload["return"] = {"url": c["UPSCAN_RETURN_BASE_URL"].rstrip("/") + "/internal/upscan/callback",
                "bearer": _capability(c, run_id, dispatch),
                "instructions": "POST JSON containing evidence_hash, model_version and body. "
                    "Use this capability only for this return. Do not put it in logs, GitHub, or the report. "
                    "A 409 means the trigger receipt is not registered yet; retry this return only, at most twice."}
            try:
                session_id = trigger(c["UPSCAN_CLAUDE_FIRE_URL"], c["UPSCAN_CLAUDE_FIRE_TOKEN"], payload)
            except Exception:
                # A timeout can mean the session started. Never auto-retry fire:
                # Anthropic's endpoint has no idempotency key.
                return s.dispatched(run_id, dispatch["phase"], error="Claude dispatch failed or outcome unknown; automatic re-fire denied")
            s.dispatched(run_id, dispatch["phase"], session_id=session_id)
        job = s.get(run_id)
        return dispatcher_view(job)

    @bp.post("/runs")
    def create():
        c = _config()
        s = current_store(c)
        d = request.get_json(silent=True) or {}
        job = s.create(d.get("run_key"), d.get("packet"), ttl=d.get("ttl", 900))
        return jsonify(advance(c, s, job["run_id"]))

    @bp.get("/runs/<run_id>")
    def read(run_id):
        c = _config()
        s = current_store(c)
        job = s.get(run_id)
        return jsonify(dispatcher_view(job))

    @bp.post("/runs/<run_id>/chatgpt")
    def chatgpt(run_id):
        c = _config()
        s = current_store(c)
        d = request.get_json(silent=True) or {}
        s.receipt(run_id, "chatgpt", d.get("phase"), d.get("evidence_hash"),
            d.get("body"), model_version=d.get("model_version"), transport="chatgpt_dispatcher")
        return jsonify(advance(c, s, run_id))

    @bp.post("/runs/<run_id>/draft")
    def draft(run_id):
        c = _config()
        s = current_store(c)
        d = request.get_json(silent=True) or {}
        s.draft(run_id, d.get("draft"))
        return jsonify(advance(c, s, run_id))

    @bp.post("/callback")
    def callback():
        c = _config()
        s = current_store(c)
        header = request.headers.get("Authorization", "")
        cap = _verify(c, header.removeprefix("Bearer ") if header.startswith("Bearer ") else "")
        job = s.get(cap["run_id"])
        dispatched = job["dispatches"].get(cap["phase"], {})
        if cap["nonce"] != dispatched.get("nonce") or not dispatched.get("session_id"):
            raise ProtocolError("No matching registered Claude session for this return")
        d = request.get_json(silent=True) or {}
        s.receipt(job["run_id"], "claude", cap["phase"], d.get("evidence_hash"),
            d.get("body"), model_version=d.get("model_version"), transport="claude_code_subscription",
            session_id=dispatched["session_id"])
        # Never return the private reviews or ChatGPT work through the callback.
        outcome = advance(c, s, job["run_id"])
        return jsonify(run_id=job["run_id"], status=outcome["status"], phase=outcome["phase"])

    app.register_blueprint(bp)
