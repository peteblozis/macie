"""MACIE C commercial policy acceptance tests.

These are pure policy tests, not proof of live signup, billing, or database.
"""
import dataclasses
import pytest

from prod_shell.src.commercial_access import (
    Code,
    Membership,
    TenantEntitlement,
    VerifiedIdentity,
    may_read_review_result,
    may_run_review,
)

IDENTITY = VerifiedIdentity(user_id="user-1", verified_email=True)
MEMBER = Membership(user_id="user-1", tenant_id="org-1")
ENTITLEMENT = TenantEntitlement(
    tenant_id="org-1", status="active", billing_verified=True,
    review_limit=25, reviews_consumed=5,
)


def decide(identity=IDENTITY, membership=MEMBER, entitlement=ENTITLEMENT, tenant_id="org-1"):
    return may_run_review(identity, membership, entitlement, tenant_id)


def test_paid_customer_can_submit_without_founder_involvement():
    result = decide()
    assert result.allowed and result.code is Code.ALLOW


@pytest.mark.parametrize("changes,expected", [
    ({"identity": None}, Code.SIGN_IN_REQUIRED),
    ({"identity": VerifiedIdentity("user-1", False)}, Code.EMAIL_NOT_VERIFIED),
    ({"membership": None}, Code.NOT_A_MEMBER),
    ({"membership": Membership("user-2", "org-1")}, Code.NOT_A_MEMBER),
    ({"membership": Membership("user-1", "org-2")}, Code.NOT_A_MEMBER),
    ({"membership": Membership("user-1", "org-1", active=False)}, Code.MEMBERSHIP_INACTIVE),
    ({"entitlement": None}, Code.TENANT_NOT_FOUND),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, tenant_id="org-2")}, Code.TENANT_NOT_FOUND),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, status="canceled")}, Code.SUBSCRIPTION_NOT_ACTIVE),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, status="past_due")}, Code.SUBSCRIPTION_NOT_ACTIVE),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, billing_verified=False)}, Code.PAYMENT_NOT_VERIFIED),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, suspended=True)}, Code.ACCOUNT_SUSPENDED),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, reviews_consumed=25)}, Code.QUOTA_EXCEEDED),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, review_limit=0)}, Code.INVALID_ENTITLEMENT),
    ({"entitlement": dataclasses.replace(ENTITLEMENT, reviews_consumed=-1)}, Code.INVALID_ENTITLEMENT),
])
def test_denies_unauthorized_or_unpaid_without_provider_calls(changes, expected):
    result = decide(**changes)
    assert result.allowed is False
    assert result.code is expected


def test_trial_is_allowed_only_when_verified_and_within_limits():
    entitlement = dataclasses.replace(ENTITLEMENT, status="trialing", reviews_consumed=24)
    assert decide(entitlement=entitlement).allowed
    assert decide(entitlement=dataclasses.replace(entitlement, reviews_consumed=25)).code is Code.QUOTA_EXCEEDED


def test_cross_tenant_document_access_is_denied_even_when_member_pays():
    assert may_read_review_result(IDENTITY, MEMBER, "org-1", "user-1")
    assert not may_read_review_result(IDENTITY, MEMBER, "org-2", "user-1")
    assert not may_read_review_result(IDENTITY, MEMBER, "org-1", "user-2")
    assert not may_read_review_result(VerifiedIdentity("user-2", True), MEMBER, "org-1", "user-1")
    assert not may_read_review_result(VerifiedIdentity("user-1", False), MEMBER, "org-1", "user-1")


def test_browser_cannot_choose_different_organization_by_request_parameter():
    assert decide(tenant_id="org-2").code is Code.NOT_A_MEMBER


def test_invalid_entitlement_types_fail_closed():
    bad = dataclasses.replace(ENTITLEMENT, review_limit=True)
    assert decide(entitlement=bad).code is Code.INVALID_ENTITLEMENT
    bad = dataclasses.replace(ENTITLEMENT, reviews_consumed="0")
    assert decide(entitlement=bad).code is Code.INVALID_ENTITLEMENT
