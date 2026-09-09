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
