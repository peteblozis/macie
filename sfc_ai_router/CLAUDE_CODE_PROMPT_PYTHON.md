# CLAUDE CODE — MACIE PYTHON INTEGRATION (18-STEP EXECUTION)
#
# Run this in Claude Code in the directory C:\SageForge\macie
# The router package (folder sfc_ai_router/) is pre-built and 11/11 tested.
# Drop the sfc_ai_router/ folder into C:\SageForge\macie\ first, then run this.

You are integrating a pre-built, 11/11-tested Python AI router into MACIE.
Detection + wiring + live verification only. Do not redesign the router.
Do not declare MACIE fixed until the original 19 MACIE tests pass through it.

## Hard rules (non-negotiable)
- Two AI lanes only: Claude and ChatGPT. No Gemini, Grok, Perplexity.
- NOTE: gemini_adapter.py EXISTS in engine/src/adapters/ but is NOT in MACIE v1
  scope. Do not wire it into the router. Flag it to Pete for a separate decision.
- OpenRouter Claude Sonnet 4.6 = default Claude route. Opus 4.8 = escalation only.
- Anthropic-direct = disabled/lowest priority (ENABLE_ANTHROPIC_DIRECT unset).
- Vercel Gateway + Bedrock = optional; only used if their keys exist.
- Never print, log, or commit API keys. Never log full prompts/responses by default.
- No production deploy. No merge to main. Work on branch feature/ai-router-recovery.

## Steps

### Step 1 — Inspect + confirm stack
```
cd C:\SageForge\macie
dir
Get-Content pyproject.toml
```
Confirm: Python 3.11+, pytest + pytest-asyncio, test paths at
engine/tests, core_shell/tests, prod_shell/tests.

### Step 2 — Read the key call sites (before touching anything)
```
Get-Content engine\src\adapters\base.py
Get-Content engine\src\adapters\claude_adapter.py
Get-Content engine\src\adapters\chatgpt_adapter.py
Get-Content engine\src\consensus.py
```
Understand:
- What interface does ModelAdapter (base.py) expose?
- How does claude_adapter.py currently call Anthropic?
- How does consensus.py select and call adapters?

### Step 3 — Create feature branch
```
git checkout -b feature/ai-router-recovery
```

### Step 4 — Install router dependencies
```
pip install httpx --break-system-packages
```
(Or add httpx to pyproject.toml [project.dependencies] and re-run pip install -e .)
If a lockfile exists: prefer pip install -r requirements.txt first.

### Step 5 — Create RouterAdapter (MACIE bridge class)
Create engine/src/adapters/router_adapter.py that:
- Inherits from ModelAdapter (matching the existing base.py interface exactly)
- Wraps sfc_ai_router.ai_router.run() internally
- Maps ModelAdapter's call signature to RouterRequest fields:
    lane = "claude"
    task_type = infer from context (default "general"; use "coding_review" for
                synthesis tasks, "hard_bug" for error analysis, etc.)
    fallback_policy = "claude_equivalent_only"
- Returns whatever type ModelAdapter.run() currently returns (match the shape)
- Never exposes the router internals to callers

### Step 6 — Wire RouterAdapter into MACIE
- In consensus.py (or wherever adapters are instantiated): replace the
  ClaudeAdapter instantiation with RouterAdapter.
- ChatGPT lane stays as-is (chatgpt_adapter.py calls OpenAI directly and
  is NOT blocked — leave it alone unless it also needs routing).
- Preserve the two-lane rule. Do not add Gemini to dispatch.
- Do not change any business logic except the adapter swap.

### Step 7 — Set OPENROUTER_API_KEY (never in repo)
PowerShell session: $env:OPENROUTER_API_KEY="sk-or-v3-..."
Or add to .env file (already in .gitignore per repo pattern).
Verify it loaded: echo $env:OPENROUTER_API_KEY (confirm non-empty, do not log value).

### Step 8 — Live smoke test (Step 16 of the 18-rule spec)
Run a single non-sensitive prompt through the router:
```python
import asyncio
from sfc_ai_router import ai_router, RouterRequest

async def smoke():
    r = await ai_router.run(RouterRequest(
        lane="claude", task_type="general",
        user_prompt="Reply with the single word: OK"
    ))
    print(f"ok={r.ok} provider={r.provider} model={r.model} latency={r.latency_ms}ms")
    assert r.ok, f"Smoke test failed: {r.error}"
    assert r.provider == "openrouter", f"Expected openrouter, got {r.provider}"
    print("SMOKE TEST PASSED")

asyncio.run(smoke())
```
Print only provider/model/latency. NEVER print the key or full response.

### Step 9 — Run original 19 MACIE tests through the router
```
python -m pytest engine/tests core_shell/tests prod_shell/tests -v
```
These must pass through the RouterAdapter (OpenRouter as Claude provider).
If any fail, document: test name, error, whether it's a router issue or a
pre-existing issue.

### Step 10 — Run the router's own test suite
```
python -m pytest sfc_ai_router/tests/ -v
```
All 11 must pass (they are offline/mocked and should pass immediately).

## Deliver back to Pete (Step 18)
1. Stack confirmed: Python 3.11, pytest-asyncio, pyproject.toml
2. Files changed: list them
3. Files created: engine/src/adapters/router_adapter.py + any others
4. Call sites replaced: which files, which lines
5. Env vars to set: OPENROUTER_API_KEY (minimum); see sfc_ai_router/.env.example
6. Exact key-set command: $env:OPENROUTER_API_KEY="sk-or-..." (session)
   or add to .env file
7. Test command: python -m pytest engine/tests core_shell/tests prod_shell/tests -v
8. Test results: pass/fail count for the 19 MACIE tests
9. Failed tests: name, error, root cause for any failures
10. MACIE actually unblocked? YES only if smoke test passed AND 19 tests pass
    through OpenRouter. Not declared fixed on router tests alone.
11. Rollback: git checkout -- . && git checkout main && git branch -d feature/ai-router-recovery
    (router folder is additive; removing it fully reverts)
12. Security notes: keys in .env (gitignored), audit log at ./logs/ai-router-audit.log,
    no prompts logged by default, no secrets in audit records
13. Anthropic self-service: Console error was "Teams cannot upgrade to prepaid
    without submitting a T&S Questionnaire answer." That questionnaire may unlock
    prepaid immediately — try it in the Console in parallel. Independent of router.

## Flag for Pete
gemini_adapter.py exists in engine/src/adapters/. MACIE v1 spec says Claude +
ChatGPT only. Confirm with Pete whether Gemini should be deactivated from dispatch
or kept dormant. Do not remove it unilaterally.
