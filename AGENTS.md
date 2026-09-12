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

`scripts/capture_fixtures.py` reads the panel's status through the real client
(read-only, no writes) and refreshes `tests/fixtures/observed/fw-<firmware>/`,
scrubbing on the way. Run it by hand, never from CI; a new firmware means a new
directory, and `VERIFIED_FIRMWARES` in `const.py` and the README's
`## Verified firmware` table must both grow with it, in that same pull request.

## Quality scale

`custom_components/heatit_wifi_panel/quality_scale.yaml` is the checklist,
and `scripts/check_quality_scale.py` is what makes it one: a `done` rule's
comment starts with the repo-relative path that is its evidence, and deleting
that file fails the check until the yaml says otherwise. Moving or renaming a
test a rule points at means editing the yaml in the same pull request. The
escape hatch is the format itself: `exempt`, with a reason.

## README

`tests/test_readme.py` is what keeps the README from describing an integration
other than the one in the tree, and it is the file to read before editing
`README.md`. It asserts that the `## Verified firmware` table, the observed
fixture directories and `VERIFIED_FIRMWARES` name the same versions; that the
`## Entities` table lists exactly the entities the platform modules declare, so
**a platform ships its README rows in the same pull request as its module**;
that the stated Home Assistant floor is the one `hacs.json` declares; and that
no "beta"/"experimental"/"pending validation" prose appears anywhere — the 0.x
version number carries that message, and saying it in words is a documented
`hacs/default` rejection. The install section is the release runbook's, not
this file's: see `docs/releasing.md`.

## Before a push

Run `scripts/check.sh`. It is the one shared entry point — ruff,
`ruff format --check`, the repository-layout check, the conformance-register
check, mypy strict, the quality-scale check and pytest — and
`.github/workflows/test.yml` calls the same file, so local and CI cannot
drift. `scripts/check.sh lint` and `scripts/check.sh test` run either half.
There are deliberately no git hooks and no pre-commit framework.

Install what it needs with `pip install -r requirements_test.txt`.

## Changelog

`CHANGELOG.md` records **what a user can see or interact with in Home
Assistant** — behaviour, entities, configuration. Nothing else: not the scripts,
not the workflows, not the tooling a contributor runs. Write the entry under
`## [Unreleased]`.

A documentation-only change earns no entry. A conformance-register row flipping
to `verified`, a research note, a spec amendment, a README, this file: each is
already its own record, and restating it in the changelog only means two places
to keep true. Label such a pull request `skip-changelog`, which is what the
pull-request check looks for; CI-only changes take the same label.

A **correction to unreleased work** takes the same label, when the
`## [Unreleased]` entry already describes the corrected behaviour. Code that
disagrees with an entry written in the same release cycle is a bug that never
shipped: Keep a Changelog folds that into the original entry rather than
recording a fix for it, and a reader sees the same sentence before and after. If
the correction changes what the entry *claims*, edit the entry instead — that
touches `CHANGELOG.md` and needs no label at all.

The test: would a **user of the integration** see or do something differently
in Home Assistant? A contributor having to run a script differently is not that,
and neither is "read the document that changed" or "nothing — the entry already
said this". Those do not belong here.
