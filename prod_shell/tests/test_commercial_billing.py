"""Real Stripe signature/entitlement integration test with fake events only.

No Stripe account, credit card, API call or paid service is used in CI.
The official Stripe Webhook signature verifier processes synthetic signed
payloads, followed by real transactional subscription writes.
"""
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest

from prod_shell.src import commercial_store as db
from prod_shell.src.commercial_billing import StripeGateway, CheckoutPending


@pytest.fixture
def billing():
    s=db.Store(db.testing_engine(),"stripe-integration-test-vault-only-abcdef0123456789")
    s.initialize_for_tests_only()
    token=s.register_account("owner@billing.test","Billing-test-password-long-enough","Billing Test Company")
    uid,tid=s.verify_email(token,"Billing Test Company")
    gate=StripeGateway(
        secret_key="sk_test_not-a-real-credential",
        webhook_secret="whsec_dummy-signature-test",
        price_id="price_ci_test_12345",
        site_origin="https://example.invalid",
        review_limit=3,live_mode=False,
    )
    return s,gate,uid,tid


def event(gate, event_id, kind, payload, *, created=None, live=False):
    body=json.dumps({
        "id":event_id,"object":"event","type":kind,"created":created or int(time.time()),
        "livemode":live,"data":{"object":payload},
    },sort_keys=True,separators=(",",":")).encode()
    stamp=int(time.time())
    signed=f"{stamp}.".encode()+body
    mac=hmac.new(gate.webhook_secret.encode(),signed,hashlib.sha256).hexdigest()
    header=f"t={stamp},v1={mac}"
    return body,header


def verify_process(store,gate,ev_id,kind,object_,**opts):
    body,signature=event(gate,ev_id,kind,object_,**opts)
    checked=gate.verify_webhook(body,signature)
    return gate.process_verified_event(checked,store)


def checkout_data(tenant):
    return {
        "id":"cs_ci_session","object":"checkout.session","mode":"subscription",
        "client_reference_id":tenant,"customer":"cus_ci_example",
        "subscription":"sub_ci_example","payment_status":"paid",
    }


def invoice_data():
    return {
        "id":"in_ci_example","object":"invoice","customer":"cus_ci_example",
        "subscription":"sub_ci_example","paid":True,"status":"paid",
    }


def test_checkout_never_activates_until_signed_paid_invoice(billing):
    store,gate,uid,tid=billing
    checkout=verify_process(store,gate,"evt_checkout_1","checkout.session.completed",
                            checkout_data(tid),created=1800000000)
    assert checkout=="checkout_linked"
    assert store.entitlement(tid).status=="incomplete"
    assert not store.entitlement(tid).billing_verified
    assert store.tenant_for_customer_subscription("cus_ci_example","sub_ci_example")==tid
    assert not store._access(uid,tid).allowed
    assert verify_process(store,gate,"evt_paid_1","invoice.paid",
                          invoice_data(),created=1800000010)=="subscription_renewed"
    ent=store.entitlement(tid)
    assert ent.status=="active" and ent.billing_verified
    assert ent.review_limit==3
    assert ent.reviews_consumed==0
    assert store._access(uid,tid).allowed


def test_idempotent_payment_replay_and_cancellation(billing):
    store,gate,uid,tid=billing
    verify_process(store,gate,"evt_co","checkout.session.completed",checkout_data(tid),created=1800000000)
    verify_process(store,gate,"evt_paid","invoice.paid",invoice_data(),created=1800000010)
    assert verify_process(store,gate,"evt_paid","invoice.paid",invoice_data(),
                          created=1800000010)=="duplicate_or_stale"
    sub={"id":"sub_ci_example","customer":"cus_ci_example","status":"canceled",
         "items":{"data":[{"price":{"id":"price_ci_test_12345"}}]}}
    assert verify_process(store,gate,"evt_cancel","customer.subscription.deleted",sub,
                          created=1800000020)=="subscription_updated"
    assert store.entitlement(tid).status=="canceled"
    assert not store._access(uid,tid).allowed
    assert verify_process(store,gate,"evt_stale","invoice.paid",invoice_data(),
                          created=1800000010)=="duplicate_or_stale"
    assert store.entitlement(tid).status=="canceled"


def test_merchant_signature_tampering_is_rejected(billing):
    store,gate,uid,tid=billing
    body,signature=event(gate,"evt_any","checkout.session.completed",checkout_data(tid))
    assert gate.verify_webhook(body,signature)["id"]=="evt_any"
    with pytest.raises(ValueError,match="signature"):
        gate.verify_webhook(body+b" ",signature)
    with pytest.raises(ValueError,match="signature"):
        gate.verify_webhook(body,"")
    live_body,live_sig=event(gate,"evt_live","checkout.session.completed",
                             checkout_data(tid),live=True)
    with pytest.raises(ValueError,match="environment mismatch"):
        gate.verify_webhook(live_body,live_sig)


def test_unmapped_invoice_retried_not_assigned_to_wrong_customer(billing):
    store,gate,uid,tid=billing
    with pytest.raises(CheckoutPending):
        verify_process(store,gate,"evt_first_invoice","invoice.paid",invoice_data())
    assert store.entitlement(tid).status=="inactive"


def test_wrong_price_and_wrong_merchant_account_fail_closed(billing):
    store,gate,uid,tid=billing
    verify_process(store,gate,"evt_co","checkout.session.completed",checkout_data(tid),created=1800000000)
    wrong={"id":"sub_ci_example","customer":"cus_ci_example","status":"active",
           "items":{"data":[{"price":{"id":"price_not-our-product"}}]}}
    with pytest.raises(ValueError,match="price"):
        verify_process(store,gate,"evt_wrong_price","customer.subscription.updated",wrong,created=1800000010)
    assert not store.entitlement(tid).billing_verified
    swapped={**checkout_data(tid),"customer":"cus_another_customer"}
    with pytest.raises(ValueError,match="mismatch"):
        verify_process(store,gate,"evt_wrong_tenant","checkout.session.completed",swapped,created=1800000020)


def test_payment_failure_suspends_new_paid_reviews(billing):
    store,gate,uid,tid=billing
    verify_process(store,gate,"evt_co","checkout.session.completed",checkout_data(tid),created=1800000000)
    verify_process(store,gate,"evt_paid","invoice.paid",invoice_data(),created=1800000010)
    failure={**invoice_data(),"paid":False,"status":"open"}
    outcome=verify_process(store,gate,"evt_failure","invoice.payment_failed",failure,created=1800000020)
    assert outcome=="subscription_past_due"
    assert not store.entitlement(tid).billing_verified
    assert store.entitlement(tid).status=="past_due"
    assert not store._access(uid,tid).allowed


def test_customer_self_checkouts_are_hosted_only_and_not_payment_proof(billing,monkeypatch):
    store,gate,uid,tid=billing
    calls=[]
    class FakeCheckout:
        class Session:
            @staticmethod
            def create(**kwargs):
                calls.append(("checkout",kwargs))
                return {"url":"https://checkout.stripe.com/c/pay/fixture"}
    class FakePortal:
        class Session:
            @staticmethod
            def create(**kwargs):
                calls.append(("portal",kwargs))
                return {"url":"https://billing.stripe.com/fixture"}
    fake=SimpleNamespace(
        checkout=FakeCheckout,billing_portal=FakePortal,
    )
    monkeypatch.setattr(gate,"_sdk",lambda:fake)
    url=gate.checkout(tenant_id=tid,email="owner@billing.test")
    assert url.startswith("https://checkout.stripe.com/")
    assert calls[0][1]["client_reference_id"]==tid
    assert calls[0][1]["line_items"][0]["price"]==gate.price_id
    assert store.entitlement(tid).status=="inactive"
    assert gate.billing_portal(merchant_customer_id="cus_ci_example").startswith(
        "https://billing.stripe.com/"
    )


def test_subscription_status_updates_only_after_earlier_verified_invoice(billing):
    store,gate,uid,tid=billing
    verify_process(store,gate,"evt_co","checkout.session.completed",checkout_data(tid),created=1800000000)
    update={"id":"sub_ci_example","customer":"cus_ci_example","status":"active",
            "items":{"data":[{"price":{"id":"price_ci_test_12345"}}]}}
    verify_process(store,gate,"evt_updated","customer.subscription.updated",update,
                   created=1800000005)
    assert store.entitlement(tid).status=="active"
    assert store.entitlement(tid).billing_verified is False
    assert not store._access(uid,tid).allowed
    verify_process(store,gate,"evt_paid","invoice.paid",invoice_data(),created=1800000010)
    assert store._access(uid,tid).allowed
