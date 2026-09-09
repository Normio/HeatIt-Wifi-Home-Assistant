#!/usr/bin/env bash
# The one shared entry point. Run this before a push; .github/workflows/test.yml
# calls this file rather than listing the commands, so local and CI cannot
# drift. There are deliberately no git hooks and no pre-commit framework — a
# fresh worktree without hooks installed is exactly the drift we design against.
#
# scripts/check_release.py is not run here: it needs a pushed tag, and only
# .github/workflows/release.yml has one. Its tests run with the rest.
set -euo pipefail

cd "$(dirname "$0")/.."

ruff check .
ruff format --check .
mypy custom_components scripts tests
python3 scripts/check_layout.py
pytest
