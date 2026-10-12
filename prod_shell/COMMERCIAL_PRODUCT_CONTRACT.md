# MACIE C — Commercial Product Operating Contract (binding)

**Product boundary:** MACIE C is a standalone, customer-purchased document and content review service. It is **not** an owner-operated consulting workflow, a private SageForge tool, or a human-assisted document review bureau.

## Definition of a successful sale

A new, unrelated customer must be able to complete all of the following **without the product founder manually intervening**:

1. Visit the product website, understand the offering and its limits, and accept the posted terms and privacy disclosures.
2. Create and verify their own account, sign in, and recover access without contacting the founder.
3. Select a clearly defined paid plan or authorized trial and complete hosted checkout without handing payment card details to MACIE.
4. Have a separate tenant/organization provisioned automatically **only after verified payment/trial entitlement**; every document, review job, seat, audit event, and quota belongs to that tenant.
5. Upload or paste an existing document, instruct MACIE C how to evaluate it, receive two genuinely independent model reviews, an agreement map, supported disagreements / NON-CONSENSUS when appropriate, an explained improved artifact, and a download.
6. Invite and manage authorized seats under their own organization (where included in the plan); prevent cross-tenant and unauthorized document/result access.
7. View usage/remaining allowance, update card/billing information, obtain invoices, upgrade/downgrade, and cancel from a customer-controlled portal.
8. Handle normal failures, payment retries and expired plans, quota enforcement, safe retries and document export/deletion through the product itself.
9. Receive help via customer-facing product documentation and a support channel routed to a **separately designated service operation**, with escalation for incidents; no manual handoff to the founder for each purchase or review.
10. Leave without founder involvement: subscription entitlement is revoked or scheduled to expire, customer documents are deleted/exported under the published policy, and access is revoked.

A product operator may perform rare maintenance, governance, security, legal, or incident response. This is fundamentally different from the founder manually activating individual customers, distributing passwords, running document reviews, changing environment variables per sale or submission, approving every output, or supervising each customer account.

## Permanent buyer-owned AI key rule — BYOK

**The purchaser independently creates and controls the AI provider API key used for MACIE C. The product owner must NEVER supply, loan, pay for or manually install model API keys on the customer's behalf.**

- MACIE C implements **Bring Your Own Key (BYOK)**. A buyer establishes an OpenRouter account and creates a **standard completion API key** with an appropriate spending limit, using OpenRouter's secure settings. One OpenRouter key enables both independent Claude-family and OpenAI-family model calls; an Anthropic direct account is not required.
- **Two distinct credentials:** MACIE C login/subscription authenticates the buyer to the application and licenses access. The *buyer's OpenRouter API key* authorizes billable AI inference directly against that buyer's provider account. They are not interchangeable; purchases cannot be bypassed by entering a provider key.
- Customer self-service provider settings must securely support connect/verify, key replacement, provider-credit warnings, revoke/delete and an explanation of expected provider charges. A customer does not send a key to the proprietor, support staff, email, issue tracker or chat.
- API keys are handled **server-side only over HTTPS**, never embedded in front-end JavaScript bundles, browser storage, query strings, telemetry, logs or generated documents. Keys are isolated per authenticated customer organization, encrypted using separate server-managed envelope keys at rest, and decrypted only for permitted model requests. Staff-facing logs show only nonsecret status.
- MACIE C must **fail closed** if the buyer's key is absent, invalid, expired, out of credits, revoked or permission-restricted. A customer's call must never silently fall back to the owner's or another customer's provider credentials, nor permit Claude to be substituted by GPT while falsely declaring consensus.
- Commercial release requires **durable encrypted tenant-specific credentials**, validated provider connections, account recovery that does not expose keys, usage metering, and lifecycle deletion. The current implementation stores buyer keys **encrypted in temporary process memory for one signed-in pilot session**, then requires reconnect on restart/sign-out. This is NOT a durable production key vault.
- A provider key alone must not grant access: subscription eligibility, tenant membership, quota and upload/privacy checks are still enforced by MACIE C.

## Architectural invariants

- **No dependency on any private owner intelligence environment.** This commercial product uses only explicitly licensed/common review engine code, customer content, configured model providers and tenant-authorized product services.
- **No direct proprietor or personal inbox dependency.** All routine operations are driven by customer actions and verified system events, not founder approvals or messages.
- **Identity and authorization:** use a proven hosted identity service or audited equivalent with email verification, account recovery, secure sessions and tenant memberships. An email entered in a form is not identity. Per-request server-side authorization is mandatory.
- **Billing:** use hosted payment collection, signed webhook verification, idempotent events, a durable customer/subscription mapping, bounded access for failed payments, proration and cancellation handling, and a self-service billing portal. Do not trust client-reported payment success.
- **Durability:** a real SQL datastore is required for customers, tenants, membership, subscription entitlement, quotas, idempotency and jobs. Never sell the current in-memory, single-process job dictionary as durable service.
- **Jobs and isolation:** durable queue/storage as warranted; enforce tenant ID and owner access before every review and download. No unbounded free API calls; quotas, concurrency and cost limits must be enforced before providers are billed.
- **Security/privacy:** encryption in transit/at rest, least privilege, no private documents in app logs, appropriate retention and deletion, data-provider disclosure, upload validation, malware/zip-bomb protections, and documented incident response.
- **Two-model honesty:** verify actual Claude and OpenAI-family provider identities; if either or synthesis fails, report NON-CONSENSUS. Do not market synthetic fixture output as live consensus.
- **Brand ownership and IP:** paid customers get MACIE C product capabilities only; they cannot access other customer records or owner-private systems.
- **Availability:** health checks, deployment rollback, monitored errors/latency/spend, incident notification to the responsible product operations channel, not the founder as a required per-customer step.

## Current implementation state (October 2026)

**Existing controlled pilot:** `macie_web.py` + `prod_shell/src/macie_c_portal.py`, running on Render, supports pasted text/DOCX/TXT, login using manually stored environment-variable users, in-memory jobs and transient result retrieval. Prior tests demonstrated the two-model engine; local access checks passed. This is **NOT** the commercial launch configuration.

**Known sale blockers:**
- No automated signup/email verification/password reset and durable BYOK vault.
- No Stripe or equivalent live checkout, payment webhook verification, recurring entitlements or self-service billing portal.
- No durable tenant/member/usage/job database and no multi-worker-safe job queue.
- No user-managed invitations/roles and no automated cancellation/data deletion.
- No defined live support, SLA, consent/privacy/terms, metered provider cost cap, or release security audit.
- The existing GitHub repository is public while old docs characterize sections as internal; perform a code/history/secrets exposure review and move owner-private content out before selling.
- Current credential bootstrap (`MACIE_C_USERS_JSON`) requires manual operator involvement and must be replaced **before commercial access is offered**.

## Implementation phases and gates

**Phase A — tenancy and entitlements:** durable schema `tenants, users, memberships, billing_customers, subscriptions, quotas, reviews, review_events`; access controls on every route and job; negative tests for cross-tenant attempts. Pure server-side policy implemented in `prod_shell/src/commercial_access.py`, awaiting durable adapters.

**Phase B — unattended customer lifecycle:** hosted identity service, verified registration/login/recovery, subscription checkout and signed idempotent webhooks; successful purchase provisions a tenant automatically. Failed, canceled, expired accounts suspend paid processing. Self-service billing, invoice/cancellation and seat management.

**Phase C — reliable review operations:** durable queue and result storage, encrypted input, retention/delete controls, true two-model invocation, capped spend and usage metering, customer downloads, recovery from worker restart, health and error alerts.

**Phase D — go-to-market readiness:** privacy/terms/refund policy, support workflow, security and penetration tests, disaster recovery, synthetic smoke checks, pricing/unit-economics approval, real paid test in sandbox with a customer other than the founder, and documented customer onboarding.

**RELEASE GATE: BLOCKED until ALL phases are demonstrated with authentic end-to-end evidence**, including an unseen test customer buying, using, paying and canceling without the founder's participation. Tests of isolated policy functions and a protected pilot portal alone do not satisfy this.

**Packaging:** Web subscription is the implementation baseline because the existing product already runs on Render. If a licensed self-hosted/offline edition is later chosen, it must independently meet the zero-founder-dependency requirement for install, activation/license management, updates, support and renewal.

## Approval boundary

Founder makes one-time business-policy decisions (e.g., pricing, legal terms, capital commitment and whether to release). **Customer-by-customer usage, onboarding, reviewing, billing, account recovery and cancellation never require founder participation.**
