#!/usr/bin/env bash
# The one shared entry point. Run this before a push; .github/workflows/test.yml
# calls this file rather than listing the commands, so local and CI cannot
# drift. There are deliberately no git hooks and no pre-commit framework — a
# fresh worktree without hooks installed is exactly the drift we design against.
#
# Two stages, so CI can run the row-independent half once and the
# Home-Assistant-dependent half once per matrix row (§8.7, §9.3):
#
#   scripts/check.sh        everything, in order — what a developer runs
#   scripts/check.sh lint   ruff, ruff format --check, the layout check
#   scripts/check.sh test   mypy strict and pytest, against the installed HA
#
# scripts/check_release.py is not run here: it needs a pushed tag, and only
# .github/workflows/release.yml has one. Its tests run with the rest.
set -euo pipefail

cd "$(dirname "$0")/.."

run_lint() {
  ruff check .
  ruff format --check .
  python3 scripts/check_layout.py
  # Stdlib only, like the layout check, so it belongs to the row-independent
  # half rather than running once per Home Assistant row.
  python3 scripts/check_conformance.py
}

run_tests() {
  mypy custom_components scripts tests
  # Coverage is measured and reported, not gated (§8.7). The one gate — 100 %
  # line coverage of config_flow.py — arrives with the config flow itself.
  python3 -m pytest \
    --quiet \
    --cov=custom_components/heatit_wifi_panel \
    --cov-report=term-missing
}

case "${1:-all}" in
  lint) run_lint ;;
  test) run_tests ;;
  all) run_lint; run_tests ;;
  *) echo "usage: $0 [lint|test]" >&2; exit 2 ;;
esac
