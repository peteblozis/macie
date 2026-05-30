"""
Consensus synthesizer.

Takes a list of ModelOutput records and produces:
  - A synthesized answer
  - A confidence read (low/medium/high) with rationale
  - An agreement map (which models agreed on which claims)
  - A list of explicit divergences

The synthesizer uses one of the models in the roster as the "synthesizer model"
to perform the comparison and unification. This is a deliberate choice: a
deterministic text-overlap algorithm is brittle for natural language, so we
delegate the semantic work to a model — but we instruct that model to produce
structured output that the engine can validate.

The synthesizer model receives ONLY the model outputs, never the original
user query context beyond what was already in the outputs. This keeps the
synthesis focused on the model responses themselves.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .consensus_types import (
    ConsensusResult,
    ModelOutput,
    Divergence,
    Confidence,
)
from .adapters.base import ModelAdapter


SYNTHESIZER_PROMPT = """You are the synthesizer for a multi-AI consensus engine.

Below are responses from {n_models} AI models answering the same query. Your job is to:

1. Identify the key claims each model made.
2. Determine where the models agreed and where they diverged.
3. Produce a unified synthesized answer that captures the consensus.
4. Assess your confidence in the synthesis: "low", "medium", or "high".
5. Provide a brief rationale for your confidence read.

Respond in STRICT JSON with this exact shape (no markdown, no commentary outside the JSON):

{{
  "synthesized_answer": "<the unified answer>",
  "confidence": "<low|medium|high>",
  "confidence_rationale": "<one or two sentences>",
  "agreement_map": {{
    "<claim 1>": ["<model_id>", "<model_id>"],
    "<claim 2>": ["<model_id>"]
  }},
  "divergences": [
    {{
      "claim": "<point of disagreement>",
      "positions": {{
        "<model_id>": "<that model's position>",
        "<model_id>": "<that model's position>"
      }}
    }}
  ]
}}

Confidence guidance:
  - "high": Models substantially agreed; synthesis is straightforward.
  - "medium": Models agreed on most points but diverged on details.
  - "low": Significant disagreement; synthesis required interpretation.

Model responses follow:

{model_blocks}
"""


def _format_model_block(output: ModelOutput) -> str:
    if output.error:
        return f"=== {output.model_id} ({output.model_version}) ===\n[ERROR: {output.error}]\n"
    return f"=== {output.model_id} ({output.model_version}) ===\n{output.raw_text}\n"


def _parse_synth_response(text: str) -> dict[str, Any] | None:
    """
    Parse the synthesizer's JSON response. Tolerant of markdown fences,
    extra preamble text, and Gemini-style responses that wrap JSON in
    natural language before or after the JSON block.
    Returns None on parse failure.
    """
    cleaned = text.strip()

    # Strategy 1: Try direct parse first (cleanest case)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences (```json ... ```)
    if "```" in cleaned:
        # Find content between first ``` block
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

    # Strategy 3: Find the first { and last } and try that substring
    # Handles cases where Gemini adds text before or after the JSON
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    # All strategies failed
    return None


def _fallback_synthesis(outputs: list[ModelOutput]) -> dict[str, Any]:
    """
    Used when the synthesizer model itself fails or returns invalid JSON.
    Returns a degraded but honest result.
    """
    successful = [o for o in outputs if not o.error]
    if not successful:
        return {
            "synthesized_answer": "All models failed to produce a response.",
            "confidence": "low",
            "confidence_rationale": "No successful model responses to synthesize.",
            "agreement_map": {},
            "divergences": [],
        }
    if len(successful) == 1:
        return {
            "synthesized_answer": successful[0].raw_text,
            "confidence": "low",
            "confidence_rationale": (
                f"Only {successful[0].model_id} responded; no cross-model comparison possible."
            ),
            "agreement_map": {"single-model response": [successful[0].model_id]},
            "divergences": [],
        }
    # Multiple successful responses but synthesizer failed: present them raw.
    combined = "\n\n---\n\n".join(
        f"[{o.model_id}]: {o.raw_text}" for o in successful
    )
    return {
        "synthesized_answer": (
            "Synthesizer unavailable. Raw responses from each model below.\n\n" + combined
        ),
        "confidence": "low",
        "confidence_rationale": "Synthesizer model failed; presenting raw responses without unification.",
        "agreement_map": {},
        "divergences": [],
    }


def synthesize(
    outputs: list[ModelOutput],
    synthesizer: ModelAdapter,
    options: dict | None = None,
) -> ConsensusResult:
    """
    Take model outputs and produce a ConsensusResult.

    Args:
        outputs: ModelOutput records from each model in the roster.
        synthesizer: A ModelAdapter to use for the synthesis step.
        options: Optional adapter parameters to pass through.

    Returns:
        ConsensusResult with synthesized answer, confidence, agreement, divergences.
    """
    successful = [o for o in outputs if not o.error]

    # Short-circuit: if zero or one successful responses, synthesis is degenerate.
    if len(successful) < 2:
        parsed = _fallback_synthesis(outputs)
        return _build_result(parsed, outputs)

    # Build the synthesizer prompt and invoke
    model_blocks = "\n\n".join(_format_model_block(o) for o in successful)
    prompt = SYNTHESIZER_PROMPT.format(
        n_models=len(successful),
        model_blocks=model_blocks,
    )

    synth_response = synthesizer.invoke(prompt, options=options)

    if synth_response.error:
        parsed = _fallback_synthesis(outputs)
        parsed["confidence_rationale"] = (
            f"Synthesizer error: {synth_response.error}. Returning fallback synthesis."
        )
        return _build_result(parsed, outputs)

    parsed = _parse_synth_response(synth_response.text)
    if parsed is None:
        parsed = _fallback_synthesis(outputs)
        parsed["confidence_rationale"] = (
            "Synthesizer returned non-JSON output. Returning fallback synthesis."
        )

    return _build_result(parsed, outputs)


def _build_result(parsed: dict, outputs: list[ModelOutput]) -> ConsensusResult:
    """Construct a ConsensusResult from a parsed synthesis dict + raw outputs."""
    # Coerce confidence to enum, defaulting to LOW on unknown values
    raw_confidence = str(parsed.get("confidence", "low")).lower()
    try:
        confidence = Confidence(raw_confidence)
    except ValueError:
        confidence = Confidence.LOW

    divergences = []
    for d in parsed.get("divergences", []):
        if isinstance(d, dict) and "claim" in d and "positions" in d:
            divergences.append(Divergence(
                claim=str(d["claim"]),
                positions={str(k): str(v) for k, v in d["positions"].items()},
            ))

    agreement_map = {}
    for claim, models in parsed.get("agreement_map", {}).items():
        if isinstance(models, list):
            agreement_map[str(claim)] = [str(m) for m in models]

    # Roll up telemetry from all outputs
    total_latency = sum(o.latency_ms for o in outputs)
    total_tokens_in = sum(o.tokens_in for o in outputs)
    total_tokens_out = sum(o.tokens_out for o in outputs)
    errors = [o.error for o in outputs if o.error]

    telemetry = {
        "total_latency_ms": total_latency,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "models_invoked": len(outputs),
        "models_succeeded": len([o for o in outputs if not o.error]),
        "errors": errors,
    }

    return ConsensusResult(
        synthesized_answer=str(parsed.get("synthesized_answer", "")),
        confidence=confidence,
        confidence_rationale=str(parsed.get("confidence_rationale", "")),
        agreement_map=agreement_map,
        divergences=divergences,
        model_outputs=outputs,
        telemetry=telemetry,
    )
