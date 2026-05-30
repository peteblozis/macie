"""SageForge AI Router — provider health + customer-facing surface guard."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional

_COOLDOWN_S = 60.0


class ProviderHealth:
    """Marks providers unavailable after auth/billing failures, with cooldown."""

    def __init__(self) -> None:
        self._unavailable_until: dict[str, float] = {}

    def is_available(self, name: str) -> bool:
        until = self._unavailable_until.get(name, 0.0)
        if until == 0.0:
            return True
        if time.monotonic() >= until:
            self._unavailable_until[name] = 0.0
            return True
        return False

    def mark_unavailable(self, name: str, seconds: float = _COOLDOWN_S) -> None:
        self._unavailable_until[name] = time.monotonic() + seconds

    def mark_healthy(self, name: str) -> None:
        self._unavailable_until[name] = 0.0


# Module-level singleton for production use.
default_health = ProviderHealth()


# ---- Surface guard -------------------------------------------------------

_INTERNAL_TERMS = ["SageForge Core", "Forge Factory", "ForgeShield"]
import re as _re
_STANDALONE_CORE = _re.compile(r"\bCore\b")


@dataclass
class SurfaceScan:
    clean: bool
    hits: list[str] = field(default_factory=list)


def scan_customer_facing(text: str) -> SurfaceScan:
    hits: list[str] = []
    for term in _INTERNAL_TERMS:
        if term in text:
            hits.append(term)
    if _STANDALONE_CORE.search(text):
        hits.append("Core")
    return SurfaceScan(clean=len(hits) == 0, hits=hits)


def assert_no_internal_terms(text: str) -> None:
    scan = scan_customer_facing(text)
    if not scan.clean:
        raise ValueError(
            f"Customer-facing output contained internal term(s): {', '.join(scan.hits)}"
        )
