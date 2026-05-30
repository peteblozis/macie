"""SageForge AI Router — append-only audit log.

Aligns with SageForge Core security baseline (append-only records).
NEVER writes API keys. NEVER writes full prompts/responses unless
AI_ROUTER_DEBUG_LOG_FULL_PROMPTS=true is explicitly set.
"""
from __future__ import annotations
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .types import RouterResult

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]+|AKIA[0-9A-Z]{12,})"
)


def _redact(s: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", s)


@dataclass
class AuditRecord:
    timestamp: str
    request_id: str
    lane: str
    task_type: str
    selected_provider: Optional[str]
    selected_model: Optional[str]
    fallbacks_attempted: list[str]
    success_or_failure: str
    error_code: Optional[str]
    latency_ms: int
    token_usage: Optional[dict]
    zdr_required: bool
    zdr_satisfied: Optional[bool]
    prompt_preview: Optional[str] = None  # only when debug enabled


def build_record(
    result: RouterResult,
    lane: str,
    task_type: str,
    prompt_preview: Optional[str] = None,
) -> AuditRecord:
    from .config import config  # local import avoids circular
    preview = None
    if config.debug_log_full_prompts and prompt_preview:
        preview = _redact(prompt_preview)[:500]
    return AuditRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        request_id=result.request_id,
        lane=lane,
        task_type=task_type,
        selected_provider=result.provider if result.ok else None,
        selected_model=result.model if result.ok else None,
        fallbacks_attempted=result.fallbacks_attempted,
        success_or_failure="success" if result.ok else "failure",
        error_code=result.error.code if result.error else None,
        latency_ms=result.latency_ms,
        token_usage=asdict(result.usage) if result.usage else None,
        zdr_required=result.zdr_required,
        zdr_satisfied=result.zdr_satisfied,
        prompt_preview=preview,
    )


def write_audit(record: AuditRecord, path: Optional[str] = None) -> None:
    from .config import config
    log_path = path or config.audit_log_path
    line = json.dumps(asdict(record)) + "\n"
    try:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        sys.stderr.write(line)
