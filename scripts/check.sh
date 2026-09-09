#!/usr/bin/env bash
# The one shared entry point. Run this before a push; .github/workflows/test.yml
# calls this file rather than listing the commands, so local and CI cannot
# drift. There are deliberately no git hooks and no pre-commit framework — a
# fresh worktree without hooks installed is exactly the drift we design against.
set -euo pipefail

cd "$(dirname "$0")/.."

ruff check .
ruff format --check .
mypy custom_components scripts
python3 scripts/check_layout.py
