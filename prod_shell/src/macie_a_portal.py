"""Authenticated direct entrance for private MACIE A.

This is the owner-only fallback for periods when Cloudflare Access is
misconfigured or unavailable.  It deliberately reuses only the hardened
password verifier and configured user records from the pilot portal; MACIE A
does not expose its SageForge context, provider keys, jobs, or results to
MACIE B/C.
"""
from __future__ import annotations

import hmac
import os
import secrets
import uuid

from flask import Blueprint, current_app, g, jsonify, make_response, render_template_string, request, session

from prod_shell.src import macie_c_portal as auth


bp = Blueprint("macie_a_portal", __name__, url_prefix="/macie/a")


PAGE_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MACIE A | SageForge Consensus</title>
<style>
:root{color-scheme:dark;--bg:#090b10;--panel:#121722;--line:#273043;--gold:#d7b75d;--text:#edf1f7;--muted:#9aa5b5;--bad:#ff8c8c;--ok:#62d7aa}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#1b2030 0,#090b10 48%);color:var(--text);font:16px/1.55 system-ui,sans-serif;min-height:100vh}
main{width:min(900px,calc(100% - 28px));margin:0 auto;padding:28px 0 60px}.brand{color:var(--gold);font-weight:800;letter-spacing:.12em}.private{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em}
h1{font-size:clamp(2rem,7vw,4rem);line-height:1;margin:.6rem 0}.lead{color:var(--muted);max-width:760px}.card{background:rgba(18,23,34,.96);border:1px solid var(--line);border-radius:16px;padding:22px;margin-top:24px;box-shadow:0 16px 50px #0006}
label{display:block;margin:13px 0 6px;font-weight:700}input,textarea,select{width:100%;background:#0b0f17;color:var(--text);border:1px solid #354158;border-radius:10px;padding:13px;font:inherit}textarea{min-height:150px;resize:vertical}
button{border:0;border-radius:10px;background:var(--gold);color:#151106;padding:12px 18px;font-weight:800;font-size:1rem;cursor:pointer;margin-top:14px}button:disabled{opacity:.55;cursor:wait}.row{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.models{color:var(--muted);font-size:.9rem}.error{color:var(--bad);white-space:pre-wrap}.status{color:var(--ok)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#090c12;border:1px solid var(--line);padding:16px;border-radius:10px}.hidden{display:none}footer{color:var(--muted);font-size:.8rem;margin-top:26px}
</style></head><body><main>
<div class="private">ActionForge Labs · Owner-only private system</div><div class="brand">MACIE A</div>
<h1>SageForge consensus</h1><p class="lead">Private SFC-powered analysis. Claude and ChatGPT evaluate independently; MACIE reconciles their answers and fails closed unless both lanes and synthesis succeed.</p>
{% if not email %}
<section class="card"><h2>Sign in</h2><p class="lead">Use your existing private MACIE pilot credentials. This direct entrance avoids the broken Cloudflare MFA enrollment screen.</p>
<form id="login"><label for="email">Email</label><input id="email" type="email" autocomplete="username" required>
<label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>
<p id="loginError" class="error" role="alert"></p><button type="submit">Sign in securely</button></form></section>
{% else %}
<section class="card"><div class="row"><span class="models">Signed in: {{ email }}</span><button id="logout" type="button">Sign out</button></div>
<label for="query">Question or objective</label><textarea id="query" maxlength="18000" placeholder="Enter the question, decision, research objective, or problem for MACIE A..."></textarea>
<div class="row"><span class="models">Claude Sonnet 4.6 · GPT-4.1 · fail-closed consensus</span><button id="run" type="button">Run MACIE A</button></div>
<p id="work" class="status" role="status"></p><p id="error" class="error" role="alert"></p></section>
<section id="result" class="card hidden"><h2>Consensus result</h2><div id="meta" class="models"></div><h3>Synthesized answer</h3><pre id="answer"></pre><h3>Agreements</h3><pre id="agreements"></pre><h3>Divergences</h3><pre id="divergences"></pre><h3>Rationale</h3><pre id="rationale"></pre></section>
{% endif %}
<footer>MACIE A remains private. MACIE B and MACIE C cannot load this context or session.</footer>
<script nonce="{{ nonce }}">(()=>{"use strict";const $=id=>document.getElementById(id),csrf={{ csrf|tojson }};
async function api(url,options){const r=await fetch(url,Object.assign({credentials:"same-origin",cache:"no-store"},options||{}));let d;try{d=await r.json()}catch(e){throw Error("Unexpected server response.")}if(!r.ok)throw Error(d.error||("Request failed: "+r.status));return d}
const login=$("login");if(login)login.addEventListener("submit",async e=>{e.preventDefault();$("loginError").textContent="";try{await api("/macie/a/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("email").value,password:$("password").value})});location.assign("/macie/a")}catch(x){$("loginError").textContent=x.message}});
const logout=$("logout");if(logout)logout.addEventListener("click",async()=>{try{await api("/macie/a/logout",{method:"POST",headers:{"X-CSRF-Token":csrf}});location.assign("/macie/a")}catch(x){$("error").textContent=x.message}});
const run=$("run");if(run)run.addEventListener("click",async()=>{const q=$("query").value.trim();if(!q)return;run.disabled=true;$("error").textContent="";$("work").textContent="Claude and ChatGPT are evaluating independently…";$("result").classList.add("hidden");try{const d=await api("/macie/a/query",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({query:q,shell:"core"})});$("meta").textContent="Confidence: "+d.confidence+" · Request: "+d.request_id;$("answer").textContent=d.synthesized_answer;$("agreements").textContent=d.agreements;$("divergences").textContent=d.divergences;$("rationale").textContent=d.rationale;$("result").classList.remove("hidden");$("work").textContent="Consensus completed."}catch(x){$("work").textContent="";$("error").textContent=x.message}finally{run.disabled=false}})})();</script>
</main></body></html>"""


def configure_macie_a(app):
    app.register_blueprint(bp)


def _allowed() -> set[str]:
    return {x.strip().lower() for x in os.environ.get("MACIE_A_ALLOWED_EMAILS", "").split(",") if x.strip()}


def _current_user() -> str | None:
    email = session.get("macie_a_email")
    if isinstance(email, str) and email in _allowed() and email in auth._users():
        return email
    return None


def _ready() -> bool:
    return os.environ.get("MACIE_A_DIRECT_ENABLED") == "1" and bool(_allowed()) and bool(auth._users()) and len(os.environ.get("MACIE_C_SESSION_SECRET", "")) >= 40


def _cloudflare_user() -> str | None:
    # Delayed import avoids a circular import while macie_web constructs app.
    import macie_web
    return macie_web._cloudflare_access_email()


def _csrf_ok() -> bool:
    supplied = request.headers.get("X-CSRF-Token", "")
    stored = session.get("macie_a_csrf", "")
    return bool(supplied) and bool(stored) and hmac.compare_digest(str(supplied), str(stored)) and auth._same_origin()


@bp.before_request
def protect_portal():
    g.macie_a_nonce = secrets.token_urlsafe(18)
    if not _cloudflare_user() and not _ready():
        return jsonify({"error": "MACIE A direct entrance is not configured."}), 503


@bp.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; connect-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-" + g.macie_a_nonce + "'"
    return response


@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def home():
    cloudflare_email = _cloudflare_user()
    if cloudflare_email:
        import macie_web
        return make_response(render_template_string(
            macie_web.HTML,
            substitution_active=macie_web.cfg.SUBSTITUTION_ACTIVE,
        ))
    email = _current_user()
    return make_response(render_template_string(PAGE_HTML, email=email, csrf=session.get("macie_a_csrf", "") if email else "", nonce=g.macie_a_nonce))


@bp.route("/login", methods=["POST"])
def login():
    if not auth._same_origin():
        return jsonify({"error": "Invalid request origin."}), 403
    if request.content_length and request.content_length > 2048:
        return jsonify({"error": "Invalid login."}), 400
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()[:200]
    password = data.get("password", "")
    key = f"macie-a|{request.remote_addr}|{email}"
    if auth._login_blocked(key):
        return jsonify({"error": "Too many attempts. Please wait 15 minutes."}), 429
    record = auth._users().get(email, "")
    if email not in _allowed() or not isinstance(password, str) or not record or not auth._check_password(password, record):
        auth._record_login_failure(key)
        return jsonify({"error": "Invalid email or password."}), 401
    with auth._lock:
        auth._failed_logins.pop(key, None)
    session.clear()
    session.permanent = True
    session["macie_a_email"] = email
    session["macie_a_csrf"] = secrets.token_urlsafe(32)
    return jsonify({"ok": True, "email": email})


@bp.route("/logout", methods=["POST"])
def logout():
    if not _current_user():
        return jsonify({"error": "Sign in first."}), 401
    if not _csrf_ok():
        return jsonify({"error": "Invalid CSRF token."}), 403
    session.clear()
    return jsonify({"ok": True})


@bp.route("/query", methods=["POST"])
def query():
    if not _current_user():
        return jsonify({"error": "Sign in before running MACIE A."}), 401
    if not _csrf_ok():
        return jsonify({"error": "Invalid CSRF token."}), 403
    data = request.get_json(silent=True) or {}
    question = data.get("query", "")
    if not isinstance(question, str) or not question.strip():
        return jsonify({"error": "Enter a question or objective."}), 400
    question = question.strip()
    if len(question) > 18000:
        return jsonify({"error": "Question exceeds the 18,000-character limit."}), 413

    # Delayed import avoids a circular import during Flask app construction.
    import macie_web
    claude_text, claude_error = macie_web.call_claude(question)
    chatgpt_text, chatgpt_error = macie_web.call_chatgpt(question)
    if claude_error or chatgpt_error or not claude_text or not chatgpt_text:
        return jsonify({"error": "MACIE consensus unavailable: both independent model responses are required.", "consensus_status": "NON_CONSENSUS", "model_statuses": [{"name": "claude", "ok": bool(claude_text) and not claude_error}, {"name": "chatgpt", "ok": bool(chatgpt_text) and not chatgpt_error}]}), 503
    synthesis = macie_web.synthesize(question, claude_text, chatgpt_text)
    parsed = macie_web.parse_synthesis(synthesis or "")
    if not synthesis or not parsed["synthesized_answer"] or not parsed["agreements"] or not parsed["divergences"]:
        return jsonify({"error": "MACIE reconciliation incomplete; no consensus certified.", "consensus_status": "NON_CONSENSUS"}), 503

    request_id = str(uuid.uuid4())[:8]
    macie_web.log_run(request_id=request_id, user_prompt=question, roster=macie_web.cfg.current_roster(), substitution_active=macie_web.cfg.SUBSTITUTION_ACTIVE, substitution_summary=macie_web.cfg.substitution_summary(), shell="core", success=True, confidence=parsed["confidence"], caller_id=_current_user())
    return jsonify({"request_id": request_id, "shell": "core", "substitution_active": macie_web.cfg.SUBSTITUTION_ACTIVE, **parsed, "model_statuses": [{"name": "claude", "ok": True}, {"name": "chatgpt", "ok": True}]})
