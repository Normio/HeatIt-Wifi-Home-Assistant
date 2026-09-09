# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `api.py`, the device client: `get_status`, `set_parameter`, `reset_kwh`
  and `reset_settings` over the panel's local HTTP API, one request in flight
  per panel, the status read retried once and nothing else ever retried, and
  the exception taxonomy of spec §3.2. Bytes are decoded as UTF-8 explicitly;
  the verdict is HTTP 200 and a `status` matched after stripping; the device's
  `reason` is surfaced verbatim and never parsed.
- `registry.py`, the thirteen observed parameters with their serialisers,
  steps, bounds, read paths, scales and presence flags. Off-step and
  out-of-range values are rejected locally, before any request exists.
- One redaction function scrubbing exactly `id`, `Network.mac`,
  `Network.SSID` and `Network.ipAddress`, at the wire level and on parsed data.
- `scripts/capture_fixtures.py`, the read-only fixture capture with its
  separate live-values block, and the first observed fixture,
  `tests/fixtures/observed/fw-1.21/`, captured from a real panel.
- `VERIFIED_FIRMWARES` in `const.py`, asserted equal to the observed fixture
  directories.
- The offline test suite's first tier: the client over `aioresponses`, the
  registry, fixture hygiene and the capture script's read-only guarantee.
- `test.yml` splits into a `Lint` job and a two-row `Tests` matrix (floor
  blocking, latest on `continue-on-error` and a monthly cron); `check.sh`
  gains `lint` and `test` stages so CI still runs the one shared file.

- The `heatit_wifi_panel` integration package with its manifest and brand
  assets, `hacs.json`, and a config flow with no steps yet.
- `scripts/check.sh`, the one entry point for ruff, `ruff format --check`, mypy
  strict and `scripts/check_layout.py`, run locally and by CI from the same file.
- `validate.yml` (HACS Action, hassfest), `test.yml` and a changelog check on
  pull requests.
- `scripts/check_layout.py`, asserting what the tree must not hold: no
  `strings.json`, brand assets in one place and at their stated sizes,
  `hacs.json`'s three keys, and the manifest's fixed keys in order.
