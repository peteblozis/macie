# MACIE C local document-review pilot

This separate application accepts an existing document, obtains independent
Claude and ChatGPT reviews through the existing AI router, and asks ChatGPT to
reconcile them into an improved document with weaknesses, changes, agreements,
and unresolved disagreements. The source is preserved byte-for-byte as UTF-8
text in a JSON receipt with its SHA-256 digest, raw model outputs, router request
IDs, provider/model names, latency, and token usage. Router IDs are application
correlation IDs, not provider-issued receipt IDs.

Run from the repository root after installing `requirements.txt`:

```powershell
python -m prod_shell.src.review_web
```

Open http://127.0.0.1:5073/macie-c. Configure existing model credentials through
the process environment: `OPENAI_API_KEY` and `OPENROUTER_API_KEY`. Model routing
uses the existing router configuration; no credentials are loaded from another
installation by this application. Optional `MACIE_C_OUTPUT_DIR` selects where
receipts are stored (default `logs/macie-c`). Keep this directory private.

## Boundaries and behavior

- No private shell, private configuration, registry, project memory, or existing
  web-app routes are loaded. Only the submitted document reaches the reviewers.
- The local server binds to loopback, rejects nonlocal clients and untrusted
  hosts, and requires a session-bound CSRF token and matching Origin for writes.
- Source and model output are rendered as text, never executable HTML.
- One review can run at a time; inputs are limited to 24,000 characters.
- Two successful distinct model responses and validated synthesis are required.
  Otherwise the receipt is `INCOMPLETE`, with no fabricated revision.
- Unresolved issues produce `NON-CONSENSUS`; otherwise the status is `REVIEWED`,
  not a claim that facts or software were independently verified.
- Approval is a user action in the browser. It marks the downloaded copy only;
  the original saved receipt remains unapproved. Nothing is executed or published.
- The receipt preserves actual model wording even when imperfect. Humans must
  inspect the improved document and independent reviews before accepting it.

## Validation

```powershell
python -m pytest -q engine/tests core_shell/tests prod_shell/tests registry/tests sfc_ai_router/tests
python scripts/check_engine_purity.py
```

Tests explicitly use test doubles, including failed providers, malformed
synthesis, unresolved disagreement, duplicate model identity, source preservation,
private-module import isolation, inaccessible private routes, and request guards.
Unit tests are not evidence of real model execution. A live pilot must retain its
separate receipt and browser evidence.

## Deployment limits

This is a local pilot, not a customer deployment. Do not point the existing host
at it or expose the development server. A remote version still needs separate
authenticated hosting, tenant data isolation, durable approval/storage, retention
and deletion controls, operational limits, and negative authorization tests.
The existing Core app, infrastructure, and start command are not modified.
