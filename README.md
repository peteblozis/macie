# MACIE — Multi-AI Consensus Intelligence Engine

**Internal — SageForge Core. Not for external distribution.**

This repository is the build target for MACIE v1, Phase 1 (Core-Mode for Pete and Pete Jr.).

## Authoritative documents

All work in this repository conforms to two binding documents, in this order of precedence:

1. **Core/Product Separation Charter v1.0** — governs the engine/shell separation rules.
2. **MACIE v1 Specification** — defines the Phase 1 build target, acceptance criteria, and build order.

If anything in this repository conflicts with either document, the documents win and the code must be corrected.

## Repository layout

```
/engine        Shared consensus engine. NO Core dependencies. NO Pete-private data.
               Identical behavior across both shells.

/core_shell    Pete + Pete Jr. only. Imports /engine. Adds Cloudflare Access,
               MFA, audit logging, Forge Factory context, project memory.

/prod_shell    Phase 1: stub only. Imports /engine. Proves engine works without
               Core. Phase 3: becomes the real customer-facing shell.

/scripts       Build, test, and CI helpers.
/docs          Internal documentation (NOT for customer distribution).
```

> Note: directory names use underscores (Python convention for importable
> packages). The Charter and Spec use the descriptive forms "core-shell" and
> "prod-shell" in prose; these refer to the same components.

## Hard rules (enforced by pre-commit check)

- `/engine` may not import from `/core_shell` or `/prod_shell`.
- `/engine` may not contain the strings: `SageForge`, `Forge Factory`, `ForgeShield`, `Core Extraction`, `Pete`, `Blozis`, `Pete Jr`, or any other internal terminology or personal identifiers.
- `/engine` must run successfully when imported by `/prod-shell` with zero Core dependencies.

Violations block commits. No exceptions.

## Phase 1 build order (from the Spec, Section 8)

1. Repository scaffold + pre-commit purity check ← **this commit**
2. Engine v1: consensus function, Claude + ChatGPT adapters, ConsensusResult schema, unit tests
3. Stub Production Shell: minimum viable import-and-run test
4. Core Shell v1: query, result, divergence callout, history, export
5. Cloudflare Access configuration
6. Audit log integration
7. Revocation test
8. Smoke test with Pete and Pete Jr.
9. Pete sign-off on daily-use readiness

## Access

- **Pete (Admin/Owner):** full Core Shell + admin operations.
- **Pete Jr. (Tester):** Core Shell query/review only, no admin.
- **All others:** denied at Cloudflare Access edge.

## Status

Phase 1, Step 2 of 9 — Engine v1 implemented and tested. Proceed to Step 3 (Stub Production Shell) — already wired up as part of Step 2 to validate the engine boundary.
