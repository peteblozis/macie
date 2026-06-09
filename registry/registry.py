from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

VALID_LANES = {"claude", "chatgpt", "gemini"}

REGISTRY_PATH = Path(
    os.environ.get("MACIE_REGISTRY_PATH", str(Path(__file__).parent / "agent-registry.json"))
)


def _registry_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("MACIE_REGISTRY_PATH", str(Path(__file__).parent / "agent-registry.json")))


SEED_AGENTS = [
    {
        "caller_id": "INT-FF-001",
        "product": "ForgeFactory",
        "instance": "core",
        "lanes": ["claude", "chatgpt", "gemini"],
        "registered_at": "2026-06-09T00:00:00+00:00",
        "status": "active",
    },
    {
        "caller_id": "INT-PL-001",
        "product": "PromptLessons",
        "instance": "core",
        "lanes": ["claude"],
        "registered_at": "2026-06-09T00:00:00+00:00",
        "status": "active",
    },
    {
        "caller_id": "EXT-CF-001",
        "product": "CallForge",
        "instance": "production",
        "lanes": ["claude", "chatgpt", "gemini"],
        "registered_at": "2026-06-09T00:00:00+00:00",
        "status": "active",
    },
]


def load_registry(path=None) -> dict:
    p = _registry_path(path)
    if not p.exists():
        data = {"agents": SEED_AGENTS}
        save_registry(data, path)
        return data
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_registry(data: dict, path=None) -> None:
    p = _registry_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def get_agents(path=None) -> list:
    return load_registry(path)["agents"]


def _prefix_for(product: str) -> str:
    words = product.split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return product[:2].upper()


def _next_caller_id(prefix: str, agents: list) -> str:
    """Generate next XX-NNN caller_id for new registrations (plain format)."""
    import re
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    existing = [
        int(m.group(1))
        for a in agents
        for m in [pattern.match(a["caller_id"])]
        if m
    ]
    seq = max(existing, default=0) + 1
    return f"{prefix}-{seq:03d}"


def register_agent(product: str, lanes: list, instance: str = "production", path=None) -> dict:
    if not product or not product.strip():
        raise ValueError("product name is required")

    if not lanes:
        raise ValueError("at least one lane is required")

    invalid = [lane for lane in lanes if lane not in VALID_LANES]
    if invalid:
        raise ValueError(f"invalid lanes: {invalid}. Valid values: {sorted(VALID_LANES)}")

    data = load_registry(path)
    agents = data["agents"]

    if any(a["product"].lower() == product.strip().lower() for a in agents):
        raise ValueError(f"product '{product}' is already registered")

    prefix = _prefix_for(product.strip())
    caller_id = _next_caller_id(prefix, agents)

    entry = {
        "caller_id": caller_id,
        "product": product.strip(),
        "instance": instance,
        "lanes": lanes,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }

    agents.append(entry)
    save_registry(data, path)
    return entry
