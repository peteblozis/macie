"""
ChatGPT adapter — invokes OpenAI's ChatGPT via the official SDK.

Reads OPENAI_API_KEY from the environment.
"""

from __future__ import annotations

import os
import time

from .base import ModelAdapter, AdapterResponse, timed_call


class ChatGPTAdapter(ModelAdapter):
    """OpenAI ChatGPT adapter."""

    model_id = "chatgpt"
    default_model = "gpt-4o"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or self.default_model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    @timed_call
    def invoke(self, query: str, options: dict | None = None) -> AdapterResponse:
        options = options or {}
        start = time.monotonic()

        try:
            from openai import OpenAI
        except ImportError:
            return AdapterResponse(
                text="",
                model_version=self.model,
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_in=0,
                tokens_out=0,
                error="openai SDK not installed; run: pip install openai",
            )

        if not self._api_key:
            return AdapterResponse(
                text="",
                model_version=self.model,
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_in=0,
                tokens_out=0,
                error="OPENAI_API_KEY not set",
            )

        client = OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": query}],
            max_tokens=options.get("max_tokens", 2048),
            temperature=options.get("temperature", 0.3),
            timeout=options.get("timeout_ms", 60000) / 1000.0,
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        text = response.choices[0].message.content or ""

        return AdapterResponse(
            text=text,
            model_version=response.model,
            latency_ms=latency_ms,
            tokens_in=response.usage.prompt_tokens if response.usage else 0,
            tokens_out=response.usage.completion_tokens if response.usage else 0,
        )
