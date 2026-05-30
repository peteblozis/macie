"""
Result store — persists consensus results as versioned artifacts.

Each result is stored as a JSON file under the results/ directory with a
unique artifact ID. The artifact ID is used to reference the result in the
audit log, in Forge Factory records, and in exports.

Storage layout:
    results/
        {artifact_id}.json    — the full ConsensusResult + metadata

The result store is Core Shell only. Never exposed to the production shell.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.src.consensus_types import ConsensusResult, Confidence, Divergence, ModelOutput


DEFAULT_RESULTS_PATH = Path("results")


def _results_dir() -> Path:
    raw = os.environ.get("MACIE_RESULTS_PATH", str(DEFAULT_RESULTS_PATH))
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _result_to_dict(result: ConsensusResult, query: str, user_email: str,
                    project_context: dict | None = None) -> dict:
    """Serialize a ConsensusResult to a storable dict."""
    return {
        "query": query,
        "user": user_email,
        "project_context": project_context or {},
        "synthesized_answer": result.synthesized_answer,
        "confidence": result.confidence.value,
        "confidence_rationale": result.confidence_rationale,
        "agreement_map": result.agreement_map,
        "divergences": [
            {"claim": d.claim, "positions": d.positions}
            for d in result.divergences
        ],
        "model_outputs": [
            {
                "model_id": o.model_id,
                "model_version": o.model_version,
                "raw_text": o.raw_text,
                "latency_ms": o.latency_ms,
                "tokens_in": o.tokens_in,
                "tokens_out": o.tokens_out,
                "error": o.error,
            }
            for o in result.model_outputs
        ],
        "telemetry": result.telemetry,
    }


def save(result: ConsensusResult, query: str, user_email: str,
         project_context: dict | None = None) -> str:
    """
    Save a ConsensusResult as a versioned artifact.

    Returns:
        artifact_id: A unique string ID for this result.
    """
    artifact_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    artifact = {
        "artifact_id": artifact_id,
        "created_at": ts,
        "result": _result_to_dict(result, query, user_email, project_context),
    }

    path = _results_dir() / f"{artifact_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    return artifact_id


def load(artifact_id: str) -> dict | None:
    """
    Load a previously saved artifact by ID.

    Returns:
        The artifact dict, or None if not found.
    """
    path = _results_dir() / f"{artifact_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_recent(n: int = 20, user_email: str | None = None) -> list[dict]:
    """
    List recent artifacts, most recent first.

    Args:
        n: Maximum number to return.
        user_email: If provided, filter to this user's artifacts only.

    Returns:
        List of artifact summary dicts (artifact_id, created_at, query preview,
        confidence, user). Does not include full model outputs.
    """
    results_dir = _results_dir()
    summaries = []

    for path in sorted(results_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                artifact = json.load(f)
            result_data = artifact.get("result", {})
            user = result_data.get("user", "")
            if user_email and user != user_email:
                continue
            query = result_data.get("query", "")
            summaries.append({
                "artifact_id": artifact["artifact_id"],
                "created_at": artifact["created_at"],
                "query_preview": query[:80] + ("..." if len(query) > 80 else ""),
                "confidence": result_data.get("confidence", "unknown"),
                "user": user,
                "divergence_count": len(result_data.get("divergences", [])),
            })
        except (json.JSONDecodeError, KeyError):
            continue

        if len(summaries) >= n:
            break

    return summaries
