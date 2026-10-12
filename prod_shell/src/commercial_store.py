"""MACIE C commercial tenant store — persistent, isolated, customer-owned.

This module does NOT expose an HTTP endpoint and never enables sales by
itself. Commercial activation requires a Render Postgres database, verified
identity/email delivery, a real merchant processor and signed webhooks.

SQLite is allowed *only* in isolated acceptance tests. Production requires
Postgres. All customer documents, results and provider credentials are
Fernet-encrypted with purpose/tenant-separated derived keys. The master
key must be provisioned in protected runtime configuration, never in code.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import (
    Boolean, Column, ForeignKey, Index, Integer, LargeBinary, MetaData,
    String, Table, Text, create_engine, delete, insert, select, update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from prod_shell.src.commercial_access import (
    Membership, TenantEntitlement, VerifiedIdentity, may_read_review_result,
    may_run_review,
)

META = MetaData()
users = Table("c_users", META,
    Column("id", String(36), primary_key=True),
    Column("email", String(320), unique=True, nullable=False),
    Column("pending_org_name", String(160), nullable=False),
    Column("password_hash", String(200), nullable=False),
    Column("verified", Boolean, nullable=False, default=False),
    Column("session_version", Integer, nullable=False, default=0),
    Column("created_at", Integer, nullable=False),
)
email_tokens = Table("c_email_tokens", META,
    Column("digest", String(64), primary_key=True),
    Column("user_id", String(36), ForeignKey("c_users.id"), nullable=False),
    Column("purpose", String(24), nullable=False),
    Column("expires_at", Integer, nullable=False),
    Column("used", Boolean, nullable=False, default=False),
)
tenants = Table("c_tenants", META,
    Column("id", String(36), primary_key=True),
    Column("name", String(160), nullable=False),
    Column("created_at", Integer, nullable=False),
)
memberships = Table("c_memberships", META,
    Column("user_id", String(36), ForeignKey("c_users.id"), primary_key=True),
    Column("tenant_id", String(36), ForeignKey("c_tenants.id"), primary_key=True),
    Column("role", String(24), nullable=False),
    Column("active", Boolean, nullable=False),
)
subscriptions = Table("c_subscriptions", META,
    Column("tenant_id", String(36), ForeignKey("c_tenants.id"), primary_key=True),
    Column("merchant_customer_id", String(130), nullable=True, unique=True),
    Column("merchant_subscription_id", String(130), nullable=True, unique=True),
    Column("status", String(32), nullable=False),
    Column("billing_verified", Boolean, nullable=False),
    Column("review_limit", Integer, nullable=False, default=0),
    Column("reviews_consumed", Integer, nullable=False, default=0),
    Column("last_billing_event_at", Integer, nullable=False, default=0),
    Column("suspended", Boolean, nullable=False, default=False),
)
provider_keys = Table("c_provider_keys", META,
    Column("tenant_id", String(36), ForeignKey("c_tenants.id"), primary_key=True),
    Column("user_id", String(36), ForeignKey("c_users.id"), primary_key=True),
    Column("provider", String(24), nullable=False),
    Column("encrypted", LargeBinary, nullable=False),
    Column("rotated_at", Integer, nullable=False),
)
reviews = Table("c_reviews", META,
    Column("id", String(36), primary_key=True),
    Column("tenant_id", String(36), ForeignKey("c_tenants.id"), nullable=False),
    Column("user_id", String(36), ForeignKey("c_users.id"), nullable=False),
    Column("state", String(24), nullable=False),
    Column("encrypted_document", LargeBinary, nullable=False),
    Column("encrypted_goal", LargeBinary, nullable=False),
    Column("encrypted_result", LargeBinary, nullable=True),
    Column("created_at", Integer, nullable=False),
    Column("expires_at", Integer, nullable=False),
)
Index("c_reviews_tenant_user_ix", reviews.c.tenant_id, reviews.c.user_id)
auth_throttles = Table("c_auth_throttles", META,
    Column("key", String(64), primary_key=True),
    Column("failures", Integer, nullable=False),
    Column("expires_at", Integer, nullable=False),
)
billing_events = Table("c_billing_events", META,
    Column("event_id", String(160), primary_key=True),
    Column("event_at", Integer, nullable=False),
    Column("event_type", String(100), nullable=False),
)
# Customer metadata is never placed in app-level logs.


def testing_engine() -> Engine:
    """Ephemeral and cross-thread compatible SQLite ONLY for automated tests."""
    return create_engine(
        "sqlite+pysqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )


def production_engine() -> Engine:
    url = os.environ.get("MACIE_C_COMMERCIAL_DATABASE_URL", "")
    if not (url.startswith("postgresql+psycopg://") or url.startswith("postgresql://")):
        raise RuntimeError("Commercial MACIE C requires a configured PostgreSQL database.")
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, future=True)


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> int:
    return int(time.time())


def _normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("A valid email address is required.")
    clean = email.strip().lower()
    if len(clean) > 320 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean):
        raise ValueError("A valid email address is required.")
    return clean


def _hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 14 or len(password) > 200:
        raise ValueError("Use a password between 14 and 200 characters.")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 330000)
    return f"pbkdf2_sha256$330000${salt.hex()}${dk.hex()}"


def _verify_password(password: str, record: str) -> bool:
    try:
        scheme, rounds, salt, digest = record.split("$")
        if scheme != "pbkdf2_sha256" or not 260000 <= int(rounds) <= 1000000:
            return False
        supplied = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                       bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(supplied, bytes.fromhex(digest))
    except (ValueError, TypeError, UnicodeError):
        return False


class Store:
    """Persistent store. Only server-trusted code may call billing setters."""

    def __init__(self, engine: Engine, master_secret: str):
        if not isinstance(master_secret, str) or len(master_secret) < 40:
            raise ValueError("Use a high-entropy 40+ character vault secret.")
        self.engine = engine
        self._master = master_secret.encode("utf-8")

    def initialize_for_tests_only(self) -> None:
        if self.engine.dialect.name != "sqlite":
            raise RuntimeError("Use a reviewed migration for production Postgres.")
        META.create_all(self.engine)

    def assert_schema(self) -> None:
        # This reads an existing table; never silently bootstraps a prod DB.
        with self.engine.connect() as db:
            db.execute(select(users.c.id).limit(1)).all()

    def _cipher(self, tenant_id: str, purpose: str) -> Fernet:
        # Separate cryptographic domain per tenant and type of record.
        digest = hmac.new(
            self._master, f"macie-c-v1:{purpose}:{tenant_id}".encode(),
            hashlib.sha256,
        ).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _seal(self, tenant_id: str, purpose: str, value: str) -> bytes:
        return self._cipher(tenant_id, purpose).encrypt(value.encode())

    def _unseal(self, tenant_id: str, purpose: str, value: bytes) -> str:
        return self._cipher(tenant_id, purpose).decrypt(value).decode()

    def auth_throttled(self, scope: str, remote: str, identity: str) -> bool:
        digest=hashlib.sha256(f"{scope}:{remote}:{identity}".encode()).hexdigest()
        with self.engine.connect() as db:
            row=db.execute(select(auth_throttles).where(
                auth_throttles.c.key==digest
            )).mappings().first()
        return bool(row and row["expires_at"]>_now() and row["failures"]>=6)

    def record_auth_failure(self, scope: str, remote: str, identity: str) -> None:
        digest=hashlib.sha256(f"{scope}:{remote}:{identity}".encode()).hexdigest()
        with self.engine.begin() as db:
            row=db.execute(select(auth_throttles).where(
                auth_throttles.c.key==digest
            )).mappings().first()
            count=(row["failures"]+1) if row and row["expires_at"]>_now() else 1
            db.execute(delete(auth_throttles).where(auth_throttles.c.key==digest))
            db.execute(insert(auth_throttles).values(
                key=digest,failures=count,expires_at=_now()+900
            ))

    def clear_auth_failures(self, scope: str, remote: str, identity: str) -> None:
        digest=hashlib.sha256(f"{scope}:{remote}:{identity}".encode()).hexdigest()
        with self.engine.begin() as db:
            db.execute(delete(auth_throttles).where(auth_throttles.c.key==digest))

    def register_account(self, email: str, password: str, company: str) -> str:
        email = _normalize_email(email)
        if not isinstance(company, str) or not 2 <= len(company.strip()) <= 160:
            raise ValueError("Organization name must contain 2–160 characters.")
        pw_hash = _hash_password(password)
        uid = _id()
        with self.engine.begin() as db:
            existing = db.execute(select(users.c.id).where(users.c.email == email)).first()
            if existing:
                raise ValueError("Account already exists or registration is pending.")
            db.execute(insert(users).values(
                id=uid, email=email, pending_org_name=company.strip(), password_hash=pw_hash,
                verified=False, session_version=0, created_at=_now(),
            ))
            # The organization is provisioned only AFTER email verification,
            # and a subscription entitlement only after signed billing events.
            token = secrets.token_urlsafe(36)
            db.execute(insert(email_tokens).values(
                digest=hashlib.sha256(token.encode()).hexdigest(),
                user_id=uid, purpose="verify", expires_at=_now()+3600, used=False,
            ))
            # The requested organization name is bound to this unverified
            # account; tenant/entitlement created only after verification.
        return token

    def issue_verification_token(self, email: str) -> str | None:
        """Self-service retry when delivery failed; only unverified accounts."""
        account=self.get_account_by_email(email)
        if not account or account["verified"]:
            return None
        token=secrets.token_urlsafe(36)
        with self.engine.begin() as db:
            db.execute(insert(email_tokens).values(
                digest=hashlib.sha256(token.encode()).hexdigest(),
                user_id=account["id"],purpose="verify",
                expires_at=_now()+3600,used=False,
            ))
        return token

    def verify_email(self, token: str, company: str | None = None) -> tuple[str, str] | None:
        if not isinstance(token, str) or len(token) > 200:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.begin() as db:
            row = db.execute(select(email_tokens).where(
                email_tokens.c.digest == digest,
                email_tokens.c.purpose == "verify",
                email_tokens.c.used.is_(False),
                email_tokens.c.expires_at >= _now(),
            )).mappings().first()
            if row is None:
                return None
            updated = db.execute(update(email_tokens).where(
                email_tokens.c.digest == digest,
                email_tokens.c.used.is_(False),
            ).values(used=True))
            if updated.rowcount != 1:
                return None
            uid = row["user_id"]
            account = db.execute(select(users).where(users.c.id == uid)).mappings().one()
            # Registration binds the organization name; verification cannot
            # rename a tenant by changing an untrusted browser form field.
            if company is not None and company.strip() != account["pending_org_name"]:
                raise ValueError("Organization name did not match registration.")
            tid = _id()
            db.execute(update(users).where(users.c.id == uid).values(verified=True))
            db.execute(insert(tenants).values(id=tid,name=account["pending_org_name"],created_at=_now()))
            db.execute(insert(memberships).values(user_id=uid,tenant_id=tid,role="owner",active=True))
            db.execute(insert(subscriptions).values(
                tenant_id=tid,status="inactive",billing_verified=False,
                reviews_consumed=0,review_limit=0,last_billing_event_at=0,suspended=False,
            ))
            return uid, tid

    def get_account(self, user_id: str) -> dict | None:
        with self.engine.connect() as db:
            row = db.execute(select(users).where(users.c.id == user_id)).mappings().first()
            return dict(row) if row else None

    def get_account_by_email(self, email: str) -> dict | None:
        try:
            email = _normalize_email(email)
        except ValueError:
            return None
        with self.engine.connect() as db:
            row = db.execute(select(users).where(users.c.email == email)).mappings().first()
            return dict(row) if row else None

    def authenticate(self, email: str, password: str) -> dict | None:
        account = self.get_account_by_email(email)
        if not account or not account["verified"]:
            # Work is bounded to avoid user enumeration and hidden unverified login.
            return None
        if not isinstance(password,str) or not _verify_password(password,account["password_hash"]):
            return None
        return {
            "user_id": account["id"],
            "session_version": account["session_version"],
            "email": account["email"],
        }

    def issue_reset_token(self, email: str) -> str | None:
        account = self.get_account_by_email(email)
        if not account or not account["verified"]:
            return None
        token = secrets.token_urlsafe(36)
        with self.engine.begin() as db:
            db.execute(insert(email_tokens).values(
                digest=hashlib.sha256(token.encode()).hexdigest(),
                user_id=account["id"],purpose="reset",
                expires_at=_now()+1800,used=False,
            ))
        return token

    def reset_password(self, token: str, new_password: str) -> bool:
        if not isinstance(token,str) or len(token)>200:
            return False
        hashed = _hash_password(new_password)
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.engine.begin() as db:
            row=db.execute(select(email_tokens).where(
                email_tokens.c.digest==digest,
                email_tokens.c.purpose=="reset",
                email_tokens.c.used.is_(False),
                email_tokens.c.expires_at>=_now(),
            )).mappings().first()
            if not row:
                return False
            check=db.execute(update(email_tokens).where(
                email_tokens.c.digest==digest,
                email_tokens.c.used.is_(False),
            ).values(used=True))
            if check.rowcount!=1:
                return False
            db.execute(update(users).where(users.c.id==row["user_id"]).values(
                password_hash=hashed,
                session_version=users.c.session_version+1,
            ))
            return True

    def owned_tenant(self, user_id: str) -> str | None:
        with self.engine.connect() as db:
            return db.execute(select(memberships.c.tenant_id).where(
                memberships.c.user_id==user_id,
                memberships.c.active.is_(True),
                memberships.c.role=="owner",
            )).scalar_one_or_none()

    def membership(self, user_id: str, tenant_id: str) -> Membership | None:
        with self.engine.connect() as db:
            row=db.execute(select(memberships).where(
                memberships.c.user_id==user_id,
                memberships.c.tenant_id==tenant_id,
            )).mappings().first()
        return Membership(user_id=row["user_id"],tenant_id=row["tenant_id"],
                          role=row["role"],active=row["active"]) if row else None

    def entitlement(self, tenant_id: str) -> TenantEntitlement | None:
        with self.engine.connect() as db:
            row=db.execute(select(subscriptions).where(
                subscriptions.c.tenant_id==tenant_id,
            )).mappings().first()
        return TenantEntitlement(
            tenant_id=row["tenant_id"],
            status=row["status"],
            billing_verified=row["billing_verified"],
            review_limit=row["review_limit"],
            reviews_consumed=row["reviews_consumed"],
            suspended=row["suspended"],
        ) if row else None

    def _access(self, user_id: str, tenant_id: str):
        account=self.get_account(user_id)
        identity=(VerifiedIdentity(user_id, bool(account and account["verified"]))
                  if account else None)
        return may_run_review(
            identity,self.membership(user_id,tenant_id),
            self.entitlement(tenant_id),tenant_id,
        )

    def apply_verified_billing_event(
        self, *, event_id: str, event_type: str, event_at: int,
        tenant_id: str, subscription_status: str, customer_id: str,
        subscription_id: str, review_limit: int, billing_verified: bool,
    ) -> bool:
        """Caller MUST verify gateway signature first. Idempotent and ordered.

        A missing tenant fails closed. A canceled/outdated event must not
        reactivate a newer subscription. Signed but replayed events are no-ops.
        """
        if not all((event_id,event_type,tenant_id,customer_id,subscription_id)):
            raise ValueError("Incomplete verified billing event.")
        if not isinstance(event_at,int) or not 0 < event_at < 2**40:
            raise ValueError("Invalid billing timestamp.")
        if not isinstance(review_limit,int) or isinstance(review_limit,bool) or review_limit<0:
            raise ValueError("Invalid plan quota.")
        with self.engine.begin() as db:
            existed=db.execute(select(billing_events.c.event_id).where(
                billing_events.c.event_id==event_id)).first()
            if existed:
                return False
            current=db.execute(select(subscriptions).where(
                subscriptions.c.tenant_id==tenant_id,
            )).mappings().first()
            if not current:
                raise ValueError("Unknown tenant; subscription cannot be activated.")
            if current["merchant_customer_id"] not in (None, customer_id):
                raise ValueError("Customer/tenant billing mismatch.")
            if current["merchant_subscription_id"] not in (None, subscription_id):
                raise ValueError("Subscription/tenant billing mismatch.")
            if event_at < current["last_billing_event_at"]:
                db.execute(insert(billing_events).values(
                    event_id=event_id,event_type=event_type,event_at=event_at))
                return False
            db.execute(update(subscriptions).where(
                subscriptions.c.tenant_id==tenant_id,
            ).values(
                merchant_customer_id=customer_id,
                merchant_subscription_id=subscription_id,
                status=subscription_status,
                billing_verified=billing_verified,
                review_limit=review_limit,
                last_billing_event_at=event_at,
            ))
            db.execute(insert(billing_events).values(
                event_id=event_id,event_type=event_type,event_at=event_at))
            return True

    def tenant_for_customer_subscription(self, customer_id: str, subscription_id: str) -> str | None:
        if not customer_id or not subscription_id:
            return None
        with self.engine.connect() as db:
            return db.execute(select(subscriptions.c.tenant_id).where(
                subscriptions.c.merchant_customer_id==customer_id,
                subscriptions.c.merchant_subscription_id==subscription_id,
            )).scalar_one_or_none()

    def set_key(self, user_id: str, tenant_id: str, key: str) -> None:
        from prod_shell.src.customer_openrouter_keys import _validate_shape
        _validate_shape(key)
        member=self.membership(user_id,tenant_id)
        if not member or not member.active:
            raise PermissionError("Account is not a member of this organization.")
        encrypted=self._seal(tenant_id,"provider:"+user_id,key)
        with self.engine.begin() as db:
            db.execute(delete(provider_keys).where(
                provider_keys.c.tenant_id==tenant_id,
                provider_keys.c.user_id==user_id))
            db.execute(insert(provider_keys).values(
                user_id=user_id,tenant_id=tenant_id,provider="openrouter",
                encrypted=encrypted,rotated_at=_now()))

    def get_key(self, user_id: str, tenant_id: str) -> str | None:
        member=self.membership(user_id,tenant_id)
        if not member or not member.active:
            return None
        with self.engine.connect() as db:
            encrypted=db.execute(select(provider_keys.c.encrypted).where(
                provider_keys.c.tenant_id==tenant_id,
                provider_keys.c.user_id==user_id)).scalar_one_or_none()
        if encrypted is None:
            return None
        try:
            return self._unseal(tenant_id,"provider:"+user_id,encrypted)
        except (InvalidToken,UnicodeDecodeError):
            return None

    def revoke_key(self, user_id: str, tenant_id: str) -> bool:
        member=self.membership(user_id,tenant_id)
        if not member or not member.active:
            return False
        with self.engine.begin() as db:
            result=db.execute(delete(provider_keys).where(
                provider_keys.c.tenant_id==tenant_id,
                provider_keys.c.user_id==user_id))
            return result.rowcount > 0

    def reserve_review(self,user_id: str,tenant_id: str,document: str,goal: str) -> str:
        """Atomically reserve one billable attempt only if entitled and keyed.

        Commercial checkout does NOT automatically guarantee AI provider credits;
        customer can still receive a provider-side failed payment/credits error.
        """
        if not isinstance(document,str) or not 0<len(document)<=50000:
            raise ValueError("Review text must be 1–50,000 characters.")
        if not isinstance(goal,str) or not 0<len(goal)<=2000:
            raise ValueError("Review goal must be 1–2,000 characters.")
        decision=self._access(user_id,tenant_id)
        if not decision.allowed:
            raise PermissionError("Review denied: "+decision.code.value)
        if not self.get_key(user_id,tenant_id):
            raise PermissionError("Connect your own AI provider key.")
        job_id=_id()
        with self.engine.begin() as db:
            quota=db.execute(update(subscriptions).where(
                subscriptions.c.tenant_id==tenant_id,
                subscriptions.c.status.in_(["active","trialing"]),
                subscriptions.c.billing_verified.is_(True),
                subscriptions.c.suspended.is_(False),
                subscriptions.c.reviews_consumed < subscriptions.c.review_limit,
            ).values(reviews_consumed=subscriptions.c.reviews_consumed+1))
            if quota.rowcount!=1:
                raise PermissionError("Subscription quota is no longer available.")
            db.execute(insert(reviews).values(
                id=job_id,tenant_id=tenant_id,user_id=user_id,
                state="queued",encrypted_document=self._seal(tenant_id,"document",document),
                encrypted_goal=self._seal(tenant_id,"goal",goal),
                encrypted_result=None,created_at=_now(),
                expires_at=_now()+1800,
            ))
        return job_id

    def start_job(self,job_id: str) -> tuple[str,str,str,str] | None:
        """Worker claims a queued job atomically, with no cross-tenant leak."""
        with self.engine.begin() as db:
            updated=db.execute(update(reviews).where(
                reviews.c.id==job_id,
                reviews.c.state=="queued",
                reviews.c.expires_at>_now(),
            ).values(state="running"))
            if updated.rowcount!=1:
                return None
            row=db.execute(select(reviews).where(reviews.c.id==job_id)).mappings().one()
        tenant=row["tenant_id"]
        return (
            row["user_id"],tenant,
            self._unseal(tenant,"document",row["encrypted_document"]),
            self._unseal(tenant,"goal",row["encrypted_goal"]),
        )

    def complete_job(self,job_id: str,result: dict[str,Any]|None) -> bool:
        """Worker writes result; never expose provider key in payload."""
        with self.engine.begin() as db:
            row=db.execute(select(reviews.c.tenant_id).where(
                reviews.c.id==job_id,reviews.c.state=="running")).first()
            if not row:
                return False
            tenant=row.tenant_id
            data=self._seal(tenant,"result",json.dumps(result,ensure_ascii=False)) if result is not None else None
            done=db.execute(update(reviews).where(
                reviews.c.id==job_id,reviews.c.state=="running",
            ).values(state="finished" if result is not None else "failed",
                     encrypted_result=data,
                     encrypted_document=b"",encrypted_goal=b""))
            return done.rowcount==1

    def review_status(self,user_id: str,tenant_id: str,job_id: str) -> dict | None:
        member=self.membership(user_id,tenant_id)
        if not member:
            return None
        with self.engine.connect() as db:
            row=db.execute(select(reviews).where(
                reviews.c.id==job_id,
                reviews.c.tenant_id==tenant_id,
                reviews.c.user_id==user_id,
                reviews.c.expires_at>_now(),
            )).mappings().first()
        if not row or not may_read_review_result(
            VerifiedIdentity(user_id,True),member,row["tenant_id"],row["user_id"]
        ):
            return None
        response={"status":row["state"]}
        if row["state"]=="finished" and row["encrypted_result"]:
            try:
                response["result"]=json.loads(self._unseal(
                    tenant_id,"result",row["encrypted_result"]))
            except (InvalidToken,UnicodeDecodeError,ValueError):
                return {"status":"failed"}
        return response

    def delete_expired_reviews(self) -> int:
        with self.engine.begin() as db:
            r=db.execute(delete(reviews).where(reviews.c.expires_at<=_now()))
            return r.rowcount
