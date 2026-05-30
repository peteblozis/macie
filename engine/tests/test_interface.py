"""
Engine v1 interface tests.

Verifies the public API is stable and behaves correctly under common conditions.
Uses mock adapters so tests are deterministic and require no API keys.
"""

import pytest

from engine.src import (
    consensus,
    ConsensusResult,
    ModelOutput,
    Confidence,
    ModelAdapter,
    AdapterResponse,
)


class MockAdapter(ModelAdapter):
    """A mock adapter that returns a configured response."""

    def __init__(self, model_id: str, text: str = "", error: str | None = None):
        self.model_id = model_id
        self._text = text
        self._error = error

    def invoke(self, query: str, options: dict | None = None) -> AdapterResponse:
        return AdapterResponse(
            text=self._text,
            model_version=f"{self.model_id}-mock-v1",
            latency_ms=42,
            tokens_in=10,
            tokens_out=20,
            error=self._error,
        )


class MockSynthesizer(ModelAdapter):
    """A mock synthesizer that returns a configured JSON response."""

    model_id = "synth-mock"

    def __init__(self, json_response: str):
        self._json = json_response

    def invoke(self, query, options=None):
        return AdapterResponse(
            text=self._json,
            model_version="synth-mock-v1",
            latency_ms=15,
            tokens_in=100,
            tokens_out=50,
            error=None,
        )


VALID_SYNTH_JSON = """{
  "synthesized_answer": "Both models agree the sky is blue due to Rayleigh scattering.",
  "confidence": "high",
  "confidence_rationale": "Models gave substantively identical explanations.",
  "agreement_map": {
    "Sky appears blue": ["mock-a", "mock-b"],
    "Cause is Rayleigh scattering": ["mock-a", "mock-b"]
  },
  "divergences": []
}"""

DIVERGENT_SYNTH_JSON = """{
  "synthesized_answer": "Models disagreed on the primary cause.",
  "confidence": "low",
  "confidence_rationale": "Significant divergence on the mechanism.",
  "agreement_map": {"Sky appears blue": ["mock-a", "mock-b"]},
  "divergences": [
    {
      "claim": "Primary cause of blue color",
      "positions": {
        "mock-a": "Rayleigh scattering",
        "mock-b": "Atmospheric absorption"
      }
    }
  ]
}"""


def _two_model_options(synth_json: str) -> dict:
    """Build options for a two-model roster with a separate synthesizer."""
    return {
        "adapters": {
            "mock-a": MockAdapter("mock-a", text="Response A"),
            "mock-b": MockAdapter("mock-b", text="Response B"),
        },
        "synthesizer_adapter": MockSynthesizer(synth_json),
    }


# --- Tests ---

def test_consensus_returns_result_with_two_models():
    """End-to-end: two mock models, separate synthesizer, valid result."""
    options = _two_model_options(VALID_SYNTH_JSON)
    result = consensus("Why is the sky blue?", ["mock-a", "mock-b"], options)

    assert isinstance(result, ConsensusResult)
    assert result.confidence == Confidence.HIGH
    assert "Rayleigh" in result.synthesized_answer
    assert len(result.divergences) == 0
    assert "Sky appears blue" in result.agreement_map
    # Roster size is 2; synthesizer is not in model_outputs
    assert len(result.model_outputs) == 2


def test_consensus_handles_divergence():
    """Synthesizer reports divergence; engine surfaces it explicitly."""
    options = _two_model_options(DIVERGENT_SYNTH_JSON)
    result = consensus("Why is the sky blue?", ["mock-a", "mock-b"], options)

    assert result.confidence == Confidence.LOW
    assert len(result.divergences) == 1
    assert result.divergences[0].claim == "Primary cause of blue color"
    assert "mock-a" in result.divergences[0].positions
    assert "mock-b" in result.divergences[0].positions


def test_consensus_handles_one_model_failing():
    """One model errors; engine still produces a synthesis from the rest."""
    options = {
        "adapters": {
            "mock-a": MockAdapter("mock-a", text="Sky is blue."),
            "mock-b": MockAdapter("mock-b", error="Connection timeout"),
        },
        "synthesizer_adapter": MockSynthesizer(VALID_SYNTH_JSON),
    }
    result = consensus("Why is the sky blue?", ["mock-a", "mock-b"], options)

    assert isinstance(result, ConsensusResult)
    assert result.telemetry["models_succeeded"] == 1
    assert "Connection timeout" in result.telemetry["errors"]


def test_consensus_handles_all_models_failing():
    """All models fail; engine returns a degraded result without crashing."""
    options = {
        "adapters": {
            "mock-a": MockAdapter("mock-a", error="API down"),
            "mock-b": MockAdapter("mock-b", error="Auth failed"),
        },
    }
    result = consensus("test query", ["mock-a", "mock-b"], options)

    assert isinstance(result, ConsensusResult)
    assert result.confidence == Confidence.LOW
    assert result.telemetry["models_succeeded"] == 0
    assert len(result.telemetry["errors"]) == 2


def test_consensus_handles_invalid_synth_json():
    """Synthesizer returns garbage; engine falls back gracefully."""
    options = {
        "adapters": {
            "mock-a": MockAdapter("mock-a", text="Answer A"),
            "mock-b": MockAdapter("mock-b", text="Answer B"),
        },
        "synthesizer_adapter": MockSynthesizer("This is not JSON at all."),
    }
    result = consensus("test", ["mock-a", "mock-b"], options)

    assert isinstance(result, ConsensusResult)
    assert result.confidence == Confidence.LOW
    # Fallback should surface the raw responses
    assert "mock-a" in result.synthesized_answer or "Answer A" in result.synthesized_answer


def test_consensus_rejects_empty_query():
    """Empty query raises ValueError."""
    with pytest.raises(ValueError, match="non-empty"):
        consensus("", ["claude"])
    with pytest.raises(ValueError, match="non-empty"):
        consensus("   ", ["claude"])


def test_consensus_rejects_empty_roster():
    """Empty roster raises ValueError."""
    with pytest.raises(ValueError, match="at least one"):
        consensus("test", [])


def test_consensus_rejects_unknown_model_id():
    """Unknown model_id with no custom adapter raises ValueError."""
    with pytest.raises(ValueError, match="Unknown model_id"):
        consensus("test", ["nonexistent-model-xyz"])


def test_confidence_enum_values():
    """Confidence enum must have exactly the three documented values."""
    assert Confidence.LOW.value == "low"
    assert Confidence.MEDIUM.value == "medium"
    assert Confidence.HIGH.value == "high"


def test_consensus_telemetry_populated():
    """Telemetry should aggregate latency and tokens across all roster outputs."""
    options = _two_model_options(VALID_SYNTH_JSON)
    result = consensus("test", ["mock-a", "mock-b"], options)

    assert result.telemetry["models_invoked"] == 2
    assert result.telemetry["models_succeeded"] == 2
    assert result.telemetry["total_latency_ms"] > 0
    assert result.telemetry["total_tokens_in"] > 0
    assert result.telemetry["total_tokens_out"] > 0


def test_markdown_fenced_synth_response_parses():
    """Synthesizer sometimes wraps JSON in markdown fences; engine handles it."""
    fenced = "```json\n" + VALID_SYNTH_JSON + "\n```"
    options = {
        "adapters": {
            "mock-a": MockAdapter("mock-a", text="A"),
            "mock-b": MockAdapter("mock-b", text="B"),
        },
        "synthesizer_adapter": MockSynthesizer(fenced),
    }
    result = consensus("test", ["mock-a", "mock-b"], options)
    assert result.confidence == Confidence.HIGH
    assert "Rayleigh" in result.synthesized_answer


def test_synthesizer_id_picks_roster_member():
    """synthesizer_id should select one of the roster members for synthesis."""
    # Use a roster model that returns valid synthesis JSON when called as synthesizer.
    # In real use this is one of the actual models; here we use a mock that
    # serves dual purpose.
    dual_purpose = MockSynthesizer(VALID_SYNTH_JSON)
    dual_purpose.model_id = "dual"

    options = {
        "adapters": {
            "mock-a": MockAdapter("mock-a", text="A"),
            "dual": dual_purpose,
        },
        "synthesizer_id": "dual",
    }
    # When dual is a roster member AND the synthesizer, both its model output
    # and its synthesis output exist. The model output appears in model_outputs;
    # the synthesis result drives confidence/divergences/etc.
    result = consensus("test", ["mock-a", "dual"], options)
    assert isinstance(result, ConsensusResult)
    assert len(result.model_outputs) == 2
