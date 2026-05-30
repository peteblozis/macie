"""SageForge AI Router — provider adapter ABC."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from ..types import RouterRequest, RouterResult


class ProviderAdapter(ABC):
    name: str
    lane: str  # "claude" or "chatgpt"
    zdr_capable: bool = False

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the required API key/credentials are present."""

    @abstractmethod
    def resolve_model(self, req: RouterRequest) -> str:
        """Return the concrete model identifier for this request."""

    @abstractmethod
    async def run(
        self,
        req: RouterRequest,
        model: str,
        request_id: str,
    ) -> RouterResult:
        """Execute the request and return a normalized RouterResult."""
