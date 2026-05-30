"""SageForge AI Router — retry policy and HTTP error classification."""
from __future__ import annotations
import asyncio
import random
from typing import Any, Callable, Awaitable, Literal, TypeVar

Disposition = Literal["success", "retryable", "unavailable", "fatal"]

T = TypeVar("T")


def classify_status(status: int, body: str = "") -> Disposition:
    """Map an HTTP status to a routing disposition.

    402 / auth failures (the exact class of the Anthropic billing block) ->
    unavailable. The router routes AROUND these instead of stalling.
    """
    if 200 <= status < 300:
        return "success"
    if status in (401, 403):
        return "unavailable"
    if status == 402:
        return "unavailable"
    if status == 429:
        return "retryable"
    if status >= 500:
        return "retryable"
    # Some providers return 400 with a billing/account body
    if status == 400 and any(
        kw in body.lower()
        for kw in ("billing", "prepaid", "account", "quota", "t&s", "questionnaire")
    ):
        return "unavailable"
    return "fatal"


async def with_backoff(
    fn: Callable[[int], Awaitable[tuple[Disposition, T]]],
    max_attempts: int = 3,
    base_delay_ms: int = 250,
    _sleep: Callable[[float], Awaitable[None]] | None = None,
) -> tuple[Disposition, T]:
    """Retry fn up to max_attempts for retryable errors with exponential backoff."""
    sleep_fn = _sleep or (lambda s: asyncio.sleep(s))
    last: tuple[Disposition, T] | None = None
    for attempt in range(1, max_attempts + 1):
        last = await fn(attempt)
        disposition, _ = last
        if disposition != "retryable":
            return last
        if attempt < max_attempts:
            delay = (base_delay_ms * (2 ** (attempt - 1)) + random.randint(0, 100)) / 1000
            await sleep_fn(delay)
    return last  # type: ignore[return-value]
