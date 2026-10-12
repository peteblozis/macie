"""Provider-neutral boundary; Stripe hosted checkout is one optional adapter.

The app never collects card information. An authenticated customer requests
hosted checkout and self-service billing; only a signature-verified merchant
webhook changes entitlements in MACIE C's durable store.

No merchant account or billing credentials are provisioned here. Commercial
mode remains disabled until an explicit operator-approved price, tax/legal
terms, support route and production test are in place.
"""
from __future__ import annotations

import os
from typing import Any

from prod_shell.src.commercial_store import Store


class CheckoutPending(Exception):
    """Verified event arrived before its checkout mapping; safe to retry."""


class StripeGateway:
    def __init__(self, *, secret_key: str, webhook_secret: str,
                 price_id: str, site_origin: str, review_limit: int,
                 live_mode: bool):
        if not secret_key or not webhook_secret.startswith("whsec_"):
            raise ValueError("Merchant credentials have not been configured.")
        if not price_id.startswith("price_") or not site_origin.startswith("https://"):
            raise ValueError("An approved recurring price and HTTPS site are required.")
        if not isinstance(review_limit,int) or not 1<=review_limit<=100000:
            raise ValueError("Plan review quota must be reviewed and positive.")
        self.secret_key=secret_key
        self.webhook_secret=webhook_secret
        self.price_id=price_id
        self.site_origin=site_origin.rstrip("/")
        self.review_limit=review_limit
        self.live_mode=live_mode

    @classmethod
    def from_environment(cls):
        return cls(
            secret_key=os.environ["MACIE_C_MERCHANT_SECRET_KEY"],
            webhook_secret=os.environ["MACIE_C_MERCHANT_WEBHOOK_SECRET"],
            price_id=os.environ["MACIE_C_MERCHANT_PRICE_ID"],
            site_origin=os.environ["MACIE_C_PUBLIC_ORIGIN"],
            review_limit=int(os.environ["MACIE_C_COMMERCIAL_PLAN_LIMIT"]),
            live_mode=os.environ.get("MACIE_C_MERCHANT_LIVE_MODE")=="1",
        )

    def _sdk(self):
        import stripe
        stripe.api_key=self.secret_key
        return stripe

    def checkout(self, *, tenant_id: str, email: str) -> str:
        stripe=self._sdk()
        session=stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            client_reference_id=tenant_id,
            line_items=[{"price":self.price_id,"quantity":1}],
            metadata={"tenant_id":tenant_id},
            subscription_data={"metadata":{"macie_c_tenant_id":tenant_id}},
            success_url=self.site_origin+"/macie/c/commercial/#checkout=return",
            cancel_url=self.site_origin+"/macie/c/commercial/#checkout=cancel",
            allow_promotion_codes=False,
        )
        url=session.get("url") if isinstance(session,dict) else session.url
        if not isinstance(url,str) or not url.startswith("https://checkout.stripe.com/"):
            raise RuntimeError("No verified secure hosted checkout URL was returned.")
        return url

    def billing_portal(self, *, merchant_customer_id: str) -> str:
        if not merchant_customer_id.startswith("cus_"):
            raise ValueError("No verified merchant customer is linked to this account.")
        stripe=self._sdk()
        portal=stripe.billing_portal.Session.create(
            customer=merchant_customer_id,
            return_url=self.site_origin+"/macie/c/commercial/",
        )
        url=portal.get("url") if isinstance(portal,dict) else portal.url
        if not isinstance(url,str) or not url.startswith("https://billing.stripe.com/"):
            raise RuntimeError("No secure billing portal URL was returned.")
        return url

    def verify_webhook(self, body: bytes, signature: str) -> dict:
        if not signature:
            raise ValueError("Missing merchant webhook signature.")
        if not isinstance(body,bytes) or len(body)>80_000:
            raise ValueError("Invalid merchant webhook size.")
        stripe=self._sdk()
        try:
            event=stripe.Webhook.construct_event(
                body,signature,self.webhook_secret,tolerance=300
            )
        except (ValueError,stripe.error.SignatureVerificationError):
            raise ValueError("Merchant webhook signature invalid.") from None
        # Stripe's signed Event is a StripeObject, NOT a regular dict.
        # Convert nested event data to a normal dictionary before processing.
        verified=event.to_dict_recursive()
        # Test events must not activate a live product, or vice versa.
        if bool(verified.get("livemode"))!=self.live_mode:
            raise ValueError("Merchant event environment mismatch.")
        return verified

    @staticmethod
    def _s(value: Any) -> str:
        """Use IDs, never trust expanded objects or nested browser metadata."""
        return value if isinstance(value,str) else ""

    @staticmethod
    def _invoice_subscription(item: dict) -> str:
        sub=item.get("subscription")
        if isinstance(sub,str):
            return sub
        parent=item.get("parent")
        if isinstance(parent,dict):
            details=parent.get("subscription_details")
            if isinstance(details,dict):
                return StripeGateway._s(details.get("subscription"))
        return ""

    def process_verified_event(self, event: dict, store: Store) -> str:
        """Persist verified events idempotently; all statuses are fail-closed.

        Must be called ONLY on event from verify_webhook(). Browser requests
        cannot call this method through the public API.
        """
        kind=self._s(event.get("type"))
        event_id=self._s(event.get("id"))
        timestamp=event.get("created")
        item=(event.get("data") or {}).get("object")
        if not isinstance(item,dict) or not event_id:
            raise ValueError("Invalid merchant event payload.")
        if not isinstance(timestamp,int):
            raise ValueError("Invalid merchant event timestamp.")
        if kind=="checkout.session.completed":
            if item.get("mode")!="subscription":
                return "ignored_non_subscription_checkout"
            tenant=self._s(item.get("client_reference_id"))
            customer=self._s(item.get("customer"))
            subscription=self._s(item.get("subscription"))
            if not (tenant and customer.startswith("cus_") and subscription.startswith("sub_")):
                raise ValueError("Checkout is missing verified subscription mapping.")
            # Checkout alone never proves an active paid subscription.
            applied=store.apply_verified_billing_event(
                event_id=event_id,event_type=kind,event_at=timestamp,
                tenant_id=tenant,subscription_status="incomplete",
                customer_id=customer,subscription_id=subscription,
                review_limit=self.review_limit,billing_verified=False,
            )
            return "checkout_linked" if applied else "duplicate_or_stale"

        if kind in ("invoice.paid","invoice.payment_failed"):
            customer=self._s(item.get("customer"))
            subscription=self._invoice_subscription(item)
            tenant=store.tenant_for_customer_subscription(customer,subscription)
            if not tenant:
                # Merchant will retry this webhook. Never guess a tenant.
                raise CheckoutPending("Payment event preceded verified checkout mapping.")
            verified_payment=(
                kind=="invoice.paid"
                and item.get("paid") is True
                and item.get("status")=="paid"
            )
            status="active" if verified_payment else "past_due"
            applied=store.apply_verified_billing_event(
                event_id=event_id,event_type=kind,event_at=timestamp,
                tenant_id=tenant,subscription_status=status,
                customer_id=customer,subscription_id=subscription,
                review_limit=self.review_limit,
                billing_verified=verified_payment,
                reset_usage=verified_payment,
            )
            return "subscription_renewed" if applied and verified_payment else (
                "subscription_past_due" if applied else "duplicate_or_stale"
            )

        if kind in ("customer.subscription.created","customer.subscription.updated",
                    "customer.subscription.deleted"):
            subscription=self._s(item.get("id"))
            customer=self._s(item.get("customer"))
            tenant=store.tenant_for_customer_subscription(customer,subscription)
            if not tenant:
                raise CheckoutPending("Subscription event preceded checkout mapping.")
            prices=[]
            for line in ((item.get("items") or {}).get("data") or []):
                price=line.get("price") or {}
                prices.append(price.get("id") if isinstance(price,dict) else None)
            if prices and self.price_id not in prices:
                raise ValueError("Unexpected subscription price.")
            status=self._s(item.get("status"))
            if kind=="customer.subscription.deleted":
                status="canceled"
            entitlement=store.entitlement(tenant)
            prior_verified=bool(entitlement and entitlement.billing_verified)
            active=status in ("active","trialing")
            applied=store.apply_verified_billing_event(
                event_id=event_id,event_type=kind,event_at=timestamp,
                tenant_id=tenant,subscription_status=status,
                customer_id=customer,subscription_id=subscription,
                review_limit=self.review_limit,
                billing_verified=active and prior_verified,
            )
            return "subscription_updated" if applied else "duplicate_or_stale"
        return "ignored"
