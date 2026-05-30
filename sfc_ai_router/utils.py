"""SageForge AI Router — utility helpers."""
from __future__ import annotations
import json
import random
import re
import time
from typing import Any, Optional


def extract_json(text: str) -> Optional[Any]:
    """Best-effort JSON extraction. Strips ```json fences. Never raises."""
    if not text:
        return None
    cleaned = re.sub(r"```json", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"[{\[][\s\S]*[}\]]", cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


def new_request_id() -> str:
    ts = format(int(time.time() * 1000), "x")
    rand = format(random.getrandbits(32), "08x")
    return f"req_{ts}_{rand}"
