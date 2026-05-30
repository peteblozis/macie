"""
Model adapter contract.

Every model adapter implements the same interface so the consensus engine
can invoke any roster of models uniformly. Adapters live in this package
and must not depend on any shell.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AdapterResponse:
    """Standard response shape returned by every adapter."""

    text: str
    model_version: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    error: str | None = None


class ModelAdapter(ABC):
    """
    Base class for a model adapter.

    Subclasses implement invoke(). The engine never instantiates a model
    directly; it always goes through an adapter.
    """

    model_id: str = ""

    @abstractmethod
    def invoke(self, query: str, options: dict | None = None) -> AdapterResponse:
        """
        Send the query to the model and return a normalized AdapterResponse.

        Adapters MUST:
          - Never raise on a remote API error; capture the error in the
            AdapterResponse.error field and return normally so the engine
            can still synthesize a result from the remaining models.
          - Measure latency in milliseconds.
          - Report tokens_in and tokens_out (zero if unknown).
          - Include the model version string.
        """


def timed_call(fn):
    """
    Decorator for adapter invoke() methods. Wraps execution in a try/except,
    measures latency, and returns an AdapterResponse with error set if the
    call raises. Keeps adapters from leaking exceptions to the engine.
    """

    def wrapper(self, query: str, options: dict | None = None) -> AdapterResponse:
        start = time.monotonic()
        try:
            result = fn(self, query, options)
            return result
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResponse(
                text="",
                model_version="unknown",
                latency_ms=latency_ms,
                tokens_in=0,
                tokens_out=0,
                error=type(e).__name__ + ": " + str(e),
            )

    return wrapper
