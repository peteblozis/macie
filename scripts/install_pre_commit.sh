#!/usr/bin/env bash
# Install the engine purity check as a git pre-commit hook.
# Run once after cloning: bash scripts/install_pre_commit.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
    echo "Not inside a git repository. Initialize git first: git init"
    exit 1
fi

HOOK_PATH="${REPO_ROOT}/.git/hooks/pre-commit"

cat > "${HOOK_PATH}" <<'HOOK'
#!/usr/bin/env bash
# MACIE engine purity pre-commit hook.
# Blocks commits that violate the Charter's engine isolation rules.
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
python3 "${REPO_ROOT}/scripts/check_engine_purity.py"
HOOK

chmod +x "${HOOK_PATH}"
echo "✓ Pre-commit hook installed at ${HOOK_PATH}"
echo "  The engine purity check will now run before every commit."
