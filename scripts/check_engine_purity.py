#!/usr/bin/env python3
"""
MACIE engine purity check.

Enforces the rules from the Core/Product Separation Charter v1.0 and MACIE v1
Specification: the /engine directory must contain no references to Core-only
terminology, no personal identifiers, and no imports from shell packages.

Run manually:    python scripts/check_engine_purity.py
Run as pre-commit hook: invoked automatically by .git/hooks/pre-commit
Exit codes: 0 = clean, 1 = violations found
"""

from __future__ import annotations
import sys
import re
from pathlib import Path

# Strings that must never appear in /engine. These are internal/Core terminology
# and personal identifiers per the Charter. Case-insensitive match.
FORBIDDEN_STRINGS = [
    "SageForge",
    "Forge Factory",
    "ForgeShield",
    "Core Extraction",
    "ActionForge",
    "Pete Blozis",
    "Pete Jr",
    "p.blozis",
    "blozis.jr",
    "Pops",
    "Bentley",
    "Loredo",
    "SageMeal",
]

# Import patterns that signal a shell-to-engine dependency leak (i.e. engine
# trying to import from a shell — forbidden direction).
FORBIDDEN_IMPORT_PATTERNS = [
    re.compile(r"from\s+core[_-]?shell"),
    re.compile(r"import\s+core[_-]?shell"),
    re.compile(r"from\s+prod[_-]?shell"),
    re.compile(r"import\s+prod[_-]?shell"),
    re.compile(r"require\s*\(\s*['\"].*core[_-]?shell"),
    re.compile(r"require\s*\(\s*['\"].*prod[_-]?shell"),
]

# File extensions to scan. Skip binaries, lockfiles, and generated artifacts.
SCAN_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
                   ".md", ".txt", ".toml", ".cfg", ".ini", ".env"}

SKIP_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv"}


def scan_engine_directory(engine_root: Path) -> list[str]:
    """Walk /engine and report any rule violations."""
    violations: list[str] = []

    if not engine_root.exists():
        return [f"FATAL: engine directory not found at {engine_root}"]

    for path in engine_root.rglob("*"):
        # Skip directories we don't care about
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            violations.append(f"{path}: could not read ({e})")
            continue

        # Check forbidden strings (case-insensitive)
        lower = content.lower()
        for needle in FORBIDDEN_STRINGS:
            if needle.lower() in lower:
                # Find line numbers for clearer reporting
                for lineno, line in enumerate(content.splitlines(), 1):
                    if needle.lower() in line.lower():
                        violations.append(
                            f"{path}:{lineno}  forbidden term '{needle}' found"
                        )

        # Check forbidden import patterns
        for lineno, line in enumerate(content.splitlines(), 1):
            for pattern in FORBIDDEN_IMPORT_PATTERNS:
                if pattern.search(line):
                    violations.append(
                        f"{path}:{lineno}  forbidden shell import: {line.strip()}"
                    )

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    engine_root = repo_root / "engine"

    print(f"Scanning {engine_root} for purity violations...")
    violations = scan_engine_directory(engine_root)

    if not violations:
        print("✓ Engine purity check PASSED. No violations.")
        return 0

    print(f"\n✗ Engine purity check FAILED. {len(violations)} violation(s):\n")
    for v in violations:
        print(f"  {v}")
    print(
        "\nThe /engine directory must remain free of Core terminology, personal\n"
        "identifiers, and shell imports. See README.md and the Core/Product\n"
        "Separation Charter v1.0 for the binding rules.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
