"""
Claude adapter — invokes Anthropic's Claude via the official SDK.

Reads ANTHROPIC_API_KEY from the environment. The adapter does not log or
persist queries; that is the shell's responsibility.
"""

from __future__ import annotations

import os
import time

from .base import ModelAdapter, AdapterResponse, timed_call


class ClaudeAdapter(ModelAdapter):
    """Anthropic Claude adapter."""

    model_id = "claude"
    default_model = "claude-opus-4-7"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or self.default_model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    @timed_call
    def invoke(self, query: str, options: dict | None = None) -> AdapterResponse:
        options = options or {}
        start = time.monotonic()

        try:
            import anthropic
        except ImportError:
            return AdapterResponse(
                text="",
                model_version=self.model,
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_in=0,
                tokens_out=0,
                error="anthropic SDK not installed; run: pip install anthropic",
            )

        if not self._api_key:
            return AdapterResponse(
                text="",
                model_version=self.model,
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_in=0,
                tokens_out=0,
                error="ANTHROPIC_API_KEY not set",
            )

        client = anthropic.Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=options.get("max_tokens", 2048),
            temperature=options.get("temperature", 0.3),
            messages=[{"role": "user", "content": query}],
            timeout=options.get("timeout_ms", 60000) / 1000.0,
        )

        latency_ms = int((time.monotonic() - start) * 1000)

        # Concatenate text blocks from the response
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        text = "\n".join(text_parts)

        return AdapterResponse(
            text=text,
            model_version=response.model,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )
