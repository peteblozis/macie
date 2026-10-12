# MACIE A/B/C binding product boundary — owner-confirmed 2026-10-12

- **A / 1:** internal SFC-powered consensus unit. Not for sale.
- **B / 2:** commercial enhancement of a **prompt created anywhere** through **independent ChatGPT and Claude consensus**. No SFC access, context, or dependency.
- **C / 3:** commercial enhancement of **existing documents/articles/material** using independent **ChatGPT and Claude** reviews and consensus. No SFC access, context, or dependency.
- B/C must operate self-service with customer-owned keys, isolated accounts and records; never depend on the founder.

## Verified inspection findings (not a security certification)
- `macie_web.py` mounts both `prod_shell.src.macie_c_portal` and `commercial_portal`.
- `prod_shell/src/macie_c.py` dispatches `['claude','chatgpt']` through the shared engine.
- `prod_shell/src/macie_c.py` imports `sfc_ai_router` for customer OpenRouter routing. The name alone is not proof of private SFC data access, but commercial independence must be proven by import graph, secret isolation, and runtime tests.
- Existing `README.md` describes MACIE v1 as internal SFC Core; `macie_web.py` presents a Core-branded page. Verify these cannot appear in commercial B/C.
- No MACIE B dedicated production entrypoint has been established in this review.
- `prod_shell/SELF_SERVICE_RELEASE_CHECKLIST.md` explicitly says MACIE C commercial release remains gated.

## Release gates (fail closed)
1. Separate A internal routes from B/C customer routes and public assets.
2. Establish B dual-model ChatGPT + Claude prompt consensus and tests; never misrepresent C as B.
3. Prove C uses actual independent Claude and OpenAI-family models, never substituted same-provider consensus.
4. Prove B/C do not load owner SFC knowledge, credentials, routes, or private modules.
5. Verify tenant isolation, BYOK, subscription, legal, security and live end-to-end checks.
6. Remove Core branding from commercial customer views without changing A.
7. Do not set commercial release flags, merge or deploy until tests and approvals are evidenced.

This file documents the discrepancy and gates; it does not certify production readiness.
