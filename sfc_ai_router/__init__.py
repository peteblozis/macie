"""SageForge AI Router — public entry point.

Usage from business logic (MACIE / Forge Factory):

    from sfc_ai_router import ai_router, RouterRequest

    result = await ai_router.run(RouterRequest(
        lane="claude",
        task_type="coding_review",
        user_prompt=prompt,
        system_prompt=system,
        max_tokens=4000,
        require_json=True,
        privacy="zdr_required",
        fallback_policy="claude_equivalent_only",
    ))

Business logic NEVER imports a provider adapter directly and NEVER calls
Anthropic. The router is the only AI boundary.
"""
from .types import RouterRequest, RouterResult, RouterError, UsageInfo
from .router import AiRouter
from .health import scan_customer_facing, assert_no_internal_terms
from .adapters import (
    OpenRouterAdapter,
    VercelAiGatewayAdapter,
    BedrockAdapter,
    AnthropicDirectAdapter,
    OpenAiDirectAdapter,
    GeminiOpenRouterAdapter,
)

# Default production router — all adapters registered.
# Unconfigured adapters (missing keys / missing boto3) are skipped automatically.
ai_router = AiRouter(adapters=[
    OpenRouterAdapter(),
    VercelAiGatewayAdapter(),
    BedrockAdapter(),
    AnthropicDirectAdapter(),
    OpenAiDirectAdapter(),
    GeminiOpenRouterAdapter(),
])

__all__ = [
    "ai_router",
    "AiRouter",
    "RouterRequest",
    "RouterResult",
    "RouterError",
    "UsageInfo",
    "OpenRouterAdapter",
    "VercelAiGatewayAdapter",
    "BedrockAdapter",
    "AnthropicDirectAdapter",
    "OpenAiDirectAdapter",
    "GeminiOpenRouterAdapter",
    "scan_customer_facing",
    "assert_no_internal_terms",
]
