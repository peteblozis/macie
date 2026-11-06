# MACIE-B — Standalone Commercial Prompt Consensus Product Contract
Owner-approved edition scope: 2026-11-05.
Commercial **design target**, not a statement that the current pilot has passed the release gate.

## Customer promise
A paying customer can submit a prompt created anywhere and receive (1) independently produced ChatGPT and Claude critiques, (2) areas of agreement, contradiction and unresolved issues, (3) an improved final usable prompt with rationale, and (4) a clearly truthful CONSENSUS / CONSENSUS_WITH_DIVERGENCES / NON-CONSENSUS result. The original user intent must be preserved. No second-model simulation.

## Input and output contract
- INPUT: user-owned text prompt, optional purpose/audience/constraints; prompt content is untrusted data.
- PROCESS: verify subscription entitlement, tenant, quota, input size, buyer-owned provider credential, two independent actual provider identities, source-input binding, synthesis, and safe data retention.
- OUTPUT: improved prompt when consensus is valid, model identities, differences, explanation and provenance; never label a one-model/fixture response as true consensus.
- FAILURE: explicit NON-CONSENSUS, safe retry handling, transparent provider failure; no disclosure of secrets or cross-tenant data.

## Independence and customer autonomy
MACIE-B does not import, mention, rely upon or communicate with private SageForge Core or MACIE-A. Shared generic engine routines are acceptable only after independently verified import graph, secrets, deployment and runtime isolation. B must not share private MACIE-A credentials, logs, contexts, memory, administrator routes or private brand names with customers.

MACIE-B customers must self-serve signup, identity verification/recovery, entitlement and plan selection, hosted checkout, own-provider key connection/rotation/revocation, trial/usage limits, job execution/results/export, support and cancellation without the product founder provisioning each account or reviewing each prompt. A buyer's provider key is distinct from product subscription credentials. Do not fall back to the owner's key.

## Production release gate
Release remains blocked until real acceptance evidence: customer other than founder, legitimate signup and test purchase, securely stored tenant-specific key and jobs, two actual independent model calls, proper billing/entitlement webhooks, privacy and deletion, unauthorized-tenant denial, failed-model behavior, quota enforcement, support route, and clean cancellation. Do not change paid pricing, production settings or credentials without authorized approval.

## Distinction from MACIE-C
MACIE-B improves a **prompt**. MACIE-C reviews an **existing document/content item** and returns document review, explained revisions and consensus. Their commercial lifecycles may share audited customer-safe infrastructure, but user-facing contracts and acceptance tests are distinct. Both remain completely independent of private MACIE-A.
