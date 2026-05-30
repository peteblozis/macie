"""
Consensus orchestrator.

The public entry point of the engine. Invokes the roster of models in parallel,
collects their outputs, hands them to the synthesizer, and returns a
ConsensusResult.

The engine has NO knowledge of the user, the shell, or the original purpose
of the query. It receives a query string and a roster; it returns a result.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .consensus_types import (
    ConsensusResult,
    ModelOutput,
    Divergence,
    Confidence,
)
from .adapters import ModelAdapter, ClaudeAdapter, ChatGPTAdapter, GeminiAdapter, RouterAdapter
from .synthesizer import synthesize


# Default registry: maps roster identifiers to adapter factories.
# All three lanes are routed through RouterAdapter → sfc_ai_router, which
# handles provider selection, retries, and fallback. Shells can override by
# passing custom adapters into consensus() via options['adapters'].
DEFAULT_ADAPTERS: dict = {
    "claude": lambda: RouterAdapter("claude"),
    "chatgpt": lambda: RouterAdapter("chatgpt"),
    "gemini": lambda: RouterAdapter("gemini"),
}


def _resolve_adapter(model_id: str, options: dict) -> ModelAdapter:
    """Resolve a roster identifier to a concrete adapter instance."""
    custom = options.get("adapters", {})
    if model_id in custom:
        adapter = custom[model_id]
        if isinstance(adapter, ModelAdapter):
            return adapter
        if isinstance(adapter, type) and issubclass(adapter, ModelAdapter):
            return adapter()

    if model_id in DEFAULT_ADAPTERS:
        return DEFAULT_ADAPTERS[model_id]()

    raise ValueError(
        f"Unknown model_id '{model_id}'. Known: {list(DEFAULT_ADAPTERS.keys())}. "
        f"Pass a custom adapter via options['adapters'] to use others."
    )


def _invoke_one(adapter: ModelAdapter, query: str, options: dict) -> ModelOutput:
    """Invoke a single adapter and normalize the response into a ModelOutput."""
    response = adapter.invoke(query, options=options)
    return ModelOutput(
        model_id=adapter.model_id,
        model_version=response.model_version,
        raw_text=response.text,
        latency_ms=response.latency_ms,
        tokens_in=response.tokens_in,
        tokens_out=response.tokens_out,
        error=response.error,
    )


def consensus(
    query: str,
    roster: list[str],
    options: dict[str, Any] | None = None,
) -> ConsensusResult:
    """
    Run a consensus operation across the model roster.

    Args:
        query: The user query to evaluate.
        roster: List of model identifiers to invoke (e.g. ["claude", "chatgpt"]).
        options: Optional parameters:
            - max_tokens (int): max tokens per model response, default 2048
            - temperature (float): default 0.3
            - timeout_ms (int): per-model timeout in ms, default 60000
            - adapters (dict): {model_id: ModelAdapter} for custom adapters
            - synthesizer_id (str): which roster member synthesizes; default
              is the first successful model in roster order

    Returns:
        ConsensusResult with synthesized answer, confidence, divergences,
        per-model outputs, and telemetry.

    Raises:
        ValueError: If the roster is empty, the query is empty, or the roster
            contains unknown model_ids without a custom adapter override.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not roster:
        raise ValueError("roster must contain at least one model_id")

    options = options or {}

    adapters = [_resolve_adapter(m, options) for m in roster]

    outputs: list[ModelOutput] = [None] * len(adapters)  # type: ignore
    with ThreadPoolExecutor(max_workers=len(adapters)) as pool:
        future_to_idx = {
            pool.submit(_invoke_one, adapter, query, options): idx
            for idx, adapter in enumerate(adapters)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            outputs[idx] = future.result()

    # Resolve synthesizer. Three sources, in priority order:
    #   1. options["synthesizer_adapter"]: a separate adapter instance NOT in
    #      the roster. Its output is NOT included in model_outputs.
    #   2. options["synthesizer_id"]: name of a roster member to double as
    #      synthesizer. Its output IS in model_outputs.
    #   3. Default: first successful roster member.
    synthesizer_adapter: ModelAdapter | None = options.get("synthesizer_adapter")

    if synthesizer_adapter is None:
        synthesizer_id = options.get("synthesizer_id")
        if synthesizer_id:
            for adapter in adapters:
                if adapter.model_id == synthesizer_id:
                    synthesizer_adapter = adapter
                    break

    if synthesizer_adapter is None:
        for adapter, output in zip(adapters, outputs):
            if not output.error:
                synthesizer_adapter = adapter
                break

    if synthesizer_adapter is None:
        return ConsensusResult(
            synthesized_answer="All models in the roster failed to respond.",
            confidence=Confidence.LOW,
            confidence_rationale="No successful model responses available for synthesis.",
            agreement_map={},
            divergences=[],
            model_outputs=outputs,
            telemetry={
                "total_latency_ms": sum(o.latency_ms for o in outputs),
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "models_invoked": len(outputs),
                "models_succeeded": 0,
                "errors": [o.error for o in outputs if o.error],
            },
        )

    return synthesize(outputs, synthesizer_adapter, options=options)
