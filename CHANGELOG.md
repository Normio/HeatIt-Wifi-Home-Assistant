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
  ids are exactly the ids `probe.py` registers.
- `tests/test_probe_safety.py` and `tests/test_check_conformance.py`; pytest
  joins `scripts/check.sh`.
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
- `VERIFIED_FIRMWARES` in `const.py`, read by `scripts/check_conformance.py`
  and asserted equal to the observed fixture directories.
- The offline test suite's first tier: the client over `aioresponses`, the
  registry, fixture hygiene and the capture script's read-only guarantee.
- `test.yml` splits into a `Lint` job and a two-row `Tests` matrix (floor
  blocking, latest on `continue-on-error` — except on a tag, where the release
  gate calls this workflow and §10.2 makes both rows block — and a monthly
  cron); `check.sh` gains `lint` and `test` stages so CI still runs the one
  shared file.

- The first observed write-path fixtures at firmware 1.21 under
  `tests/fixtures/observed/fw-1.21/`: three write echoes (one the lying
  `sensorMode` echo), a 400, the `text/html` 404 and the HTTP/1.0 505, each as
  raw bytes with its headers beside it, captured by `probe.py --writes`.

- `release.yml`: pushing a `vX.Y.Z` tag runs the validators, `test.yml` and
  `scripts/check_release.py` against the tagged commit, and only when all of
  them pass creates the GitHub release with the changelog section as its
  body. A failed gate leaves the bare tag and deletes nothing.
- `scripts/check_release.py`, the lockstep check: tag equals manifest
  version, the tagged commit is on `main`, the files a release needs exist,
  `hacs.json` keeps its floor gate, and the changelog section is non-empty.
- `tests/scripts/`, holding the lockstep check's own tests. One of them
  asserts that every `continue-on-error` in the workflows the gate calls is
  switched off on a tag, so a failing row can never be passed over.
- `docs/releasing.md`, the release procedure and the repository settings the
  release depends on.

### Changed

- The `mocked` fixture supplies aiohttp 3.14's required `stream_writer` to the
  responses aioresponses builds, when the running aiohttp has that parameter.
  aioresponses 0.7.9, its newest release, does not pass it, which reddened the
  latest row on a test-only dependency's lag rather than on anything Home
  Assistant changed under us — the one thing that row exists to report.
- Register row Q18 moves from the `read` to the `write` tier: its evidence
  required writing `panelMode=0`, which no read-tier check may do.
