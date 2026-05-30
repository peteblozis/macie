# MACIE v1 Spec — Amendment 1

**Date:** 2026-05-24
**Author:** Pete Blozis
**Status:** Active

## Purpose

This amendment defines how MACIE handles the temporary unavailability
of a v1 spec-approved AI model, without changing what MACIE v1 is.

## Background

The signed MACIE v1 Spec defines the dispatch roster as **Claude +
ChatGPT only**, with the explicit statement: *"No Gemini, Perplexity,
Grok, or other models are part of MACIE v1 unless we later decide to
add them in a future version."*

On 2026-05-21, the Anthropic API account under organization
"PeteAI, LLC" was discovered to be misclassified as a Team plan,
making prepaid credits unusable. A support ticket was opened
(Receipt #2258-2799-2534, $47.97 paid). After multiple business
days without resolution, active MACIE engineering work stalled
because slot A (Claude) could not be invoked.

This amendment defines the governed response to that situation.

## Amendment Text

### Article 1. Temporary Substitution Permitted

If a v1 spec-approved provider becomes unavailable due to upstream
account, billing, infrastructure, or service issues outside MACIE's
control, a **temporary substitute model** may stand in for the
unavailable provider until the spec provider is restored.

### Article 2. Substitution Does Not Promote

A temporary substitute is **not** promoted to spec status. It fills a
slot only. The v1 spec roster remains Claude + ChatGPT. The
substitute model is not a third v1 model.

### Article 3. Mandatory Visibility Requirements

Every MACIE output produced while a substitution is active **must**
display a clearly visible substitution banner identifying:

- Which spec model is being substituted
- Which substitute model is filling that slot
- That the substitution is temporary

The banner shall be enforced at the engine output layer, not at the
shell layer, so it cannot be accidentally suppressed.

### Article 4. Mandatory Audit Trail

Every MACIE run while a substitution is active **must** be recorded
in the append-only audit log with:

- `substitution_active: true`
- The substituted roster
- A human-readable substitution summary

The audit log shall be append-only and retained per the SageForge
Core security baseline.

### Article 5. Production Shell Tagging

The Production Shell remains operational during substitution, but
output is tagged as non-spec. A future amendment may convert this
tagging to a hard block; v1 default is **tag, not block**, to
preserve customer-facing continuity.

### Article 6. Restoration Procedure

When the spec provider's upstream issue is resolved:

1. The `SUBSTITUTION_ACTIVE` flag in `macie_config.py` is set to
   `False` by the project admin (Pete Blozis).
2. The next MACIE run uses the spec roster `[claude, chatgpt]`.
3. The substitution banner disappears from subsequent outputs.
4. Audit log entries from that point forward show
   `substitution_active: false`.

No code rebuild, redeploy, or test rerun is required.

### Article 7. Current Active Substitution

As of the date of this amendment, the following substitution is
active:

| Slot | Spec Model | Substitute Model |
|------|------------|-------------------|
| A    | Claude     | Gemini (google-generativeai) |
| B    | ChatGPT    | (no substitution) |

**Substitute provider:** Google AI Studio / Gemini API
**Substitute model:** `gemini-2.5-flash`
**Reason:** Anthropic API account misclassification, support ticket
open since 2026-05-21, payment confirmed (Receipt #2258-2799-2534)
but credits unusable until reclassified.
**Expected duration:** Until Anthropic resolves account.

## Scope and Limits

This amendment does **not** authorize:

- Permanent addition of new models to v1
- Routing of customer (Production Shell) data to substitute providers
  without the visibility tag
- Disabling of the audit log
- Disabling of the substitution banner
- Use of substitute models that have not been pre-approved by Pete
  (current approved substitute providers: Google Gemini)

Future v2 work that intentionally adds a third dispatch model is
governed by a separate spec, not this amendment.

## Signature

Pete Blozis — 2026-05-24
