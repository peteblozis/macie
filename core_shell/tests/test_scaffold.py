"""
Core Shell tests — Step 4.
Covers submit_query, history, export, audit log, and all error paths.
"""

import os
import tempfile
import pytest

from core_shell.src import main, audit, result_store
from engine.src import ModelAdapter, AdapterResponse, ConsensusResult, Confidence


# --- Mock adapters ---

class _MockModel(ModelAdapter):
    def __init__(self, mid, text):
        self.model_id = mid
        self._text = text

    def invoke(self, query, options=None):
        return AdapterResponse(
            text=self._text, model_version=f"{self.model_id}-test",
            latency_ms=1, tokens_in=1, tokens_out=1,
        )


class _MockSynth(ModelAdapter):
    model_id = "synth"

    def invoke(self, query, options=None):
        return AdapterResponse(
            text='{"synthesized_answer":"unified answer","confidence":"high",'
                 '"confidence_rationale":"models agreed","agreement_map":{},'
                 '"divergences":[]}',
            model_version="synth-test", latency_ms=1, tokens_in=1, tokens_out=1,
        )


def _mock_options():
    return {
        "adapters": {"a": _MockModel("a", "alpha"), "b": _MockModel("b", "beta")},
        "synthesizer_adapter": _MockSynth(),
    }


# --- Fixtures to isolate audit/result storage per test ---

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path):
    """Redirect audit log and results to a temp directory for each test."""
    os.environ["MACIE_AUDIT_LOG_PATH"] = str(tmp_path / "audit" / "test.log")
    os.environ["MACIE_RESULTS_PATH"] = str(tmp_path / "results")
    yield
    del os.environ["MACIE_AUDIT_LOG_PATH"]
    del os.environ["MACIE_RESULTS_PATH"]


# --- Tests ---

def test_submit_query_returns_artifact_id_and_result():
    response = main.submit_query(
        "pete@test.com", "What is the best approach?",
        roster=["a", "b"], options=_mock_options()
    )
    assert "artifact_id" in response
    assert isinstance(response["result"], ConsensusResult)
    assert response["artifact_id"] != ""


def test_submit_query_writes_audit_entries():
    main.submit_query(
        "pete@test.com", "test query",
        roster=["a", "b"], options=_mock_options()
    )
    entries = audit.read_recent(n=10)
    event_types = [e["event"] for e in entries]
    assert "query_submitted" in event_types
    assert "consensus_completed" in event_types


def test_submit_query_saves_retrievable_artifact():
    response = main.submit_query(
        "pete@test.com", "test query",
        roster=["a", "b"], options=_mock_options()
    )
    artifact = result_store.load(response["artifact_id"])
    assert artifact is not None
    assert artifact["result"]["synthesized_answer"] == "unified answer"
    assert artifact["result"]["user"] == "pete@test.com"


def test_submit_query_rejects_unauthenticated():
    with pytest.raises(PermissionError):
        main.submit_query("", "test query")


def test_submit_query_applies_project_context():
    captured = {}

    class _Capture(ModelAdapter):
        def __init__(self, mid):
            self.model_id = mid
        def invoke(self, query, options=None):
            captured["query"] = query
            return AdapterResponse(
                text="captured", model_version="cap",
                latency_ms=1, tokens_in=1, tokens_out=1,
            )

    options = {
        "adapters": {"a": _Capture("a"), "b": _Capture("b")},
        "synthesizer_adapter": _MockSynth(),
    }
    main.submit_query(
        "pete@test.com", "core question",
        project_context={"project": "MACIE", "stage": "build"},
        roster=["a", "b"], options=options,
    )
    assert "Context for this query" in captured["query"]
    assert "project: MACIE" in captured["query"]
    assert "core question" in captured["query"]


def test_get_history_returns_summaries():
    main.submit_query("pete@test.com", "query one", roster=["a", "b"], options=_mock_options())
    main.submit_query("pete@test.com", "query two", roster=["a", "b"], options=_mock_options())
    history = main.get_history("pete@test.com")
    assert len(history) == 2
    assert all("artifact_id" in h for h in history)
    assert all("query_preview" in h for h in history)
    assert all("confidence" in h for h in history)


def test_get_history_filters_by_user():
    main.submit_query("pete@test.com", "pete query", roster=["a", "b"], options=_mock_options())
    main.submit_query("jr@test.com", "jr query", roster=["a", "b"], options=_mock_options())
    pete_history = main.get_history("pete@test.com")
    jr_history = main.get_history("jr@test.com")
    assert len(pete_history) == 1
    assert len(jr_history) == 1
    assert pete_history[0]["user"] == "pete@test.com"
    assert jr_history[0]["user"] == "jr@test.com"


def test_export_artifact_returns_full_artifact():
    response = main.submit_query(
        "pete@test.com", "export test",
        roster=["a", "b"], options=_mock_options()
    )
    exported = main.export_artifact("pete@test.com", response["artifact_id"])
    assert exported["artifact_id"] == response["artifact_id"]
    assert "model_outputs" in exported["result"]
    assert "telemetry" in exported["result"]


def test_export_artifact_raises_on_missing_id():
    with pytest.raises(FileNotFoundError):
        main.export_artifact("pete@test.com", "nonexistent-artifact-id")


def test_get_audit_log_returns_entries():
    main.submit_query("pete@test.com", "audit test", roster=["a", "b"], options=_mock_options())
    log = main.get_audit_log("pete@test.com")
    assert len(log) > 0
    assert all("ts" in e for e in log)
    assert all("event" in e for e in log)
    assert all("user" in e for e in log)


def test_audit_log_is_append_only():
    """Verify log grows with each operation and old entries are preserved."""
    main.submit_query("pete@test.com", "first", roster=["a", "b"], options=_mock_options())
    count_after_first = len(audit.read_recent(n=100))
    main.submit_query("pete@test.com", "second", roster=["a", "b"], options=_mock_options())
    count_after_second = len(audit.read_recent(n=100))
    assert count_after_second > count_after_first
