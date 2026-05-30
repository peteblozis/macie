"""
Gemini adapter — invokes Google's Gemini via the new google-genai SDK.

Reads GEMINI_API_KEY from the environment. The adapter does not log or
persist queries; that is the shell's responsibility.

TEMPORARY CLAUDE SUBSTITUTE — see SPEC_AMENDMENT.md for details.
When Anthropic resolves the PeteAI LLC account, remove gemini from roster.
"""

from __future__ import annotations

import os
import time

from .base import ModelAdapter, AdapterResponse, timed_call


class GeminiAdapter(ModelAdapter):
    """Google Gemini adapter using google-genai SDK."""

    model_id = "gemini"
    default_model = "gemini-2.5-flash"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or self.default_model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    @timed_call
    def invoke(self, query: str, options: dict | None = None) -> AdapterResponse:
        options = options or {}
        start = time.monotonic()

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return AdapterResponse(
                text="",
                model_version=self.model,
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_in=0,
                tokens_out=0,
                error="google-genai SDK not installed; run: pip install google-genai",
            )

        if not self._api_key:
            return AdapterResponse(
                text="",
                model_version=self.model,
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_in=0,
                tokens_out=0,
                error="GEMINI_API_KEY not set",
            )

        client = genai.Client(api_key=self._api_key)

        config = types.GenerateContentConfig(
            max_output_tokens=options.get("max_tokens", 2048),
            temperature=options.get("temperature", 0.3),
        )

        response = client.models.generate_content(
            model=self.model,
            contents=query,
            config=config,
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        text = response.text if hasattr(response, "text") else ""

        tokens_in = 0
        tokens_out = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        return AdapterResponse(
            text=text,
            model_version=self.model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
