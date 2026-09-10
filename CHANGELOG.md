# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The `heatit_wifi_panel` integration package with its manifest and brand
  assets, `hacs.json`, and a config flow with no steps yet.
- `scripts/check.sh`, the one entry point for ruff, `ruff format --check`, mypy
  strict and `scripts/check_layout.py`, run locally and by CI from the same file.
- `validate.yml` (HACS Action, hassfest), `test.yml` and a changelog check on
  pull requests.
- `scripts/check_layout.py`, asserting what the tree must not hold: no
  `strings.json`, brand assets in one place and at their stated sizes,
  `hacs.json`'s three keys, and the manifest's fixed keys in order.
- `scripts/probe.py`, the hardware conformance probe: stdlib only, four
  ascending tiers, claim text read from the register at runtime, a
  snapshot-and-restore ledger verified from a fresh status read after every
  check, `--restore` to replay a snapshot, fail-closed fixture capture, and the
  spec's exit codes. `--destructive` and `--thermal` both refuse a
  non-interactive stdin (a spec amendment records why).
- `scripts/check_conformance.py`, the CI gate over the conformance register:
  the six drift conditions of §12.4, including that the register's automated
  ids are exactly the ids `probe.py` registers. `VERIFIED_FIRMWARES` lands in
  `const.py` for it to read.
- `tests/test_probe_safety.py` and `tests/test_check_conformance.py`; pytest
  joins `scripts/check.sh`.

### Changed

- Register row Q18 moves from the `read` to the `write` tier: its evidence
  required writing `panelMode=0`, which no read-tier check may do.
