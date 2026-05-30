"""
RouterAdapter — bridges MACIE's synchronous ModelAdapter interface to
sfc_ai_router's async AiRouter. One instance per lane (claude/chatgpt/gemini).

The adapter is called from ThreadPoolExecutor threads (see consensus.py), so
asyncio.run() is safe: each thread starts without a running event loop.
"""

from __future__ import annotations

import asyncio

from .base import ModelAdapter, AdapterResponse, timed_call


def _default_router():
    from sfc_ai_router import ai_router
    return ai_router


class RouterAdapter(ModelAdapter):
    """MACIE adapter that dispatches through sfc_ai_router for a given lane."""

    def __init__(self, lane: str, router=None):
        self.model_id = lane
        self._lane = lane
        self._router = router  # injectable for tests

    @timed_call
    def invoke(self, query: str, options: dict | None = None) -> AdapterResponse:
        from sfc_ai_router import RouterRequest

        options = options or {}
        router = self._router if self._router is not None else _default_router()

        req = RouterRequest(
            lane=self._lane,
            task_type=options.get("task_type", "general"),
            user_prompt=query,
            system_prompt=options.get("system_prompt"),
            max_tokens=options.get("max_tokens", 2048),
        )

        result = asyncio.run(router.run(req))

        tokens_in = 0
        tokens_out = 0
        if result.usage:
            tokens_in = result.usage.input_tokens or 0
            tokens_out = result.usage.output_tokens or 0

        if result.ok:
            return AdapterResponse(
                text=result.text,
                model_version=result.model,
                latency_ms=result.latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )

        error_msg = result.error.message if result.error else "Router returned failure"
        return AdapterResponse(
            text="",
            model_version=result.model,
            latency_ms=result.latency_ms,
            tokens_in=0,
            tokens_out=0,
            error=error_msg,
        )
