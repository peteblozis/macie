"""SageForge AI Router — configuration.

All values read os.environ LIVE via properties. Nothing frozen at import time,
so runtime env changes and test overrides take effect without re-import.
Anthropic-direct is present but DISABLED until the account issue is resolved.
"""
from __future__ import annotations
import os

# Task types that warrant escalation to the stronger (Opus) model.
ESCALATION_TASKS = {
    "architecture_review",
    "hard_bug",
    "security_review",
    "complex_refactor",
    "failed_test_analysis",
}

_DEFAULT_CLAUDE_ORDER = ["openrouter", "vercel_ai_gateway", "bedrock", "anthropic_direct"]
_DEFAULT_CHATGPT_ORDER = ["openai_direct"]
_DEFAULT_GEMINI_ORDER = ["openrouter_gemini"]


def _env(name: str, fallback: str = "") -> str:
    return os.environ.get(name, fallback) or fallback


def _env_bool(name: str, fallback: bool = False) -> bool:
    v = os.environ.get(name, "")
    if not v:
        return fallback
    return v.strip().lower() in ("1", "true", "yes", "on")


def _parse_order(raw: str, fallback: list[str]) -> list[str]:
    if not raw:
        return fallback
    parts = [s.strip() for s in raw.split(",") if s.strip()]
    return parts if parts else fallback


class _Config:
    # Claude lane model policy
    @property
    def openrouter_claude_model(self) -> str:
        return _env("OPENROUTER_CLAUDE_MODEL", "anthropic/claude-sonnet-4.6")

    @property
    def openrouter_claude_escalation_model(self) -> str:
        return _env("OPENROUTER_CLAUDE_ESCALATION_MODEL", "anthropic/claude-opus-4.8")

    @property
    def bedrock_claude_model_id(self) -> str:
        return _env("BEDROCK_CLAUDE_MODEL_ID", "anthropic.claude-sonnet-4-6")

    @property
    def anthropic_claude_model(self) -> str:
        return _env("ANTHROPIC_CLAUDE_MODEL", "claude-sonnet-4-6")

    @property
    def vercel_claude_model(self) -> str:
        return _env("VERCEL_AI_GATEWAY_CLAUDE_MODEL", "anthropic/claude-sonnet-4.6")

    # ChatGPT lane
    @property
    def openai_model(self) -> str:
        return _env("OPENAI_MODEL", "gpt-4.1")

    # Gemini lane (via OpenRouter)
    @property
    def openrouter_gemini_model(self) -> str:
        return _env("OPENROUTER_GEMINI_MODEL", "google/gemini-2.5-flash")

    # Provider order
    @property
    def claude_order(self) -> list[str]:
        return _parse_order(_env("AI_ROUTER_PROVIDER_ORDER"), _DEFAULT_CLAUDE_ORDER)

    @property
    def chatgpt_order(self) -> list[str]:
        return list(_DEFAULT_CHATGPT_ORDER)

    @property
    def gemini_order(self) -> list[str]:
        return list(_DEFAULT_GEMINI_ORDER)

    # Anthropic-direct gate — OFF until account is repaired
    @property
    def enable_anthropic_direct(self) -> bool:
        return _env_bool("ENABLE_ANTHROPIC_DIRECT", False)

    # Privacy / ZDR
    @property
    def require_zdr(self) -> bool:
        return _env_bool("AI_ROUTER_REQUIRE_ZDR", False)

    # Audit
    @property
    def audit_log_path(self) -> str:
        return _env("AI_ROUTER_AUDIT_LOG_PATH", "./logs/ai-router-audit.log")

    @property
    def debug_log_full_prompts(self) -> bool:
        return _env_bool("AI_ROUTER_DEBUG_LOG_FULL_PROMPTS", False)

    @property
    def default_max_tokens(self) -> int:
        return 4000


config = _Config()


def should_escalate(task_type: str) -> bool:
    return task_type in ESCALATION_TASKS


def order_for_lane(lane: str) -> list[str]:
    if lane == "claude":
        order = list(config.claude_order)
        if not config.enable_anthropic_direct:
            order = [p for p in order if p != "anthropic_direct"]
        return order
    if lane == "gemini":
        return config.gemini_order
    return list(config.chatgpt_order)
