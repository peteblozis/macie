"""Real MACIE C software-path tests with explicitly synthetic model fixtures.

These are integration tests, NOT evidence that Claude/OpenAI API calls work.
"""
import json

import pytest

from engine.src import ModelAdapter, AdapterResponse
from prod_shell.src.macie_c import review_document


PUBLIC_TEST_DOCUMENT = (
    "Proposed WP-CLI plan: import 100 draft fsa_lesson posts. Add checks for "
    "wp executable, WordPress core installed, and fsa_lesson post type. "
    "Then import all 100 and declare it safe because preflight passed. "
    "No backup, duplicate IDs, retries or final reconciliation are specified."
)


class StaticReviewer(ModelAdapter):
    def __init__(self, model_id, text, error=None):
        self.model_id = model_id
        self.text = text
        self.error = error
        self.received = []

    def invoke(self, query, options=None):
        self.received.append(query)
        return AdapterResponse(
            text=self.text if not self.error else "",
            model_version=self.model_id + "-FIXTURE-NOT-LIVE",
            latency_ms=1,
            tokens_in=0,
            tokens_out=0,
            error=self.error,
        )


class StaticSynthesizer(ModelAdapter):
    model_id = "fixture-synthesizer"

    def __init__(self):
        self.received = []

    def invoke(self, query, options=None):
        self.received.append(query)
        response = {
            "synthesized_answer": (
                "Do not equate a successful preflight with import safety. "
                "Verify the target WordPress instance; create a backup; "
                "validate the 100 source records; pilot two draft posts; "
                "use stable source IDs for idempotency; import the remainder "
                "with a journal; and reconcile exactly the intended 100 drafts."
            ),
            "confidence": "medium",
            "confidence_rationale": "Both fixture reviewers favor a staged import; they differ on batch size.",
            "agreement_map": {"preflight alone is insufficient": ["claude", "chatgpt"]},
            "divergences": [{
                "claim": "Pilot size",
                "positions": {"claude": "2 posts", "chatgpt": "5 posts"},
            }],
        }
        return AdapterResponse(
            text=json.dumps(response),
            model_version="fixture-synthesizer-NOT-LIVE",
            latency_ms=1, tokens_in=0, tokens_out=0,
        )


def test_document_review_runs_through_real_engine_with_fixture_reviewers():
    reviewer_a = StaticReviewer(
        "claude", "Require backup, transaction journal, duplicates prevention; pilot two drafts."
    )
    reviewer_b = StaticReviewer(
        "chatgpt", "Preflight good, but pilot five drafts, check site and reconciliation."
    )
    synth = StaticSynthesizer()

    result = review_document(
        PUBLIC_TEST_DOCUMENT,
        "Critique this proposal and recommend an implementable next step.",
        options={
            "adapters": {"claude": reviewer_a, "chatgpt": reviewer_b},
            "synthesizer_adapter": synth,
        },
    )

    assert result["edition"] == "MACIE C"
    assert result["status"] == "CONSENSUS_WITH_DIVERGENCES"
    assert result["models_succeeded"] == ["chatgpt", "claude"]
    assert len(synth.received) == 1
    assert PUBLIC_TEST_DOCUMENT in reviewer_a.received[0]
    assert PUBLIC_TEST_DOCUMENT in reviewer_b.received[0]
    assert "source IDs" in result["synthesized_review"]
    assert result["divergences"][0]["claim"] == "Pilot size"

    print("MACIE_C_FIXTURE_RESULT=" + json.dumps({
        "status": result["status"],
        "versions": [o["model_version"] for o in result["model_outputs"]],
        "synthesized_review": result["synthesized_review"],
        "divergences": result["divergences"],
        "execution_type": "synthetic model adapters; real consensus engine code",
    }))


def test_one_failed_model_returns_non_consensus_not_false_success():
    result = review_document(
        PUBLIC_TEST_DOCUMENT,
        options={"adapters": {
            "claude": StaticReviewer("claude", "", error="Provider unreachable"),
            "chatgpt": StaticReviewer("chatgpt", "Preflight needs backup"),
        }},
    )
    assert result["status"] == "NON-CONSENSUS"
    assert result["synthesized_review"] == ""
    assert result["models_succeeded"] == ["chatgpt"]


@pytest.mark.parametrize("document", ["", " ", 7, "x" * 50001])
def test_invalid_documents_rejected(document):
    with pytest.raises(ValueError):
        review_document(document)
