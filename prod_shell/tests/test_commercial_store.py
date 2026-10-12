"""Commercial MACIE C persistent store: executable SQLite acceptance fixtures.

Production requires PostgreSQL; this tests identical SQLAlchemy table/transaction
logic without accessing the owner's real data or payment/provider accounts.
"""
from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import select

from prod_shell.src import commercial_store as db


def key(value="A"):
    return "sk-or-v1-" + (value*46)


@pytest.fixture
def store():
    s=db.Store(db.testing_engine(),"fixed-ONLY-FOR-TESTS-do-not-deploy-0123456789ABCDE")
    s.initialize_for_tests_only()
    return s


@pytest.fixture
def buyer(store):
    token=store.register_account(
        " Customer@Test.Example ",
        "This-is-a-long-and-independent-password",
        "HOMEstretch Seller Services",
    )
    assert store.authenticate("customer@test.example","This-is-a-long-and-independent-password") is None
    assert store.verify_email(token,"HOMEstretch Seller Services")
    user=store.get_account_by_email("customer@test.example")
    assert user is not None and user["verified"]
    tenant=store.owned_tenant(user["id"])
    assert tenant
    return user["id"],tenant


def authorize(store,tenant,event_id="evt_first",event_at=None,limit=2):
    return store.apply_verified_billing_event(
        event_id=event_id,event_type="customer.subscription.updated",
        event_at=event_at or int(time.time()),tenant_id=tenant,
        subscription_status="active",customer_id="cus_example",
        subscription_id="sub_example",review_limit=limit,billing_verified=True,
    )


def test_signup_email_verification_and_login_without_founder(store):
    token=store.register_account("new@example.org","Very-long-random-password-2026","Customer LLC")
    assert store.get_account_by_email("new@example.org")["verified"] is False
    assert store.verify_email("invalid-token","Customer LLC") is None
    uid,tid=store.verify_email(token,"Customer LLC")
    assert store.verify_email(token,"Customer LLC") is None
    assert store.authenticate("new@example.org","Wrong-password-0000") is None
    auth=store.authenticate("new@example.org","Very-long-random-password-2026")
    assert auth["user_id"]==uid
    assert store.owned_tenant(uid)==tid
    membership=store.membership(uid,tid)
    assert membership.role=="owner" and membership.active
    entitlement=store.entitlement(tid)
    assert entitlement.status=="inactive"
    assert not entitlement.billing_verified
    assert entitlement.review_limit==0


def test_duplicates_and_weak_passwords_rejected(store):
    store.register_account("customer@example.com","An-excellent-long-password","Customer Business")
    with pytest.raises(ValueError,match="exists"):
        store.register_account("customer@example.com","Different-long-password-222","Business 2")
    with pytest.raises(ValueError,match="password"):
        store.register_account("bad@example.com","weak","Real Firm")
    with pytest.raises(ValueError):
        store.register_account("not email","Verylongpassword-123","Real Firm")


def test_password_reset_revokes_all_old_sessions(store,buyer):
    user,tid=buyer
    email="customer@test.example"
    session=store.authenticate(email,"This-is-a-long-and-independent-password")
    old_version=session["session_version"]
    token=store.issue_reset_token(email)
    assert store.reset_password(token,"New-secure-password-2026-reset")
    assert not store.reset_password(token,"another-password-2026")
    assert store.authenticate(email,"This-is-a-long-and-independent-password") is None
    now=store.authenticate(email,"New-secure-password-2026-reset")
    assert now["session_version"]==old_version+1
    assert store.get_account(user)["verified"]


def test_webhook_idempotency_out_of_order_and_cancel(store,buyer):
    user,tid=buyer
    ts=int(time.time())
    assert authorize(store,tid,event_at=ts)
    assert not authorize(store,tid,event_at=ts)
    assert store.entitlement(tid).status=="active"
    assert store.entitlement(tid).review_limit==2
    assert not store.apply_verified_billing_event(
        event_id="evt_old",event_type="customer.subscription.updated",
        event_at=ts-1,tenant_id=tid,subscription_status="trialing",
        customer_id="cus_example",subscription_id="sub_example",
        review_limit=200,billing_verified=True,
    )
    assert store.entitlement(tid).review_limit==2
    assert store.apply_verified_billing_event(
        event_id="evt_cancel",event_type="customer.subscription.deleted",
        event_at=ts+1,tenant_id=tid,subscription_status="canceled",
        customer_id="cus_example",subscription_id="sub_example",
        review_limit=0,billing_verified=False,
    )
    assert store.entitlement(tid).status=="canceled"
    assert not store.apply_verified_billing_event(
        event_id="evt_stale",event_type="invoice.paid",
        event_at=ts,tenant_id=tid,subscription_status="active",
        customer_id="cus_example",subscription_id="sub_example",
        review_limit=200,billing_verified=True,
    )
    assert store.entitlement(tid).status=="canceled"


def test_unpaid_and_unkeyed_reviews_denied_before_provider_use(store,buyer):
    uid,tid=buyer
    with pytest.raises(PermissionError,match="subscription"):
        store.reserve_review(uid,tid,"Work draft","Improve it")
    authorize(store,tid)
    with pytest.raises(PermissionError,match="provider key"):
        store.reserve_review(uid,tid,"Work draft","Improve it")
    assert store.entitlement(tid).reviews_consumed==0


def test_customer_key_is_encrypted_and_tenant_isolated(store,buyer):
    uid,tid=buyer
    store.set_key(uid,tid,key())
    assert store.get_key(uid,tid)==key()
    with store.engine.connect() as conn:
        ciphertext=conn.execute(
            select(db.provider_keys.c.encrypted)).scalar_one()
    assert key().encode() not in ciphertext
    assert ciphertext.startswith(b"gAAAA")
    assert store.get_key(uid,"tenant-that-does-not-exist") is None
    assert store.get_key("intruder",tid) is None
    assert store.revoke_key(uid,tid)
    assert store.get_key(uid,tid) is None


def test_paid_user_reserves_queued_job_and_reconciles_quota(store,buyer):
    uid,tid=buyer
    authorize(store,tid)
    store.set_key(uid,tid,key())
    job=store.reserve_review(uid,tid,"Existing marketing brochure","Critique and rewrite")
    assert store.entitlement(tid).reviews_consumed==1
    assert store.review_status(uid,tid,job)=={"status":"queued"}
    started=store.start_job(job)
    assert started==(uid,tid,"Existing marketing brochure","Critique and rewrite")
    assert store.start_job(job) is None
    result={"edition":"MACIE C","status":"CONSENSUS","synthesized_review":"Strong, but validate statistics."}
    assert store.complete_job(job,result)
    fetched=store.review_status(uid,tid,job)
    assert fetched["status"]=="finished"
    assert fetched["result"]==result
    assert not store.complete_job(job,result)
    with store.engine.connect() as conn:
        row=conn.execute(select(db.reviews)).mappings().one()
    assert row["encrypted_document"]==b""
    assert row["encrypted_goal"]==b""
    assert b"validate statistics" not in row["encrypted_result"]


def test_quota_is_atomic_and_denies_excess_review(store,buyer):
    uid,tid=buyer
    authorize(store,tid,limit=1)
    store.set_key(uid,tid,key())
    store.reserve_review(uid,tid,"Document A","Review it")
    with pytest.raises(PermissionError,match="quota"):
        store.reserve_review(uid,tid,"Document B","Review it")
    assert store.entitlement(tid).reviews_consumed==1


def test_results_cannot_be_read_across_accounts_or_businesses(store,buyer):
    uid,tid=buyer
    authorize(store,tid)
    store.set_key(uid,tid,key())
    job=store.reserve_review(uid,tid,"Private copy","Improve this copy")
    assert store.review_status("unrelated-user",tid,job) is None
    assert store.review_status(uid,"unrelated-tenant",job) is None
    assert store.review_status(uid,tid,"unknown-job") is None
    second=store.register_account("other@agency.org","Long-secret-password-for-other","Other Agency")
    second_id,second_tid=store.verify_email(second,"Other Agency")
    assert store.review_status(second_id,second_tid,job) is None
    assert store.get_key(second_id,second_tid) is None
    with pytest.raises(PermissionError):
        store.set_key(second_id,tid,key("B"))


def test_failed_job_returns_no_document_or_secret(store,buyer):
    uid,tid=buyer
    authorize(store,tid)
    store.set_key(uid,tid,key())
    job=store.reserve_review(uid,tid,"Sensitive sample","Review")
    assert store.start_job(job)
    assert store.complete_job(job,None)
    assert store.review_status(uid,tid,job)=={"status":"failed"}


def test_encryption_domains_fail_when_crossed(store,buyer):
    uid,tid=buyer
    ciphertext=store._seal(tid,"document","Sensitive buyer-only data")
    from cryptography.fernet import InvalidToken
    with pytest.raises(InvalidToken):
        store._unseal(tid,"goal",ciphertext)
    with pytest.raises(InvalidToken):
        store._unseal("another-tenant","document",ciphertext)


def test_sqlite_is_test_only_and_production_needs_postgres(monkeypatch,store):
    monkeypatch.delenv("MACIE_C_COMMERCIAL_DATABASE_URL",raising=False)
    with pytest.raises(RuntimeError,match="PostgreSQL"):
        db.production_engine()
    from sqlalchemy.exc import OperationalError
    with pytest.raises(OperationalError):
        db.Store(db.testing_engine(),"another-test-secret-0123456789-abcdef").assert_schema()


def test_expired_rejection_and_deletion(store,buyer,monkeypatch):
    uid,tid=buyer
    authorize(store,tid)
    store.set_key(uid,tid,key())
    job=store.reserve_review(uid,tid,"Draft","Review")
    with store.engine.begin() as conn:
        conn.execute(db.update(db.reviews).where(db.reviews.c.id==job).values(expires_at=0))
    assert store.review_status(uid,tid,job) is None
    assert store.delete_expired_reviews()==1
    assert store.start_job(job) is None
