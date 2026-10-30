# UPSCAN implementation evidence - October 30, 2026

## Confirmed changes

- Existing SFC Morning Dispatcher + UPSCAN task updated successfully.
- Exact prompt readback matches original plus approved consensus amendment.
- Existing enabled state and 8:00 AM America/Chicago schedule verified unchanged.
- Private protocol, authenticated subscription bridge, Flask registration,
  bounded challenge/exact-draft acceptance, durable duplicate protection,
  scoped return receipts, and no-paid-fallback preflight implemented.
- Dedicated offline CI workflow and operator protocol included.

## Local validation

Command: `PYTHONPATH=<temporary test dependencies> python -m pytest core_shell/tests -q`

Result: **36 passed in 0.45s**, including 25 new protocol/bridge cases and
11 existing core-shell regression cases. Python compilation passed. The existing
macie_web.py introductory Windows-path docstring emits an escape-sequence warning;
it does not affect compilation and was not changed by this feature.

Tests cover: full three-stage fixture return flow, strict fixture labels, blind
review even when Claude returns first, final-hash mismatch, partial/no agreement,
missing reviewer, no-change review, immutable evidence, unknown sources, duplicate
runs and callbacks, overwritten receipts, substituted models, restart-safe
dispatch claims, expiry, owner authentication, forged capabilities, callback
tokens denied owner access, disabled bridge, API-key rejection, required billing
verification, trigger-versus-completion distinction, uncertain fire without
automatic retry, and inaccessible-source gaps.

## Live state at this checkpoint

No provider API spending or model calls occurred in testing. No live consensus
was claimed. Claude's cloud-task page was opened and showed a sign-in requirement;
no signed-in Pro session or routine token is available to this runtime. The local
runtime has no Claude CLI and no Claude/Anthropic/OpenRouter/MACIE credentials.

The production bridge remains disabled by default. Live activation requires
authorized Claude Pro sign-in, task setup, a private authenticated return path,
durable existing service storage, checked billing settings, deployment and one
actual two-provider review. These account/deployment steps have not been
represented as completed by offline tests or a dispatcher instruction update.
