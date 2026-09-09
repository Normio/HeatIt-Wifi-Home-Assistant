# AGENTS.md

Home Assistant integration (HACS custom component) for the Heatit WiFi Panel
wall heater, driven over its local HTTP API.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `Normio/HeatIt-Wifi-Home-Assistant`, managed with
the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See
`docs/agents/domain.md`.

### Local device pointer

If a real Heatit WiFi Panel is reachable, its address lives in `.local/device.json`
(gitignored; shape in `.local/device.example.json`). Probe scripts and any
hardware-conformance run read the host from there — never hardcode an IP, and
never commit one.

## Before a push

Run `scripts/check.sh`. It is the one shared entry point — ruff,
`ruff format --check`, mypy strict and the repository-layout check — and
`.github/workflows/test.yml` calls the same file, so local and CI cannot drift.
There are deliberately no git hooks and no pre-commit framework.

Install what it needs with `pip install -r requirements_test.txt`.

## Changelog

Every pull request writes its entry under `## [Unreleased]` in `CHANGELOG.md`.
A pull-request check fails when `CHANGELOG.md` is untouched, unless the pull
request carries the `skip-changelog` label (docs-only or CI-only changes).
