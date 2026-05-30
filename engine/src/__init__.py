"""
Multi-AI Consensus Intelligence Engine.

This package is the shared engine. It contains no dependencies on any shell
and no references to any private context. It must remain importable by any
shell that adheres to its public interface.
"""

from .consensus import consensus, DEFAULT_ADAPTERS
from .consensus_types import (
    ConsensusResult,
    ModelOutput,
    Divergence,
    Confidence,
)
from .adapters import ModelAdapter, AdapterResponse, ClaudeAdapter, ChatGPTAdapter, GeminiAdapter, RouterAdapter

__all__ = [
    "consensus",
    "DEFAULT_ADAPTERS",
    "ConsensusResult",
    "ModelOutput",
    "Divergence",
    "Confidence",
    "ModelAdapter",
    "AdapterResponse",
    "ClaudeAdapter",
    "ChatGPTAdapter",
    "GeminiAdapter",
    "RouterAdapter",
]
__version__ = "0.2.0"
