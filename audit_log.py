"""
MACIE Audit Logger
==================

Append-only JSONL log of every MACIE run. One line per run. Records
substitution status and shell so you can later prove which runs were
spec-true (Claude + ChatGPT) vs. substituted.

Per SageForge Core security baseline: append-only, retained.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Default log location — override with MACIE_AUDIT_LOG env var if you want
DEFAULT_LOG_PATH = os.environ.get(
    "MACIE_AUDIT_LOG",
    str(Path.home() / ".macie" / "audit.jsonl"),
)


def log_run(
    request_id: str,
    user_prompt: str,
    roster: list[str],
    substitution_active: bool,
    substitution_summary: str,
    shell: str,
    success: bool,
    confidence: str | None = None,
    note: str | None = None,
    log_path: str | None = None,
    caller_id: str | None = None,
) -> None:
    """Append one audit record. Never modifies existing records."""
    path = Path(log_path or DEFAULT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "caller_id": caller_id if caller_id else "UNREGISTERED",
        "user_prompt_preview": user_prompt[:200],
        "roster": roster,
        "substitution_active": substitution_active,
        "substitution_summary": substitution_summary,
        "shell": shell,
        "success": success,
        "confidence": confidence,
        "note": note,
    }

    # Append-only — open in 'a' mode, never 'w'.
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
