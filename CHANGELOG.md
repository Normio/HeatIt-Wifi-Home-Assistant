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
- `release.yml`: pushing a `vX.Y.Z` tag runs the validators, `test.yml` and
  `scripts/check_release.py` against the tagged commit, and only when all of
  them pass creates the GitHub release with the changelog section as its
  body. A failed gate leaves the bare tag and deletes nothing.
- `scripts/check_release.py`, the lockstep check: tag equals manifest
  version, the tagged commit is on `main`, the files a release needs exist,
  `hacs.json` keeps its floor gate, and the changelog section is non-empty.
- `tests/`, with the lockstep check's tests as its first residents, run by
  `scripts/check.sh` alongside the linters; mypy strict now covers it too.
- `docs/releasing.md`, the release procedure and the repository settings the
  release depends on.
