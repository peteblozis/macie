"""
Production Shell — Phase 1 stub.

This stub exists from day one to keep the engine/shell boundary honest. It must:

  1. Import the shared engine successfully.
  2. Have ZERO dependencies on the admin shell, private context, or internal
     terminology.
  3. Run a consensus query end-to-end via the engine.

In Phase 3, this stub becomes the real customer-facing shell. The architectural
boundary it enforces today is what makes that extraction safe.
"""

from engine.src import (
    consensus,
    ConsensusResult,
    ModelAdapter,
    AdapterResponse,
    Confidence,
)


def smoke_test() -> dict:
    """
    Verify the engine is reachable from the production shell with zero
    Core dependencies. Returns a status dict.

    Uses inline mock adapters so the smoke test runs without any API keys
    or network access — the point is to prove the import boundary works.
    """
    status = {
        "engine_imported": True,
        "engine_version": None,
        "consensus_callable": callable(consensus),
        "result_type_available": ConsensusResult is not None,
        "end_to_end_succeeded": False,
    }

    try:
        from engine.src import __version__
        status["engine_version"] = __version__
    except ImportError:
        status["engine_version"] = "unknown"

    class _Mock(ModelAdapter):
        def __init__(self, mid, text):
            self.model_id = mid
            self._text = text

        def invoke(self, query, options=None):
            return AdapterResponse(
                text=self._text,
                model_version=f"{self.model_id}-stub",
                latency_ms=1, tokens_in=1, tokens_out=1,
            )

    class _Synth(ModelAdapter):
        model_id = "synth"

        def invoke(self, query, options=None):
            return AdapterResponse(
                text='{"synthesized_answer":"OK","confidence":"high",'
                     '"confidence_rationale":"stub","agreement_map":{},'
                     '"divergences":[]}',
                model_version="synth-stub",
                latency_ms=1, tokens_in=1, tokens_out=1,
            )

    try:
        result = consensus(
            "smoke test",
            ["a", "b"],
            {
                "adapters": {"a": _Mock("a", "alpha"), "b": _Mock("b", "beta")},
                "synthesizer_adapter": _Synth(),
            },
        )
        status["end_to_end_succeeded"] = (
            isinstance(result, ConsensusResult)
            and result.confidence == Confidence.HIGH
        )
    except Exception as e:
        status["end_to_end_error"] = f"{type(e).__name__}: {e}"

    return status


if __name__ == "__main__":
    import json
    print(json.dumps(smoke_test(), indent=2))
