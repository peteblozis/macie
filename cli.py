"""
MACIE CLI
=========

Run MACIE from PowerShell without writing Python.

USAGE
-----

Basic query (Core Shell default):
    python cli.py "Should we use Cloudflare Access or Tunnel?"

Production Shell:
    python cli.py --shell production "Customer-safe answer please"

Read prompt from a file:
    python cli.py --file my_prompt.txt

Show current config (no API call):
    python cli.py --status

JSON output:
    python cli.py --json "your question" > result.json

Recent audit log entries:
    python cli.py --audit
    python cli.py --audit 20

EXIT CODES
----------
    0 = success
    1 = all roster models failed
    2 = configuration error (missing env vars, etc.)
    3 = bad CLI arguments
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

# Make engine importable
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "engine"))

import macie_config as cfg
from audit_log import log_run


# ---------------------------------------------------------------------------
# Status / audit modes (no API needed)
# ---------------------------------------------------------------------------

def cmd_status() -> int:
    """Print current config without calling any API."""
    print("=" * 60)
    print("MACIE v1 — Current Configuration")
    print("=" * 60)
    print(f"Spec roster:       {cfg.SPEC_ROSTER}")
    print(f"Current roster:    {cfg.current_roster()}")
    print(f"Substitution:      {'ACTIVE' if cfg.SUBSTITUTION_ACTIVE else 'inactive'}")
    print()
    print(f"Summary: {cfg.substitution_summary()}")
    if cfg.SUBSTITUTION_ACTIVE:
        print()
        print("Reason:")
        import textwrap
        for line in textwrap.wrap(cfg.SUBSTITUTION_REASON, width=58):
            print(f"  {line}")
    print()
    print("Environment keys:")
    needed = {
        "claude":  "ANTHROPIC_API_KEY",
        "chatgpt": "OPENAI_API_KEY",
        "gemini":  "GEMINI_API_KEY",
    }
    for model_id in cfg.current_roster():
        key = needed.get(model_id)
        if key:
            present = "✓ set" if os.environ.get(key) else "✗ MISSING"
            print(f"  {model_id:8s} needs {key:22s} {present}")
    print("=" * 60)
    return 0


def cmd_audit(n: int) -> int:
    """Print the last N audit log entries."""
    from audit_log import DEFAULT_LOG_PATH
    log_path = Path(DEFAULT_LOG_PATH)
    if not log_path.exists():
        print(f"No audit log yet at {log_path}")
        print("(One will be created on the first real run.)")
        return 0
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        print(f"Audit log is empty: {log_path}")
        return 0
    tail = lines[-n:]
    print("=" * 70)
    print(f"MACIE Audit Log — last {len(tail)} of {len(lines)} entries")
    print(f"Path: {log_path}")
    print("=" * 70)
    for raw in tail:
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            print(f"(unparseable: {raw[:80]})")
            continue
        sub_flag = "SUB" if r.get("substitution_active") else "   "
        ok_flag = "OK " if r.get("success") else "ERR"
        roster = ",".join(r.get("roster", []))
        print(f"{r.get('ts','?')}  [{sub_flag}] [{ok_flag}] "
              f"{r.get('request_id','????'):8s} "
              f"{r.get('shell','?'):10s} "
              f"roster=[{roster}] "
              f"\"{r.get('user_prompt_preview','')[:50]}\"")
    print("=" * 70)
    return 0


# ---------------------------------------------------------------------------
# Run mode — calls into the engine
# ---------------------------------------------------------------------------

def _read_prompt(args) -> str:
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"ERROR: prompt file not found: {path}", file=sys.stderr)
            sys.exit(3)
        return path.read_text(encoding="utf-8").strip()
    if not args.prompt:
        print("ERROR: no prompt. Use a positional arg or --file.", file=sys.stderr)
        print("       Try: python cli.py --help", file=sys.stderr)
        sys.exit(3)
    return " ".join(args.prompt).strip()


def _check_env_keys(roster: list[str]) -> list[str]:
    """Return list of missing-env-var messages, empty if all present."""
    needed = {
        "claude":  "ANTHROPIC_API_KEY",
        "chatgpt": "OPENAI_API_KEY",
        "gemini":  "GEMINI_API_KEY",
    }
    missing = []
    for model_id in roster:
        key = needed.get(model_id)
        if key and not os.environ.get(key):
            missing.append(f"  provider '{model_id}' needs ${key}")
    return missing


def cmd_run(args) -> int:
    prompt = _read_prompt(args)
    roster = cfg.current_roster()

    # Validate env up front
    missing = _check_env_keys(roster)
    if missing:
        print("ERROR: required environment variable(s) missing:", file=sys.stderr)
        for m in missing:
            print(m, file=sys.stderr)
        print(file=sys.stderr)
        print("Set in PowerShell with:", file=sys.stderr)
        for m in missing:
            var = m.split("$")[-1]
            print(f"  $env:{var} = \"<your key>\"", file=sys.stderr)
        return 2

    # Lazy imports so --status and --audit work even without engine deps
    from engine.src.consensus import consensus
    from engine.src.adapters.gemini_adapter import GeminiAdapter

    # Provide GeminiAdapter via the options.adapters override so we don't
    # have to modify the engine's DEFAULT_ADAPTERS registry. The engine
    # supports this natively per consensus.py: _resolve_adapter().
    options = {
        "adapters": {
            "gemini": GeminiAdapter,
        },
    }

    request_id = str(uuid.uuid4())[:8]

    try:
        result = consensus(query=prompt, roster=roster, options=options)
    except Exception as e:
        print(f"ENGINE ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        log_run(
            request_id=request_id, user_prompt=prompt, roster=roster,
            substitution_active=cfg.SUBSTITUTION_ACTIVE,
            substitution_summary=cfg.substitution_summary(),
            shell=args.shell, success=False, note=f"engine error: {e}",
        )
        return 1

    # Pull fields from ConsensusResult — these names come from consensus_types
    # which we haven't seen, so we access them defensively
    synthesized = getattr(result, "synthesized_answer", "(no synthesis)")
    confidence = getattr(result, "confidence", None)
    confidence_str = (
        confidence.value if hasattr(confidence, "value") else str(confidence)
    )
    model_outputs = getattr(result, "model_outputs", [])
    telemetry = getattr(result, "telemetry", {})

    # Determine success — at least one model succeeded
    any_success = any(
        not getattr(o, "error", None) for o in model_outputs
    )

    # Output
    banner = cfg.current_banner()
    if args.json:
        payload = {
            "request_id": request_id,
            "shell": args.shell,
            "substitution_banner": banner,
            "substitution_summary": cfg.substitution_summary(),
            "roster": roster,
            "synthesized_answer": synthesized,
            "confidence": confidence_str,
            "model_outputs": [
                {
                    "model_id": getattr(o, "model_id", "?"),
                    "model_version": getattr(o, "model_version", "?"),
                    "latency_ms": getattr(o, "latency_ms", 0),
                    "error": getattr(o, "error", None),
                    "raw_text_preview": (getattr(o, "raw_text", "") or "")[:200],
                }
                for o in model_outputs
            ],
            "telemetry": telemetry,
        }
        print(json.dumps(payload, indent=2))
    else:
        if banner:
            print(banner)
            print(cfg.substitution_summary())
            print()
        print(synthesized)
        print()
        print("-" * 70)
        print(f"Request ID: {request_id}   Confidence: {confidence_str}   "
              f"Shell: {args.shell}")
        for o in model_outputs:
            status = "ERR" if getattr(o, "error", None) else "OK"
            print(f"  [{status}] {getattr(o, 'model_id', '?'):8s} "
                  f"{getattr(o, 'latency_ms', 0)}ms")
            if getattr(o, "error", None):
                print(f"        error: {o.error}")

    log_run(
        request_id=request_id, user_prompt=prompt, roster=roster,
        substitution_active=cfg.SUBSTITUTION_ACTIVE,
        substitution_summary=cfg.substitution_summary(),
        shell=args.shell, success=any_success, confidence=confidence_str,
    )

    return 0 if any_success else 1


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="macie",
        description="MACIE v1 — Multi-AI Consensus Intelligence Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true",
                      help="show current config and exit (no API call)")
    mode.add_argument("--audit", nargs="?", const=10, type=int, metavar="N",
                      help="show last N audit entries (default 10) and exit")
    p.add_argument("--shell", choices=["core", "production"], default="core",
                   help="which shell context (default: core)")
    p.add_argument("--file", default=None, metavar="PATH",
                   help="read prompt from a file")
    p.add_argument("--json", action="store_true",
                   help="emit result as JSON")
    p.add_argument("prompt", nargs="*",
                   help="the user prompt (omit if using --file)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.status:
        return cmd_status()
    if args.audit is not None:
        return cmd_audit(args.audit)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
