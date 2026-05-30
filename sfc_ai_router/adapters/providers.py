"""SageForge AI Router — remaining provider adapters.

- VercelAiGatewayAdapter  (optional Claude route, Anthropic Messages shape)
- BedrockAdapter          (optional enterprise Claude route, boto3)
- AnthropicDirectAdapter  (present but DISABLED until account is restored)
- OpenAiDirectAdapter     (ChatGPT lane)
"""
from __future__ import annotations
import json
import os
import time
from typing import Any, Optional

import httpx

from ..adapters.base import ProviderAdapter
from ..config import config
from ..retry import classify_status, with_backoff
from ..types import RouterError, RouterRequest, RouterResult, UsageInfo
from ..utils import extract_json, new_request_id


# ── Vercel AI Gateway ──────────────────────────────────────────────────────

class VercelAiGatewayAdapter(ProviderAdapter):
    name = "vercel_ai_gateway"
    lane = "claude"
    zdr_capable = False

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = http_client

    def is_configured(self) -> bool:
        return bool(os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("VERCEL_AI_GATEWAY_API_KEY"))

    def resolve_model(self, req: RouterRequest) -> str:
        return req.model_override or config.vercel_claude_model

    async def run(self, req: RouterRequest, model: str, request_id: str) -> RouterResult:
        start = time.monotonic()
        key = os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("VERCEL_AI_GATEWAY_API_KEY", "")
        base = os.environ.get("VERCEL_AI_GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh")
        body = {
            "model": model, "max_tokens": req.max_tokens,
            "system": req.system_prompt,
            "messages": [{"role": "user", "content": req.user_prompt}],
        }
        async def attempt(n):
            try:
                async with (self._client or httpx.AsyncClient()) as c:
                    r = await c.post(f"{base}/v1/messages", headers={
                        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01"}, json=body, timeout=60)
                return classify_status(r.status_code, r.text), {"status": r.status_code, "text": r.text}
            except Exception as e:
                return "retryable", {"error": str(e)}
        disposition, val = await with_backoff(attempt)
        latency_ms = int((time.monotonic() - start) * 1000)
        if disposition != "success":
            msg = val.get("error") or val.get("text", "Vercel gateway failed")
            return RouterResult(ok=False, provider=self.name, model=model, text="", latency_ms=latency_ms,
                request_id=request_id, error=RouterError(message=str(msg), retryable=disposition=="retryable",
                code=str(val.get("status","network"))))
        try:
            parsed = json.loads(val["text"])
        except Exception:
            return RouterResult(ok=False, provider=self.name, model=model, text="", latency_ms=latency_ms,
                request_id=request_id, error=RouterError(message="Unparseable body", retryable=False, code="parse"))
        content = (parsed.get("content") or [{}])[0].get("text", "")
        u = parsed.get("usage", {})
        usage = UsageInfo(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
            total_tokens=(u.get("input_tokens",0)+u.get("output_tokens",0))) if u else None
        return RouterResult(ok=True, provider=self.name, model=parsed.get("model",model),
            text=content, json_data=extract_json(content) if req.require_json else None,
            usage=usage, latency_ms=latency_ms, request_id=request_id)


# ── AWS Bedrock ────────────────────────────────────────────────────────────

class BedrockAdapter(ProviderAdapter):
    name = "bedrock"
    lane = "claude"
    zdr_capable = True  # Bedrock does not retain prompts for training

    def is_configured(self) -> bool:
        return bool(
            (os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
            or os.environ.get("AWS_PROFILE")
            or os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE")
        )

    def resolve_model(self, req: RouterRequest) -> str:
        return req.model_override or config.bedrock_claude_model_id

    async def run(self, req: RouterRequest, model: str, request_id: str) -> RouterResult:
        import asyncio, time as _time
        start = _time.monotonic()
        try:
            import boto3  # type: ignore
        except ImportError:
            return RouterResult(ok=False, provider=self.name, model=model, text="",
                latency_ms=0, request_id=request_id,
                error=RouterError(message="boto3 not installed", retryable=False, code="sdk_missing"))
        try:
            region = os.environ.get("AWS_REGION", "us-east-1")
            client = boto3.client("bedrock-runtime", region_name=region)
            payload = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": req.max_tokens,
                "system": req.system_prompt,
                "messages": [{"role": "user", "content": [{"type": "text", "text": req.user_prompt}]}],
            })
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.invoke_model(modelId=model, contentType="application/json",
                    accept="application/json", body=payload))
            decoded = json.loads(resp["body"].read())
            content = (decoded.get("content") or [{}])[0].get("text", "")
            u = decoded.get("usage", {})
            usage = UsageInfo(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                total_tokens=u.get("input_tokens",0)+u.get("output_tokens",0)) if u else None
            return RouterResult(ok=True, provider=self.name, model=model, text=content,
                json_data=extract_json(content) if req.require_json else None,
                usage=usage, latency_ms=int((_time.monotonic()-start)*1000), request_id=request_id)
        except Exception as e:
            name = type(e).__name__
            retryable = "Throttl" in name or "ServiceUnavailable" in name
            return RouterResult(ok=False, provider=self.name, model=model, text="",
                latency_ms=int((_time.monotonic()-start)*1000), request_id=request_id,
                error=RouterError(message=str(e), retryable=retryable, code=name))


# ── Anthropic Direct (DISABLED until account is restored) ──────────────────

class AnthropicDirectAdapter(ProviderAdapter):
    name = "anthropic_direct"
    lane = "claude"
    zdr_capable = True

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = http_client

    def is_configured(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def resolve_model(self, req: RouterRequest) -> str:
        return req.model_override or config.anthropic_claude_model

    async def run(self, req: RouterRequest, model: str, request_id: str) -> RouterResult:
        start = time.monotonic()
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        body = {"model": model, "max_tokens": req.max_tokens,
            "system": req.system_prompt,
            "messages": [{"role": "user", "content": req.user_prompt}]}
        async def attempt(n):
            try:
                async with (self._client or httpx.AsyncClient()) as c:
                    r = await c.post("https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                 "Content-Type": "application/json"}, json=body, timeout=60)
                return classify_status(r.status_code, r.text), {"status": r.status_code, "text": r.text}
            except Exception as e:
                return "retryable", {"error": str(e)}
        disposition, val = await with_backoff(attempt)
        latency_ms = int((time.monotonic() - start) * 1000)
        if disposition != "success":
            msg = val.get("error") or val.get("text", "Anthropic direct failed")
            return RouterResult(ok=False, provider=self.name, model=model, text="", latency_ms=latency_ms,
                request_id=request_id, error=RouterError(message=str(msg), retryable=disposition=="retryable",
                code=str(val.get("status","network"))))
        try:
            parsed = json.loads(val["text"])
        except Exception:
            return RouterResult(ok=False, provider=self.name, model=model, text="", latency_ms=latency_ms,
                request_id=request_id, error=RouterError(message="Unparseable body", retryable=False, code="parse"))
        content = (parsed.get("content") or [{}])[0].get("text", "")
        u = parsed.get("usage", {})
        usage = UsageInfo(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
            total_tokens=u.get("input_tokens",0)+u.get("output_tokens",0)) if u else None
        return RouterResult(ok=True, provider=self.name, model=parsed.get("model",model),
            text=content, json_data=extract_json(content) if req.require_json else None,
            usage=usage, latency_ms=latency_ms, request_id=request_id)


# ── OpenAI Direct (ChatGPT lane) ───────────────────────────────────────────

class OpenAiDirectAdapter(ProviderAdapter):
    name = "openai_direct"
    lane = "chatgpt"
    zdr_capable = False

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = http_client

    def is_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def resolve_model(self, req: RouterRequest) -> str:
        return req.model_override or config.openai_model

    async def run(self, req: RouterRequest, model: str, request_id: str) -> RouterResult:
        start = time.monotonic()
        key = os.environ.get("OPENAI_API_KEY", "")
        messages = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})
        messages.append({"role": "user", "content": req.user_prompt})
        body: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": req.max_tokens}
        if req.require_json:
            body["response_format"] = {"type": "json_object"}
        async def attempt(n):
            try:
                async with (self._client or httpx.AsyncClient()) as c:
                    r = await c.post("https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json=body, timeout=60)
                return classify_status(r.status_code, r.text), {"status": r.status_code, "text": r.text}
            except Exception as e:
                return "retryable", {"error": str(e)}
        disposition, val = await with_backoff(attempt)
        latency_ms = int((time.monotonic() - start) * 1000)
        if disposition != "success":
            msg = val.get("error") or val.get("text", "OpenAI failed")
            return RouterResult(ok=False, provider=self.name, model=model, text="", latency_ms=latency_ms,
                request_id=request_id, error=RouterError(message=str(msg), retryable=disposition=="retryable",
                code=str(val.get("status","network"))))
        try:
            parsed = json.loads(val["text"])
        except Exception:
            return RouterResult(ok=False, provider=self.name, model=model, text="", latency_ms=latency_ms,
                request_id=request_id, error=RouterError(message="Unparseable body", retryable=False, code="parse"))
        content = parsed.get("choices",[{}])[0].get("message",{}).get("content","")
        u = parsed.get("usage",{})
        usage = UsageInfo(input_tokens=u.get("prompt_tokens"), output_tokens=u.get("completion_tokens"),
            total_tokens=u.get("total_tokens")) if u else None
        return RouterResult(ok=True, provider=self.name, model=parsed.get("model",model),
            text=content, json_data=extract_json(content) if req.require_json else None,
            usage=usage, latency_ms=latency_ms, request_id=request_id)


# ── Google Gemini via OpenRouter ───────────────────────────────────────────

_OR_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class GeminiOpenRouterAdapter(ProviderAdapter):
    name = "openrouter_gemini"
    lane = "gemini"
    zdr_capable = True

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = http_client

    def is_configured(self) -> bool:
        return bool(os.environ.get("OPENROUTER_API_KEY"))

    def resolve_model(self, req: RouterRequest) -> str:
        return req.model_override or config.openrouter_gemini_model

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
                    resp = await client.post(_OR_ENDPOINT, headers=headers, json=body, timeout=60)
                text = resp.text
                return classify_status(resp.status_code, text), {"status": resp.status_code, "text": text}
            except Exception as e:
                return "retryable", {"error": str(e)}

        disposition, val = await with_backoff(attempt)
        latency_ms = int((time.monotonic() - start) * 1000)

        if disposition != "success":
            msg = val.get("error") or val.get("text", "OpenRouter Gemini request failed")
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
                error=RouterError(message="Unparseable OpenRouter Gemini body", retryable=False, code="parse"),
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
