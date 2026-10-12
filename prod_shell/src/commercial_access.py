"""Commercial MACIE C tenant/entitlement policy — no owner-mediated usage.

This is a *pure decision layer*, deliberately independent of any particular
identity provider, payment gateway, or database. Only verified server-side
identity, membership, and billing events may be used to construct its inputs.

Not wired to the current invitation-only prototype. The commercial launcher
must first provide durable multi-tenant storage, verified checkout webhooks,
and automatic identity/tenant provisioning.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Code(str, Enum):
    ALLOW = "allow"
    SIGN_IN_REQUIRED = "sign_in_required"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    ACCOUNT_SUSPENDED = "account_suspended"
    NOT_A_MEMBER = "not_a_member"
    MEMBERSHIP_INACTIVE = "membership_inactive"
    SUBSCRIPTION_NOT_ACTIVE = "subscription_not_active"
    PAYMENT_NOT_VERIFIED = "payment_not_verified"
    QUOTA_EXCEEDED = "quota_exceeded"
    TENANT_NOT_FOUND = "tenant_not_found"
    INVALID_ENTITLEMENT = "invalid_entitlement"


@dataclass(frozen=True)
class VerifiedIdentity:
    """Identity assertion received from the server-verified identity adapter."""
    user_id: str
    verified_email: bool


@dataclass(frozen=True)
class Membership:
    """User membership resolved against the durable tenant membership store."""
    user_id: str
    tenant_id: str
    active: bool = True
    role: str = "member"


@dataclass(frozen=True)
class TenantEntitlement:
    """Billing/usage snapshot, derived from verified provider webhooks.

    The business plan controls the actual quota; no unlimited free access.
    """
    tenant_id: str
    status: str  # active, trialing, past_due, canceled, unpaid, ...
    billing_verified: bool
    review_limit: int
    reviews_consumed: int
    suspended: bool = False


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    code: Code


def may_run_review(
    identity: VerifiedIdentity | None,
    membership: Membership | None,
    entitlement: TenantEntitlement | None,
    requested_tenant_id: str,
) -> AccessDecision:
    """Fail closed when identity, membership, or subscription is unknown.

    Invoked before billing any AI tokens or accepting customer documents.
    Each request must resolve identity + tenant from server-side records;
    never accept a tenant ID or subscription status as authoritative input
    simply because it came in the browser request.
    """
    def deny(code: Code) -> AccessDecision:
        return AccessDecision(False, code)
    if not identity or not identity.user_id.strip():
        return deny(Code.SIGN_IN_REQUIRED)
    if not identity.verified_email:
        return deny(Code.EMAIL_NOT_VERIFIED)
    if not requested_tenant_id or not membership:
        return deny(Code.NOT_A_MEMBER)
    if membership.user_id != identity.user_id or membership.tenant_id != requested_tenant_id:
        return deny(Code.NOT_A_MEMBER)
    if not membership.active:
        return deny(Code.MEMBERSHIP_INACTIVE)
    if not entitlement or entitlement.tenant_id != requested_tenant_id:
        return deny(Code.TENANT_NOT_FOUND)
    if entitlement.suspended:
        return deny(Code.ACCOUNT_SUSPENDED)
    if entitlement.status not in {"active", "trialing"}:
        return deny(Code.SUBSCRIPTION_NOT_ACTIVE)
    if not entitlement.billing_verified:
        return deny(Code.PAYMENT_NOT_VERIFIED)
    if (
        not isinstance(entitlement.review_limit, int)
        or isinstance(entitlement.review_limit, bool)
        or not isinstance(entitlement.reviews_consumed, int)
        or isinstance(entitlement.reviews_consumed, bool)
        or entitlement.review_limit < 1
        or entitlement.reviews_consumed < 0
    ):
        return deny(Code.INVALID_ENTITLEMENT)
    if entitlement.reviews_consumed >= entitlement.review_limit:
        return deny(Code.QUOTA_EXCEEDED)
    return AccessDecision(True, Code.ALLOW)


def may_read_review_result(
    identity: VerifiedIdentity | None,
    membership: Membership | None,
    job_tenant_id: str,
    job_owner_id: str,
) -> bool:
    """Only the verified creating user within that same tenant sees a result.

    Enterprise organization sharing is a future explicit opt-in, not a
    default across users or across businesses.
    """
    return bool(
        identity and identity.user_id and identity.verified_email
        and membership and membership.active
        and membership.user_id == identity.user_id
        and membership.tenant_id == job_tenant_id
        and identity.user_id == job_owner_id
    )
