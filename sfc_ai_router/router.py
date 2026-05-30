"""SageForge AI Router — core routing engine.

Business logic calls ai_router.run(request). It never learns which provider ran.
"""
from __future__ import annotations
import time
from typing import Optional

from .adapters.base import ProviderAdapter
from .audit import build_record, write_audit
from .config import order_for_lane, config
from .health import ProviderHealth, default_health
from .types import RouterRequest, RouterResult, RouterError
from .utils import new_request_id


class AiRouter:
    def __init__(
        self,
        adapters: list[ProviderAdapter],
        health: Optional[ProviderHealth] = None,
        audit_writer=None,
    ) -> None:
        self._adapters: dict[str, ProviderAdapter] = {a.name: a for a in adapters}
        self._health = health or default_health
        self._audit_writer = audit_writer  # injectable for tests

    async def run(self, req: RouterRequest) -> RouterResult:
        request_id = new_request_id()
        start = time.monotonic()
        zdr_required = config.require_zdr or req.privacy == "zdr_required"

        # Build candidate provider order
        order = order_for_lane(req.lane)
        if req.fallback_policy == "cross_lane_allowed":
            other = "chatgpt" if req.lane == "claude" else "claude"
            order = order + order_for_lane(other)

        fallbacks_attempted: list[str] = []
        last_error: Optional[RouterError] = None

        for name in order:
            adapter = self._adapters.get(name)
            if not adapter:
                continue
            if adapter.lane != req.lane and req.fallback_policy != "cross_lane_allowed":
                continue
            if not adapter.is_configured():
                continue
            if not self._health.is_available(name):
                continue
            if zdr_required and not adapter.zdr_capable:
                fallbacks_attempted.append(f"{name}:skipped_zdr")
                continue

            fallbacks_attempted.append(name)
            model = adapter.resolve_model(req)
            result = await adapter.run(req, model, request_id)

            if result.ok:
                self._health.mark_healthy(name)
                final = RouterResult(
                    ok=True, provider=result.provider, model=result.model,
                    text=result.text, json_data=result.json_data, usage=result.usage,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    request_id=request_id,
                    fallbacks_attempted=fallbacks_attempted,
                    zdr_required=zdr_required,
                    zdr_satisfied=adapter.zdr_capable if zdr_required else None,
                )
                self._write_audit(final, req)
                return final

            # Failure — classify
            last_error = result.error
            code = result.error.code if result.error else ""
            msg = result.error.message if result.error else ""
            if code in ("401", "402", "403") or any(
                kw in msg.lower() for kw in ("billing", "account", "permission", "prepaid", "questionnaire")
            ):
                self._health.mark_unavailable(name)

        # All providers exhausted
        latency_ms = int((time.monotonic() - start) * 1000)
        failure = RouterResult(
            ok=False, provider="none", model="none", text="",
            latency_ms=latency_ms, request_id=request_id,
            error=last_error or RouterError(
                message="No configured/available provider could satisfy the request",
                retryable=False, code="no_provider",
            ),
            fallbacks_attempted=fallbacks_attempted,
            zdr_required=zdr_required,
            zdr_satisfied=False if zdr_required else None,
        )
        self._write_audit(failure, req)
        return failure

    def _write_audit(self, result: RouterResult, req: RouterRequest) -> None:
        try:
            record = build_record(
                result, req.lane, req.task_type,
                prompt_preview=req.user_prompt,
            )
            if self._audit_writer:
                self._audit_writer(record)
            else:
                write_audit(record)
        except Exception:
            pass  # audit must never crash the request path
