"""
MACIE Interactive Mode
======================
Run: python macie_interactive.py
Type your question at the prompt and hit Enter.
"""

from __future__ import annotations
import json
import os
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "engine"))

import macie_config as cfg
from audit_log import log_run

BANNER = "=" * 70
WELCOME = f"""{BANNER}
  MACIE - Multi-AI Consensus Intelligence Engine
  Interactive Mode

  Type your question and hit Enter.
  Commands: /help  /status  /audit  /shell core  /shell prod  /quit
{BANNER}"""

SYNTHESIS_PROMPT = """You are the synthesis engine for MACIE, a Multi-AI Consensus Intelligence Engine.

Below are responses from two AI models answering the same question.
Your job is to:
1. Identify where they agree
2. Identify where they differ
3. Produce ONE unified synthesized answer that is stronger than either alone
4. Give a confidence rating: high (strong agreement), medium (partial agreement), low (significant disagreement)

USER QUESTION: {question}

MODEL A (Gemini) RESPONSE:
{response_a}

MODEL B (ChatGPT) RESPONSE:
{response_b}

Write your synthesis now. Start directly with the synthesized answer.
Format:
SYNTHESIZED ANSWER:
[your unified answer here]

CONFIDENCE: [high/medium/low]
RATIONALE: [one sentence explaining your confidence]
AGREEMENTS: [key points both models agreed on]
DIVERGENCES: [key points where they differed, if any]"""


def check_env() -> list[str]:
    needed = {"gemini": "GEMINI_API_KEY", "chatgpt": "OPENAI_API_KEY"}
    missing = []
    for model_id in cfg.current_roster():
        key = needed.get(model_id)
        if key and not os.environ.get(key):
            missing.append((model_id, key))
    return missing


def call_gemini(query: str) -> tuple[str, str | None]:
    """Returns (text, error)"""
    try:
        from google import genai
        from google.genai import types
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return "", "GEMINI_API_KEY not set"
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(max_output_tokens=2048, temperature=0.3)
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=query, config=config)
        return response.text or "", None
    except Exception as e:
        return "", str(e)


def call_chatgpt(query: str) -> tuple[str, str | None]:
    """Returns (text, error)"""
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return "", "OPENAI_API_KEY not set"
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": query}],
            max_tokens=2048,
            temperature=0.3,
        )
        return response.choices[0].message.content or "", None
    except Exception as e:
        return "", str(e)


def synthesize_with_chatgpt(question: str, response_a: str, response_b: str) -> str:
    """Use ChatGPT to synthesize the two responses into one."""
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        prompt = SYNTHESIS_PROMPT.format(
            question=question,
            response_a=response_a,
            response_b=response_b,
        )
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return None


def run_query(query: str, shell: str) -> bool:
    request_id = str(uuid.uuid4())[:8]
    print()
    print(f"  Step 1/3: Asking Gemini ...")
    gemini_text, gemini_error = call_gemini(query)

    print(f"  Step 2/3: Asking ChatGPT ...")
    chatgpt_text, chatgpt_error = call_chatgpt(query)

    if gemini_error and chatgpt_error:
        print(f"\n  Both models failed.")
        print(f"  Gemini error: {gemini_error}")
        print(f"  ChatGPT error: {chatgpt_error}")
        log_run(request_id=request_id, user_prompt=query,
                roster=cfg.current_roster(),
                substitution_active=cfg.SUBSTITUTION_ACTIVE,
                substitution_summary=cfg.substitution_summary(),
                shell=shell, success=False)
        return False

    print(f"  Step 3/3: Synthesizing consensus ...")
    synthesis = None

    if gemini_text and chatgpt_text:
        synthesis = synthesize_with_chatgpt(query, gemini_text, chatgpt_text)

    print()
    print(BANNER)
    if cfg.SUBSTITUTION_ACTIVE:
        print(f"  {cfg.SUBSTITUTION_BANNER}")
        print()

    if synthesis:
        print(synthesis)
        confidence = "medium"
        if "CONFIDENCE: high" in synthesis.upper():
            confidence = "high"
        elif "CONFIDENCE: low" in synthesis.lower():
            confidence = "low"
    else:
        # Fallback — show both but label clearly
        print("  NOTE: Synthesis unavailable. Showing both model responses.")
        print()
        if gemini_text:
            print(f"  [Gemini]:\n{gemini_text}")
            print()
        if chatgpt_text:
            print(f"  [ChatGPT]:\n{chatgpt_text}")
        confidence = "low"

    print()
    print("-" * 70)
    g_status = "ERR" if gemini_error else "OK"
    c_status = "ERR" if chatgpt_error else "OK"
    print(f"  Request: {request_id}   Confidence: {confidence}   Shell: {shell}")
    print(f"    [{g_status}] gemini    [{c_status}] chatgpt")
    print(BANNER)
    print()

    log_run(request_id=request_id, user_prompt=query,
            roster=cfg.current_roster(),
            substitution_active=cfg.SUBSTITUTION_ACTIVE,
            substitution_summary=cfg.substitution_summary(),
            shell=shell, success=True, confidence=confidence)
    return True


def cmd_help():
    print("""
  Commands:
    /help          show this help
    /status        show current config
    /audit         show last 10 runs
    /shell core    switch to Core Shell
    /shell prod    switch to Production Shell
    /quit          exit
    (anything else) = your question to MACIE
""")


def cmd_status():
    print(f"\n  Spec roster:    {cfg.SPEC_ROSTER}")
    print(f"  Current roster: {cfg.current_roster()}")
    print(f"  Substitution:   {'ACTIVE' if cfg.SUBSTITUTION_ACTIVE else 'inactive'}")
    print(f"  Summary:        {cfg.substitution_summary()}\n")


def cmd_audit():
    from audit_log import DEFAULT_LOG_PATH
    log_path = Path(DEFAULT_LOG_PATH)
    if not log_path.exists():
        print("\n  (No audit log yet.)\n")
        return
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    print(f"\n  Last {min(10, len(lines))} entries:\n")
    for raw in lines[-10:]:
        try:
            r = json.loads(raw)
            sub = "SUB" if r.get("substitution_active") else "   "
            ok = "OK " if r.get("success") else "ERR"
            print(f"  {r.get('ts','?')[:19]}  [{sub}][{ok}]  "
                  f"\"{r.get('user_prompt_preview','')[:50]}\"")
        except Exception:
            continue
    print()


def main():
    print(WELCOME)
    print()
    if cfg.SUBSTITUTION_ACTIVE:
        print(f"  {cfg.SUBSTITUTION_BANNER}")
        print(f"  {cfg.substitution_summary()}")
    else:
        print(f"  Running spec roster: {cfg.SPEC_ROSTER}")
    print()

    missing = check_env()
    if missing:
        print("  Missing API keys:")
        for model_id, key in missing:
            print(f"    {model_id} needs ${key}")
        print()
        input("  Press Enter to exit.")
        return

    shell = "core"
    while True:
        try:
            line = input(f"\n  [{shell}] Your question (or /help): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Goodbye, Pops.\n")
            return

        if not line:
            continue

        if line.startswith("/"):
            cmd = line.lower()
            if cmd in ("/quit", "/exit", "/q"):
                print("\n  Goodbye, Pops.\n")
                return
            elif cmd == "/help":
                cmd_help()
            elif cmd == "/status":
                cmd_status()
            elif cmd == "/audit":
                cmd_audit()
            elif cmd.startswith("/shell"):
                parts = cmd.split()
                if len(parts) == 2 and parts[1] in ("core", "prod", "production"):
                    shell = "production" if parts[1].startswith("prod") else "core"
                    print(f"\n  Shell: {shell}\n")
                else:
                    print("\n  Usage: /shell core  OR  /shell prod\n")
            else:
                print(f"\n  Unknown command. Try /help\n")
            continue

        run_query(line, shell)


if __name__ == "__main__":
    main()
