# MACIE SYNTHESIZER PATCH
# =======================
# Run this script from C:\SageForge\macie to patch the synthesizer's
# JSON parser so it handles Gemini's response style correctly.
#
# The problem: Gemini wraps JSON in extra text like:
#   "Here is the JSON response:\n\n```json\n{...}\n```"
# The original parser only strips leading ``` fences.
# This patch makes it find JSON anywhere in the response.
#
# Usage:
#   cd C:\SageForge\macie
#   python patch_synthesizer.py

import re
import shutil
from pathlib import Path

SYNTHESIZER_PATH = Path("engine/src/synthesizer.py")
BACKUP_PATH = Path("engine/src/synthesizer.py.bak")

OLD_FUNCTION = '''def _parse_synth_response(text: str) -> dict[str, Any] | None:
    """
    Parse the synthesizer\'s JSON response. Tolerant of markdown fences.
    Returns None on parse failure.
    """
    cleaned = text.strip()
    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it\'s ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\\n".join(lines)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None'''

NEW_FUNCTION = '''def _parse_synth_response(text: str) -> dict[str, Any] | None:
    """
    Parse the synthesizer\'s JSON response. Tolerant of markdown fences,
    extra preamble text, and Gemini-style responses that wrap JSON in
    natural language before or after the JSON block.
    Returns None on parse failure.
    """
    cleaned = text.strip()

    # Strategy 1: Try direct parse first (cleanest case)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences (```json ... ```)
    if "```" in cleaned:
        # Find content between first ``` block
        fence_match = re.search(r"```(?:json)?\\s*([\\s\\S]*?)```", cleaned)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

    # Strategy 3: Find the first { and last } and try that substring
    # Handles cases where Gemini adds text before or after the JSON
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    # All strategies failed
    return None'''


def patch():
    if not SYNTHESIZER_PATH.exists():
        print(f"ERROR: {SYNTHESIZER_PATH} not found.")
        print("Make sure you are running from C:\\SageForge\\macie")
        return False

    content = SYNTHESIZER_PATH.read_text(encoding="utf-8")

    if OLD_FUNCTION not in content:
        # Check if already patched
        if "Strategy 1: Try direct parse first" in content:
            print("Synthesizer is already patched. Nothing to do.")
            return True
        print("ERROR: Could not find the target function to replace.")
        print("The synthesizer.py file may have changed.")
        print("Send a screenshot of this error to Claude for manual fix.")
        return False

    # Back up original
    shutil.copy(SYNTHESIZER_PATH, BACKUP_PATH)
    print(f"Backup saved: {BACKUP_PATH}")

    # Apply patch
    new_content = content.replace(OLD_FUNCTION, NEW_FUNCTION)
    SYNTHESIZER_PATH.write_text(new_content, encoding="utf-8")
    print(f"Patch applied: {SYNTHESIZER_PATH}")
    print()
    print("The synthesizer can now handle Gemini's JSON response style.")
    print("Run MACIE again and you should get a true consensus answer.")
    return True


if __name__ == "__main__":
    import sys
    # Add re import check to synthesizer
    synth = Path("engine/src/synthesizer.py")
    if synth.exists():
        content = synth.read_text(encoding="utf-8")
        if "import re" not in content:
            # Add re import after existing imports
            content = content.replace("import json", "import json\nimport re")
            synth.write_text(content, encoding="utf-8")
            print("Added 're' import to synthesizer.py")

    success = patch()
    sys.exit(0 if success else 1)
