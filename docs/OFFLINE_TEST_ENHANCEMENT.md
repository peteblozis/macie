# Existing test suite enhancement

This change extends the existing consensus engine, document-review shell and HTTP route tests. It adds no provider, no alternate consensus engine and no live endpoint enablement.

## Reproduced defects and repairs

- Blank reviewer responses were excluded by the document shell but still counted as successful in engine telemetry. The engine now marks blank/invalid text as a failed response.
- JSON synthesis arrays, numbers, invalid field types and malformed divergence positions could crash the engine or be accepted as a synthesis. The existing synthesizer now checks the documented response shape and returns its existing low-confidence raw fallback on invalid data. The document-review shell reports NON-CONSENSUS for that fallback.

The new tests failed against the unchanged source and pass with these repairs. The HTTP denial tests verify that a disabled route, missing/wrong key, malformed JSON and excessive payload do not invoke review. Client-supplied adapter options are not forwarded. Transport tests verify the actual retry policy's three-attempt bound, rate-limit recovery and no retry on authentication/billing denials, using a fake HTTP client and an injected no-delay sleeper.

## Execution

```bash
python -m pytest -q engine/tests core_shell/tests prod_shell/tests registry/tests sfc_ai_router/tests --junitxml=test-results/macie-offline.xml
python scripts/check_engine_purity.py
```

Local result on October 11, 2026: **93 passed**, including **38 added test cases**; engine purity check passed. Original suite: 55 passed. The added resilience/HTTP tests initially returned 11 failures and 20 passes against the original source, demonstrating that the tests detect the repaired defects.

The existing MACIE review workflow now triggers on engine/router changes as well as review-shell changes, includes all existing suites plus the additions, and retains test results even on failure. It uses no provider API credentials.

## Limits

All new model and HTTP outputs are synthetic. These tests verify software behavior; they do not prove factual accuracy, live prompt-injection resistance, current provider health, deployment identity, customer readiness or production activation. A valid JSON shape is not evidence that its claims are true. Existing live and release gates still apply.
