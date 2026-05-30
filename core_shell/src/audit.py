"""
Audit log — append-only, per the SageForge Core security baseline.

Every query, model invocation, synthesis, export, and access event is written
here. Nothing is ever deleted from the audit log programmatically. The log
file itself is a newline-delimited JSON file (one JSON object per line) so it
is both human-readable and machine-parseable.

The audit log is a Core Shell responsibility. It never touches the engine or
the production shell.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Default log location — override via MACIE_AUDIT_LOG_PATH environment variable
DEFAULT_LOG_PATH = Path("audit") / "macie_audit.log"


def _log_path() -> Path:
    raw = os.environ.get("MACIE_AUDIT_LOG_PATH", str(DEFAULT_LOG_PATH))
    return Path(raw)


def _ensure_log_dir() -> Path:
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write(event_type: str, user_email: str, data: dict[str, Any]) -> None:
    """
    Append one event to the audit log.

    Args:
        event_type: Short identifier for the event type. Examples:
            "query_submitted", "consensus_completed", "export_created",
            "access_denied", "session_started"
        user_email: Authenticated user who triggered the event.
        data: Event-specific data. Must be JSON-serializable.
            NOTE: Never include the raw query text or model outputs here —
            those stay in the result store. The audit log records metadata
            only: what happened, who did it, when, and what the outcome was.
    """
    path = _ensure_log_dir()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "user": user_email,
        "data": data,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_recent(n: int = 50, user_email: str | None = None) -> list[dict]:
    """
    Read the most recent n audit entries, optionally filtered by user.

    Args:
        n: Maximum number of entries to return (most recent first).
        user_email: If provided, only return entries for this user.

    Returns:
        List of audit entry dicts, most recent first.
    """
    path = _log_path()
    if not path.exists():
        return []

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if user_email is None or entry.get("user") == user_email:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    # Most recent first
    entries.reverse()
    return entries[:n]
