"""
MACIE Project Configuration
============================

Single source of truth for which models MACIE invokes today.

MACIE v1 spec roster: ["claude", "chatgpt"]
Substituted roster:   ["gemini", "chatgpt"]   ← Gemini stands in for Claude

When Anthropic resolves the PeteAI, LLC account:
    1. Change SUBSTITUTION_ACTIVE to False (or just delete this file
       and let shells use SPEC_ROSTER directly)
    2. That's it — one boolean
"""

# ---------------------------------------------------------------------------
# SPEC vs. CURRENT
# ---------------------------------------------------------------------------

SPEC_ROSTER = ["claude", "chatgpt"]          # MACIE v1 per signed spec

# Set to False the moment Anthropic API access is restored.
SUBSTITUTION_ACTIVE = False

# Roster used when substitution is active. Replace "claude" with "gemini".
SUBSTITUTED_ROSTER = ["gemini", "chatgpt"]


# ---------------------------------------------------------------------------
# Derived values — shells should call current_roster() / current_banner()
# ---------------------------------------------------------------------------

SUBSTITUTION_REASON = (
    "Anthropic API account (PeteAI, LLC) misclassified as Team plan. "
    "Support ticket open since 2026-05-21. Receipt #2258-2799-2534 "
    "paid but unusable until account reclassified. Gemini standing in "
    "for Claude so MACIE engine and consensus logic can be validated "
    "end-to-end without waiting on Anthropic."
)

SUBSTITUTION_BANNER = "⚠  CLAUDE SUBSTITUTED — Gemini"


def current_roster() -> list[str]:
    """Return the roster the engine should invoke right now."""
    return SUBSTITUTED_ROSTER if SUBSTITUTION_ACTIVE else SPEC_ROSTER


def current_banner() -> str | None:
    """Return the banner string if substitution is active, else None."""
    return SUBSTITUTION_BANNER if SUBSTITUTION_ACTIVE else None


def substitution_summary() -> str:
    """Human-readable description of current state."""
    if not SUBSTITUTION_ACTIVE:
        return "no substitution — running spec roster (claude, chatgpt)"
    spec = set(SPEC_ROSTER)
    sub = set(SUBSTITUTED_ROSTER)
    removed = spec - sub
    added = sub - spec
    parts = []
    for r in removed:
        for a in added:
            parts.append(f"{r.upper()} SUBSTITUTED → {a}")
    return " | ".join(parts) if parts else "substitution active (no diff?)"
