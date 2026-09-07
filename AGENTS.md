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
