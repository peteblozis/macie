"""SageForge AI Router — OpenRouter adapter (PRIMARY Claude route).

Reaches Claude through OpenRouter with zero dependency on the Anthropic
account/billing classification. Uses the OpenAI-compatible Chat Completions
shape at openrouter.ai/api/v1/chat/completions.
"""
from __future__ import annotations
import json
import os
import time
from typing import Any, Optional

import httpx

from ..adapters.base import ProviderAdapter
from ..config import config, should_escalate
from ..retry import classify_status, with_backoff
from ..types import RouterError, RouterRequest, RouterResult, UsageInfo
from ..utils import extract_json, new_request_id

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterAdapter(ProviderAdapter):
    name = "openrouter"
    lane = "claude"
    zdr_capable = True  # OpenRouter exposes Zero-Data-Retention controls

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = http_client

    def is_configured(self) -> bool:
        return bool(os.environ.get("OPENROUTER_API_KEY"))

    def resolve_model(self, req: RouterRequest) -> str:
        if req.model_override:
            return req.model_override
        return (
            config.openrouter_claude_escalation_model
            if should_escalate(req.task_type)
            else config.openrouter_claude_model
        )

    async def run(self, req: RouterRequest, model: str, request_id: str) -> RouterResult:
        start = time.monotonic()
        key = os.environ.get("OPENROUTER_API_KEY", "")

        messages = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})
        messages.append({"role": "user", "content": req.user_prompt})

        headers: dict[str, str] = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("OPENROUTER_APP_URL", "https://actionforgelabs.com"),
            "X-Title": "SageForge AI Router",
        }
        if req.privacy in ("zdr_required", "zdr_preferred"):
            headers["X-OpenRouter-ZDR"] = "true"

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": req.max_tokens,
        }
        if req.require_json:
            body["response_format"] = {"type": "json_object"}

        async def attempt(n: int):
            try:
                async with (self._client or httpx.AsyncClient()) as client:
                    resp = await client.post(_ENDPOINT, headers=headers, json=body, timeout=60)
                text = resp.text
                return classify_status(resp.status_code, text), {"status": resp.status_code, "text": text}
            except Exception as e:
                return "retryable", {"error": str(e)}

        disposition, val = await with_backoff(attempt)
        latency_ms = int((time.monotonic() - start) * 1000)

        if disposition != "success":
            msg = val.get("error") or val.get("text", "OpenRouter request failed")
            return RouterResult(
                ok=False, provider=self.name, model=model, text="",
                latency_ms=latency_ms, request_id=request_id,
                error=RouterError(message=str(msg), retryable=disposition == "retryable",
                                  code=str(val.get("status", "network"))),
            )

        try:
            parsed = json.loads(val["text"])
        except Exception:
            return RouterResult(
                ok=False, provider=self.name, model=model, text="",
                latency_ms=latency_ms, request_id=request_id,
                error=RouterError(message="Unparseable OpenRouter body", retryable=False, code="parse"),
            )

        content: str = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
        u = parsed.get("usage", {})
        usage = UsageInfo(
            input_tokens=u.get("prompt_tokens"),
            output_tokens=u.get("completion_tokens"),
            total_tokens=u.get("total_tokens"),
        ) if u else None

        return RouterResult(
            ok=True,
            provider=self.name,
            model=parsed.get("model", model),
            text=content,
            json_data=extract_json(content) if req.require_json else None,
            usage=usage,
            latency_ms=latency_ms,
            request_id=request_id,
        )
