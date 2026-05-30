"""Model adapters for the consensus engine."""

from .base import ModelAdapter, AdapterResponse, timed_call
from .claude_adapter import ClaudeAdapter
from .chatgpt_adapter import ChatGPTAdapter
from .gemini_adapter import GeminiAdapter
from .router_adapter import RouterAdapter

__all__ = [
    "ModelAdapter",
    "AdapterResponse",
    "timed_call",
    "ClaudeAdapter",
    "ChatGPTAdapter",
    "GeminiAdapter",
    "RouterAdapter",
]
