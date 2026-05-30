"""SageForge AI Router — shared types.

Business logic imports only these shapes. It never sees a provider SDK.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Lane = Literal["claude", "chatgpt", "gemini"]
Privacy = Literal["none", "zdr_preferred", "zdr_required"]
FallbackPolicy = Literal["claude_equivalent_only", "lane_only", "cross_lane_allowed"]
TaskType = Literal[
    "coding_review",
    "architecture_review",
    "hard_bug",
    "security_review",
    "complex_refactor",
    "failed_test_analysis",
    "general",
]


@dataclass
class RouterRequest:
    lane: Lane
    task_type: TaskType
    user_prompt: str
    system_prompt: Optional[str] = None
    max_tokens: int = 4000
    require_json: bool = False
    privacy: Privacy = "none"
    fallback_policy: FallbackPolicy = "claude_equivalent_only"
    model_override: Optional[str] = None


@dataclass
class UsageInfo:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


@dataclass
class RouterError:
    message: str
    retryable: bool
    code: Optional[str] = None


@dataclass
class RouterResult:
    ok: bool
    provider: str
    model: str
    text: str
    latency_ms: int
    request_id: str
    json_data: Optional[Any] = None
    usage: Optional[UsageInfo] = None
    error: Optional[RouterError] = None
    fallbacks_attempted: list[str] = field(default_factory=list)
    zdr_required: bool = False
    zdr_satisfied: Optional[bool] = None  # None = unknown
