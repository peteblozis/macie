"""
Public data types for the consensus engine.

Kept in their own module so that the synthesizer and other engine components
can import them without circular dependencies on the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Confidence(str, Enum):
    """Synthesizer confidence in the unified result."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ModelOutput:
    """Raw output from a single model, retained for inspection."""
    model_id: str
    model_version: str
    raw_text: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    error: str | None = None


@dataclass
class Divergence:
    """A single point where models disagreed."""
    claim: str
    positions: dict[str, str]  # model_id -> that model's position on the claim


@dataclass
class ConsensusResult:
    """
    The full result of a consensus operation.

    Fields:
        synthesized_answer: The unified response across all models.
        confidence: Synthesizer confidence in the unified result.
        confidence_rationale: Brief textual explanation of the confidence read.
        agreement_map: Per-claim record of which models agreed and which diverged.
        divergences: Explicit list of points where models disagreed.
        model_outputs: Raw outputs from each model.
        telemetry: Structured metrics (latency totals, token totals, timestamps).
    """
    synthesized_answer: str
    confidence: Confidence
    confidence_rationale: str
    agreement_map: dict[str, list[str]]  # claim -> list of model_ids that agreed
    divergences: list[Divergence]
    model_outputs: list[ModelOutput]
    telemetry: dict[str, Any] = field(default_factory=dict)
