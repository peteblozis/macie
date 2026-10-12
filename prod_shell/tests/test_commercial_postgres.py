"""Integration test real PostgreSQL storage (GitHub Actions service container only).

Never connects to owner's Render database. Requires dedicated temporary
MACIE_C_TEST_POSTGRES_URL supplied by CI. No user data or credentials.
"""
import os

import pytest
from sqlalchemy import text, select

from prod_shell.src import commercial_store as db


@pytest.mark.skipif(
    not os.environ.get("MACIE_C_TEST_POSTGRES_URL"),
    reason="Dedicated Postgres CI service is not configured",
)
def test_real_postgres_commercial_schema_entitlement_byok_and_tenant_access(monkeypatch):
    url=os.environ["MACIE_C_TEST_POSTGRES_URL"]
    assert ("127.0.0.1" in url or "localhost" in url), (
        "Never allow this integration test to modify a remote database."
    )
    monkeypatch.setenv("MACIE_C_COMMERCIAL_DATABASE_URL",url)
    engine=db.production_engine()
    db.META.create_all(engine)
    try:
        store=db.Store(engine,"CI-ONLY-VAULT-MASTER-STRING-DO-NOT-DEPLOY-00001")
        store.assert_schema()
        first=store.register_account(
            "first@example.invalid",
            "A-secure-password-for-first-account",
            "First Local Test Company",
        )
        uid,tid=store.verify_email(first,"First Local Test Company")
        assert store.owned_tenant(uid)==tid
        assert store.get_key(uid,tid) is None
        store.set_key(uid,tid,"sk-or-v1-"+"x"*40)
        assert store.get_key(uid,tid).startswith("sk-or-")
        assert store.entitlement(tid).status=="inactive"
        assert not store.entitlement(tid).billing_verified
        assert store.apply_verified_billing_event(
            event_id="evt_test_1",event_type="customer.subscription.updated",
            event_at=2000000000,tenant_id=tid,subscription_status="active",
            customer_id="cus_ci",subscription_id="sub_ci",
            review_limit=1,billing_verified=True,
        )
        assert store.tenant_for_customer_subscription("cus_ci","sub_ci")==tid
        job=store.reserve_review(uid,tid,"Example untrusted text","Review for errors")
        assert store.start_job(job)
        assert store.complete_job(job,{"status":"CONSENSUS","synthesized_review":"done"})
        assert store.review_status(uid,tid,job)["result"]["synthesized_review"]=="done"
        with pytest.raises(PermissionError):
            store.reserve_review(uid,tid,"Another draft","Review")
        second=store.register_account(
            "second@example.invalid",
            "A-secure-password-for-second-buyer",
            "Second Local Test Company",
        )
        uid2,tid2=store.verify_email(second,"Second Local Test Company")
        assert store.review_status(uid2,tid2,job) is None
        assert store.get_key(uid2,tid2) is None
        with engine.connect() as conn:
            assert conn.execute(select(db.users.c.id)).all()
            assert conn.execute(select(db.reviews.c.id)).all()
    finally:
        db.META.drop_all(engine)
        engine.dispose()
