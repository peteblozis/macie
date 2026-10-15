"""MACIE B private operational pilot.

This route is separate from MACIE A and MACIE C. It reuses only the hardened
pilot identity/session/key controls; it never loads private SageForge context.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, g, jsonify, make_response, render_template_string, request, session

from prod_shell.src import customer_openrouter_keys as customer_keys
from prod_shell.src import macie_c_portal as shared
from prod_shell.src.macie_b import MAX_PROMPT_CHARS, enhance_with_customer_key
from prod_shell.src.macie_b_template import PAGE_HTML


bp = Blueprint("macie_b_portal", __name__, url_prefix="/macie/b")
_JOB_TTL_SECONDS = 1800
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="macie-b-prompt")
_lock = threading.RLock()
_jobs: dict[str, dict] = {}


def configure_macie_b(app):
    app.register_blueprint(bp)


def _is_ready() -> bool:
    return os.environ.get("MACIE_B_ENABLED") == "1" and shared._is_ready()


def _cleanup_jobs():
    now = time.monotonic()
    with _lock:
        for key, job in list(_jobs.items()):
            if now - job["created"] > _JOB_TTL_SECONDS:
                _jobs.pop(key, None)


def _run_job(job_id: str, prompt: str):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["state"] = "running"
        owner = job["owner"]
        sid = job["session_id"]
    key = customer_keys.get_key(owner, sid)
    if not key:
        with _lock:
            if job_id in _jobs:
                _jobs[job_id]["state"] = "failed"
                _jobs[job_id]["error"] = "Reconnect your OpenRouter key and retry."
        return
    try:
        result = enhance_with_customer_key(prompt, key)
        sanitized = shared._scrub_secret(result, key)
        with _lock:
            if job_id in _jobs:
                _jobs[job_id]["state"] = "finished"
                _jobs[job_id]["result"] = sanitized
    except Exception:
        with _lock:
            if job_id in _jobs:
                _jobs[job_id]["state"] = "failed"
                _jobs[job_id]["error"] = "Prompt consensus failed. Verify your provider key and try again."


@bp.before_request
def protect_portal():
    g.macie_b_nonce = secrets.token_urlsafe(18)
    if not _is_ready():
        return jsonify({"error": "MACIE B private pilot is not yet configured."}), 503


@bp.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'; connect-src 'self'; style-src 'unsafe-inline'; "
        "script-src 'nonce-" + g.macie_b_nonce + "'"
    )
    return response


@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def home():
    email = shared._current_user()
    return make_response(render_template_string(
        PAGE_HTML,
        email=email,
        csrf=session.get("macie_c_csrf", "") if email else "",
        nonce=g.macie_b_nonce,
    ))


@bp.route("/login", methods=["POST"])
def login():
    return shared.login()


@bp.route("/logout", methods=["POST"])
def logout():
    return shared.logout()


@bp.route("/provider", methods=["GET"])
def provider_status():
    return shared.provider_status()


@bp.route("/provider", methods=["POST"])
def provider_connect():
    return shared.provider_connect()


@bp.route("/provider", methods=["DELETE"])
def provider_disconnect():
    return shared.provider_disconnect()


@bp.route("/enhance", methods=["POST"])
def submit_enhancement():
    denied = shared._authenticated()
    if denied:
        return denied
    if not shared._csrf_ok():
        return jsonify({"error": "Invalid CSRF token."}), 403
    if request.content_length and request.content_length > MAX_PROMPT_CHARS * 4 + 1000:
        return jsonify({"error": "Prompt submission exceeds size limit."}), 413
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Provide a valid prompt."}), 400
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "Provide a nonempty prompt."}), 400
    if len(prompt) > MAX_PROMPT_CHARS:
        return jsonify({"error": f"Prompt exceeds {MAX_PROMPT_CHARS:,} characters."}), 400

    _cleanup_jobs()
    owner = shared._current_user()
    sid = session.get("macie_c_sid", "")
    if not customer_keys.connected(owner, sid):
        return jsonify({"error": "Connect your own OpenRouter API key before submitting."}), 409

    with _lock:
        user_running = sum(
            job["owner"] == owner and job["state"] in ("queued", "running")
            for job in _jobs.values()
        )
        if user_running >= 1:
            return jsonify({"error": "A prompt is already processing. Wait for it to finish."}), 429
        job_id = secrets.token_urlsafe(18)
        _jobs[job_id] = {
            "owner": owner,
            "session_id": sid,
            "state": "queued",
            "created": time.monotonic(),
            "result": None,
        }
    _EXECUTOR.submit(_run_job, job_id, prompt)
    return jsonify({"job_id": job_id, "status": "queued", "product": "MACIE-B"}), 202


@bp.route("/enhance/<job_id>", methods=["GET"])
def enhancement_status(job_id):
    denied = shared._authenticated()
    if denied:
        return denied
    _cleanup_jobs()
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["owner"] != shared._current_user():
            return jsonify({"error": "Prompt job not found or expired."}), 404
        response = {"status": job["state"], "product": "MACIE-B"}
        if job["state"] == "finished":
            response["result"] = job["result"]
        if job["state"] == "failed":
            response["error"] = job.get("error", "Prompt consensus failed.")
    return jsonify(response)
