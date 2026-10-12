# MACIE C Commercial Self-Service — executable implementation / release gates

**Owner requirement:** MACIE C is a separately SOLD product. Every buyer must create their own product account and their own OpenRouter provider key and can purchase, operate, recover access, rotate keys, review documents, download results and cancel independently. No Pete/manual activation, no owner-paid model calls, no access to private SageForge information.

## What this branch actually adds

- `commercial_store.py`: durable, transactionally written account, email verification, recovery, tenant membership, subscriptions, billing-event dedupe, usage quotas, tenant/user-scoped encrypted provider keys, encrypted 30-minute review records and owner-only result retrieval. PostgreSQL supported for production. SQLite is deliberately test-only.
- `commercial_mail.py`: SMTP STARTTLS email verification/password recovery; verification token stored only as a hash and embedded in the browser URL **fragment**, which is not sent to the server until browser POST.
- `commercial_portal.py` and `commercial_template.py`: independent customer signup/login/verification/recovery, own OpenRouter key connect/rotate/revoke, review submission and result checks with paid-entitlement enforcement, hosted checkout, self-service billing redirect, signed billing webhooks, login throttling. **These routes are disabled in production until release gates are met.**
- `commercial_billing.py`: optional Stripe hosted subscription checkout and billing portal; authentic Stripe SDK **webhook signature verification** before any subscription state change; checkout return or browser `paid=true` never grants access. Signed checkout links account/tenant; paid invoice activates; failed invoice/cancellation suspends; replay/out-of-order events cannot increase entitlements.
- Real GitHub Actions job against **temporary PostgreSQL 16**; Python API tests with fake mailer and fake AI provider; actual Stripe SDK verification against synthetic HMAC-signed webhook test bodies. No owner data/credentials, real card transaction or public sale used.
- Existing `/macie/c` controlled pilot stays separate. Owner-private MACIE A remains excluded from the commercial shell.

## Deployment: MUST remain disabled

This implementation is intentionally fail-closed. Do **not** set `MACIE_C_COMMERCIAL_ENABLED=1` or `MACIE_C_COMMERCIAL_RELEASE_APPROVED=1` merely because unit/CI tests pass.

Before either is enabled, the product operator must configure the following as **protected Render runtime secrets** (do not send them to a chat, GitHub, public files, or customer email):

| Variable | Purpose |
| --- | --- |
| `MACIE_C_COMMERCIAL_DATABASE_URL` | Private/internal Render **Postgres** DSN; no SQLite on hosted production. |
| `MACIE_C_COMMERCIAL_VAULT_SECRET` | Independent high-entropy 40+ char encryption master key, protected and backed up. |
| `MACIE_C_SMTP_HOST`, `MACIE_C_SMTP_USERNAME`, `MACIE_C_SMTP_PASSWORD`, `MACIE_C_EMAIL_FROM` | Transactional verification/recovery email sender over validated TLS. |
| `MACIE_C_PUBLIC_ORIGIN` | Approved production HTTPS origin for all links. |
| `MACIE_C_MERCHANT_SECRET_KEY`, `MACIE_C_MERCHANT_WEBHOOK_SECRET`, `MACIE_C_MERCHANT_PRICE_ID` | Approved merchant credentials, genuine signed webhook and recurring price. |
| `MACIE_C_MERCHANT_LIVE_MODE=1`, `MACIE_C_COMMERCIAL_PLAN_LIMIT`, `MACIE_C_COMMERCIAL_PLAN_DISPLAY` | Real billing mode, approved included review quota, visible price. |
| `MACIE_C_TERMS_URL`, `MACIE_C_PRIVACY_URL`, `MACIE_C_SIGNED_TERMS_VERSION`, `MACIE_C_PRIVACY_VERSION` | Legally reviewed public documents and version acceptance. |
| `MACIE_C_CUSTOMER_SUPPORT_EMAIL` | Independent business support queue, not required founder participation. |
| `MACIE_C_COMMERCIAL_ENABLED=1`, `MACIE_C_COMMERCIAL_RELEASE_APPROVED=1` | **Two separate one-time release flags, OFF until signoff.** |

**No actual paid database or payment-processing account was created by this branch.** The user has explicitly rejected purchasing another system. Using a merchant processing connector does not replace MACIE C, but any new charges and legal/merchant agreement require separate one-time approval.

## Release testing still REQUIRED (not satisfied by mocked CI)

1. Provision a durable Render PostgreSQL instance **after cost/retention approval**. Apply a reviewed schema migration (production must not run `create_all()` from an unverified app startup). Verify backups and restore.
2. Configure verified transactional email. Test real signup, email verification and recovery with non-owner accounts, throttling/abuse prevention, customer lifecycle and correct cookie/session revocation.
3. Configure approved hosted merchant processing and pricing. Verify sandbox customer buys, paid-invoice webhook activates, tampered/duplicate/late events are refused, renewal quota resets only on valid payment, overdue/canceled users are denied, invoices/cancellation self-service work. Then validate actual merchant production settings without making unintended charges.
4. Verify real OpenRouter customer key shape/validation, own-account charges, key rotation, no owner key fallback, cross-tenant isolation and no unauthorized disclosure in app/router logs.
5. Demonstrate authenticated live Claude and GPT replies, synthesis/explicit NON-CONSENSUS, before/after edits, valid file uploads, download results, and follow-up on external customer (e.g. HOMEstretch) material **without founder contact**.
6. Replace current in-process thread queue with a production-grade durable claim/recovery flow. Define who pays for partial provider calls if a worker dies and prevent unintended retries/duplicate model charges. The DB already tracks job status and encrypted payload, but worker crash handling is not yet complete.
7. Confirm 30-minute document deletion under suspended app conditions with a scheduled external retention job, customer-initiated deletion/export, disaster recovery, incident playbook, vulnerability assessment, sensitive data handling and customer support SLAs.
8. Confirm repository history/public `core_shell` files contain no owner-private context and no credentials. Move/separate private source before commercial marketing if any contamination found.
9. Verify business legal terms, privacy/security disclosures, data processing/AI provider terms, review quotas, pricing, refunds and merchant taxes, approved customer service contact and actual support resolution.
10. An **unrelated test customer** completes the entire paid cycle from signup to cancellation/erasure without founder involvement. Record receipts/verified webhook IDs/status and test-case evidence, not sensitive personal details.

## Honest state

- **Working engine:** previously proved Claude and OpenAI GPT produce live independent reviews.
- **Working controlled pilot:** deployed on Render with a customer-owned OpenRouter session key.
- **Commercial store/UI/merchant integration:** feature-flagged, testable code in this branch; **not yet activated or commercially deployable** without the gates above.
- The preceding test flows use synthetic external model responses and simulated payment/email delivery. Success does not prove real checkout, email delivery, or production database.
- Do not modify the HOMEstretch activation email to say commercial buying is enabled until all gates pass.
