"""MACIE C commercial self-service API (closed until infrastructure verified).

This intentionally runs BESIDE the existing controlled pilot. It cannot
serve a paying customer until explicitly enabled with production Postgres,
SMTP, merchant checkout and an approved worker/recovery design.

Every identity assertion, entitlement and review permission is checked
server-side. Customer-supplied tenant or subscription status is ignored.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, current_app, g, jsonify, request, session, render_template_string

from prod_shell.src.commercial_mail import mail_configured, send_token_message
from prod_shell.src.commercial_billing import StripeGateway, CheckoutPending
from prod_shell.src.commercial_store import Store, production_engine
from prod_shell.src.commercial_template import HTML
from prod_shell.src.customer_openrouter_keys import verify_openrouter_key
from prod_shell.src.macie_c import review_document
from prod_shell.src.macie_c_portal import _submitted_document, _scrub_secret

bp=Blueprint("macie_c_commercial",__name__,url_prefix="/macie/c/commercial")
_WORKERS=ThreadPoolExecutor(max_workers=2,thread_name_prefix="macie-c-buyer-worker")
_STORE_LOCK=threading.Lock()
_STORE=None


def _expire_old_documents():
    """Background retention enforcement; job results are never retained past TTL.

    Each Render web worker may run one cleaner; deletion is idempotent in DB.
    A missing DB must not crash the unrelated private/pilot applications.
    """
    while True:
        try:
            if _configured():
                _store().delete_expired_reviews()
        except Exception:
            pass  # Never log document content, credentials, or SQL secrets.
        time.sleep(900)


def configure_commercial(app):
    app.register_blueprint(bp)
    if os.environ.get("MACIE_C_COMMERCIAL_RELEASE_APPROVED")=="1":
        threading.Thread(
            target=_expire_old_documents,daemon=True,
            name="macie-c-retention-cleaner",
        ).start()


def _configured() -> bool:
    return all((
        os.environ.get("MACIE_C_COMMERCIAL_ENABLED")=="1",
        # Separate one-time production release decision; never enable from
        # account signup, payment callback, test fixture, or deployment alone.
        os.environ.get("MACIE_C_COMMERCIAL_RELEASE_APPROVED")=="1",
        os.environ.get("MACIE_C_SIGNED_TERMS_VERSION"),
        os.environ.get("MACIE_C_PRIVACY_VERSION"),
        os.environ.get("MACIE_C_CUSTOMER_SUPPORT_EMAIL"),
        os.environ.get("MACIE_C_TERMS_URL","").startswith("https://"),
        os.environ.get("MACIE_C_PRIVACY_URL","").startswith("https://"),
        os.environ.get("MACIE_C_COMMERCIAL_PLAN_DISPLAY"),
        # Paid live access must not accidentally use sandbox invoices.
        os.environ.get("MACIE_C_MERCHANT_LIVE_MODE")=="1",
        os.environ.get("MACIE_C_COMMERCIAL_DATABASE_URL","").startswith(
            ("postgresql://","postgresql+psycopg://")),
        len(os.environ.get("MACIE_C_COMMERCIAL_VAULT_SECRET",""))>=40,
        mail_configured(),
        bool(os.environ.get("MACIE_C_MERCHANT_SECRET_KEY")),
        bool(os.environ.get("MACIE_C_MERCHANT_WEBHOOK_SECRET")),
        bool(os.environ.get("MACIE_C_MERCHANT_PRICE_ID")),
        (os.environ.get("MACIE_C_COMMERCIAL_PLAN_LIMIT","").isdigit()
         and int(os.environ.get("MACIE_C_COMMERCIAL_PLAN_LIMIT","0"))>0),
    ))


def _store() -> Store:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                s=Store(production_engine(),os.environ["MACIE_C_COMMERCIAL_VAULT_SECRET"])
                s.assert_schema()  # never bootstrap production schema automatically
                _STORE=s
    return _STORE


def _origin_ok() -> bool:
    from urllib.parse import urlsplit
    origin=request.headers.get("Origin")
    if not origin:
        return True  # authenticated writes still require CSRF
    u=urlsplit(origin)
    return (u.scheme==("http" if current_app.testing else "https")
            and u.netloc.lower()==request.host.lower()
            and u.path in ("","/"))


def _csrf_ok() -> bool:
    import hmac
    supplied=request.headers.get("X-CSRF-Token","")
    expected=session.get("commercial_csrf","")
    return bool(expected and supplied) and hmac.compare_digest(expected,supplied) and _origin_ok()


def _who() -> tuple[str,str] | None:
    uid=session.get("commercial_user_id")
    tenant=session.get("commercial_tenant_id")
    if not isinstance(uid,str) or not isinstance(tenant,str):
        return None
    row=_store().get_account(uid)
    if not row or not row["verified"] or row["session_version"]!=session.get("commercial_session_version"):
        return None
    membership=_store().membership(uid,tenant)
    if not membership or not membership.active:
        return None
    return uid,tenant


def _require_account():
    identity=_who()
    if not identity:
        return None,(jsonify({"error":"Sign in to your own MACIE C account."}),401)
    return identity,None


def _require_post():
    if not _csrf_ok():
        return jsonify({"error":"Invalid request authenticity token."}),403
    return None


def _body(max_bytes=4000):
    if request.content_length and request.content_length>max_bytes:
        raise ValueError("Request exceeded size limit.")
    parsed=request.get_json(silent=True)
    if not isinstance(parsed,dict):
        raise ValueError("Provide a valid JSON object.")
    return parsed


@bp.before_request
def commercial_gate():
    g.macie_commercial_nonce=secrets.token_urlsafe(18)
    if not _configured():
        return jsonify({"error":"Commercial MACIE C is not yet available."}),503


@bp.after_request
def commercial_security(response):
    response.headers["Cache-Control"]="no-store, max-age=0"
    response.headers["Pragma"]="no-cache"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Content-Security-Policy"]=(
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
        "connect-src 'self'; form-action 'self'; style-src 'unsafe-inline'; "
        "script-src 'nonce-"+g.macie_commercial_nonce+"'"
    )
    return response


@bp.route("",methods=["GET"])
@bp.route("/",methods=["GET"])
def homepage():
    identity=_who()
    return render_template_string(
        HTML,
        nonce=g.macie_commercial_nonce,
        user_id=identity[0] if identity else None,
        csrf=session.get("commercial_csrf","") if identity else "",
        terms_url=os.environ.get("MACIE_C_TERMS_URL",""),
        privacy_url=os.environ.get("MACIE_C_PRIVACY_URL",""),
        support_email=os.environ.get("MACIE_C_CUSTOMER_SUPPORT_EMAIL",""),
        plan_display=os.environ.get("MACIE_C_COMMERCIAL_PLAN_DISPLAY",""),
    )


@bp.route("/status",methods=["GET"])
def status():
    who=_who()
    if not who:
        return jsonify({"authenticated":False})
    uid,tenant=who
    ent=_store().entitlement(tenant)
    return jsonify({
        "authenticated":True,
        "email":_store().get_account(uid)["email"],
        "organization_id":tenant,
        "provider_connected":bool(_store().get_key(uid,tenant)),
        "subscription":{
            "status":ent.status,"billing_verified":ent.billing_verified,
            "review_limit":ent.review_limit,"reviews_consumed":ent.reviews_consumed,
        } if ent else None,
    })


@bp.route("/signup",methods=["POST"])
def signup():
    if not _origin_ok():
        return jsonify({"error":"Invalid request origin."}),403
    try:
        body=_body()
        email=body.get("email","")
        if body.get("accept_terms") is not True:
            return jsonify({"error":"Accept the product terms and privacy notice first."}),400
        remote=request.remote_addr or "unknown"
        throttle=str(email).strip().lower()
        if _store().auth_throttled("signup",remote,throttle):
            return jsonify({"error":"Too many attempts. Please try again later."}),429
        token=_store().register_account(email,body.get("password",""),body.get("company",""))
        send_token_message(email.strip().lower(),token,"verify")
        return jsonify({"message":"Check your email for a verification link."}),202
    except ValueError as exc:
        # Generic duplicate handling prevents user/email enumeration.
        if "already exists" in str(exc):
            return jsonify({"message":"If eligible, check your email for next steps."}),202
        return jsonify({"error":str(exc)}),400
    except Exception:
        return jsonify({"error":"Registration email service is temporarily unavailable."}),503


@bp.route("/resend-verification",methods=["POST"])
def resend():
    if not _origin_ok():
        return jsonify({"error":"Invalid request origin."}),403
    try:
        body=_body()
        email=body.get("email","")
        remote=request.remote_addr or "unknown"
        if _store().auth_throttled("resend",remote,str(email).lower()):
            return jsonify({"error":"Try again later."}),429
        _store().record_auth_failure("resend",remote,str(email).lower())
        token=_store().issue_verification_token(email)
        if token:
            send_token_message(email.strip().lower(),token,"verify")
    except Exception:
        pass
    return jsonify({"message":"If the account is pending, a link will be sent."}),202


@bp.route("/verify-email",methods=["POST"])
def verify():
    if not _origin_ok():
        return jsonify({"error":"Invalid request origin."}),403
    try:
        body=_body()
        result=_store().verify_email(body.get("token",""))
        if not result:
            return jsonify({"error":"Link invalid, expired or already used."}),400
        return jsonify({"verified":True,"message":"Account verified. Sign in to continue."})
    except ValueError as exc:
        return jsonify({"error":str(exc)}),400


@bp.route("/login",methods=["POST"])
def login():
    if not _origin_ok():
        return jsonify({"error":"Invalid request origin."}),403
    try:
        body=_body()
        email=str(body.get("email","")).strip().lower()
        remote=request.remote_addr or "unknown"
        if _store().auth_throttled("login",remote,email):
            return jsonify({"error":"Too many attempts. Try again later."}),429
        account=_store().authenticate(email,body.get("password",""))
        if not account:
            _store().record_auth_failure("login",remote,email)
            return jsonify({"error":"Invalid credentials or unverified account."}),401
        tenant=_store().owned_tenant(account["user_id"])
        if not tenant:
            return jsonify({"error":"Your organization is not provisioned."}),409
        _store().clear_auth_failures("login",remote,email)
        session.clear()
        session.permanent=True
        session["commercial_user_id"]=account["user_id"]
        session["commercial_tenant_id"]=tenant
        session["commercial_session_version"]=account["session_version"]
        session["commercial_csrf"]=secrets.token_urlsafe(32)
        return jsonify({"signed_in":True,"csrf":session["commercial_csrf"]})
    except ValueError as exc:
        return jsonify({"error":str(exc)}),400


@bp.route("/logout",methods=["POST"])
def logout():
    user,err=_require_account()
    if err:return err
    denied=_require_post()
    if denied:return denied
    session.clear()
    return jsonify({"signed_in":False})


@bp.route("/request-reset",methods=["POST"])
def request_reset():
    if not _origin_ok():
        return jsonify({"error":"Invalid request origin."}),403
    try:
        body=_body()
        email=body.get("email","")
        remote=request.remote_addr or "unknown"
        if _store().auth_throttled("password-reset",remote,str(email).lower()):
            return jsonify({"error":"Try again later."}),429
        _store().record_auth_failure("password-reset",remote,str(email).lower())
        token=_store().issue_reset_token(email)
        if token:
            send_token_message(email.strip().lower(),token,"reset")
    except Exception:
        pass
    return jsonify({"message":"If the account exists, a reset link will be sent."}),202


@bp.route("/reset-password",methods=["POST"])
def reset_password():
    if not _origin_ok():
        return jsonify({"error":"Invalid request origin."}),403
    try:
        body=_body()
        if not _store().reset_password(body.get("token",""),body.get("new_password","")):
            return jsonify({"error":"Reset link invalid or expired."}),400
        session.clear()
        return jsonify({"reset":True})
    except ValueError as exc:
        return jsonify({"error":str(exc)}),400


@bp.route("/provider",methods=["GET"])
def provider_status():
    identity,err=_require_account()
    if err:return err
    uid,tenant=identity
    return jsonify({"provider":"openrouter","connected":bool(_store().get_key(uid,tenant))})


@bp.route("/provider",methods=["POST"])
def provider_connect():
    identity,err=_require_account()
    if err:return err
    denied=_require_post()
    if denied:return denied
    try:
        body=_body(1000)
        key=body.get("api_key")
        verify_openrouter_key(key)
        _store().set_key(identity[0],identity[1],key)
        return jsonify({"provider":"openrouter","connected":True})
    except ValueError as exc:
        return jsonify({"error":str(exc)}),400


@bp.route("/provider",methods=["DELETE"])
def provider_disconnect():
    identity,err=_require_account()
    if err:return err
    denied=_require_post()
    if denied:return denied
    _store().revoke_key(*identity)
    return jsonify({"provider":"openrouter","connected":False})


def _run_commercial_job(store: Store, job_id: str):
    row=store.start_job(job_id)
    if not row:
        return
    uid,tid,document,goal=row
    key=store.get_key(uid,tid)
    if not key:
        store.complete_job(job_id,None)
        return
    try:
        result=review_document(
            document,goal,options={"max_tokens":3600},customer_openrouter_key=key
        )
        # Failures are shown as NON-CONSENSUS, never fake success.
        store.complete_job(job_id,_scrub_secret(result,key))
    except Exception:
        store.complete_job(job_id,None)


@bp.route("/review",methods=["POST"])
def submit_review():
    identity,err=_require_account()
    if err:return err
    denied=_require_post()
    if denied:return denied
    try:
        document,goal=_submitted_document()
        store=_store()
        # Opportunistic deletion augments the dedicated periodic cleaner.
        store.delete_expired_reviews()
        job_id=store.reserve_review(identity[0],identity[1],document,goal)
        _WORKERS.submit(_run_commercial_job,store,job_id)
        return jsonify({"job_id":job_id,"status":"queued"}),202
    except ValueError as exc:
        return jsonify({"error":str(exc)}),400
    except PermissionError as exc:
        return jsonify({"error":str(exc)}),403


@bp.route("/review/<job_id>",methods=["GET"])
def review_status(job_id):
    identity,err=_require_account()
    if err:return err
    value=_store().review_status(identity[0],identity[1],job_id)
    if value is None:
        return jsonify({"error":"No accessible review with that ID."}),404
    return jsonify(value)


@bp.route("/checkout",methods=["POST"])
def checkout():
    identity,err=_require_account()
    if err:return err
    denied=_require_post()
    if denied:return denied
    uid,tenant=identity
    ent=_store().entitlement(tenant)
    if ent and ent.billing_verified and ent.status=="active":
        return jsonify({"error":"An active subscription already exists. Use billing settings."}),409
    email=_store().get_account(uid)["email"]
    try:
        url=StripeGateway.from_environment().checkout(tenant_id=tenant,email=email)
        return jsonify({"checkout_url":url})
    except Exception:
        # Never leak merchant/API responses or card-related information.
        return jsonify({"error":"Checkout is temporarily unavailable."}),503


@bp.route("/billing",methods=["POST"])
def billing_portal():
    identity,err=_require_account()
    if err:return err
    denied=_require_post()
    if denied:return denied
    customer=_store().billing_customer(identity[1])
    if not customer:
        return jsonify({"error":"No verified billing account is linked."}),409
    try:
        url=StripeGateway.from_environment().billing_portal(
            merchant_customer_id=customer)
        return jsonify({"billing_portal_url":url})
    except Exception:
        return jsonify({"error":"Customer billing portal is temporarily unavailable."}),503


@bp.route("/billing-webhook",methods=["POST"])
def signed_billing_webhook():
    # Stripe sends a verified signed event, not an authenticated browser request.
    # This endpoint can never be used to set arbitrary browser-supplied paid=true.
    body=request.get_data(cache=False)
    signature=request.headers.get("Stripe-Signature","")
    try:
        gateway=StripeGateway.from_environment()
        event=gateway.verify_webhook(body,signature)
        outcome=gateway.process_verified_event(event,_store())
        return jsonify({"received":True,"outcome":outcome})
    except CheckoutPending:
        # A verified invoice arrived before checkout linkage. 503 => retry.
        return jsonify({"error":"Merchant event requires retry."}),503
    except ValueError:
        return jsonify({"error":"Invalid merchant event."}),400
    except Exception:
        # No billing secrets or payment body enter logs.
        return jsonify({"error":"Merchant event handling temporarily unavailable."}),503
