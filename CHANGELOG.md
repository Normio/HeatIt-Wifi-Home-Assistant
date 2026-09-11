# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-11

First release. A Home Assistant integration for the **Heatit WiFi Panel** wall
heater, over the panel's own HTTP API on the local network: no cloud service,
no account, and no vendor app in the path once the panel is on WiFi.

This release ships the panel as a thermostat. The remaining entities — the
setpoint and display numbers, the switches, the selects, the sensors and the
reset buttons — are written against the same device client and arrive in later
releases.

### Added

- **The panel as a device.** One panel is one device, identified by the
  panel's own device id rather than its MAC, so a panel that changes address
  keeps its history and its entity ids. The MAC travels in `connections` as a
  migration path. Model, firmware and the room assigned in the MyHeatit app are
  read from the device; the room becomes an area suggestion, and a rename in
  Home Assistant is never overwritten by one in the app.
- **A climate entity.** Off and Heat, with **comfort and eco as presets** —
  the target temperature follows whichever setpoint the panel is regulating to,
  so it changes when the preset does and is blank while the panel is off.
  Turning on always lands in Heating; selecting a preset while off turns the
  panel on in that mode. Temperature limits come from the device and are
  reported as they are. Whether the element is on comes from the panel's relay
  rather than from its reported power, which trails the relay by about 15
  seconds. Recorded as [ADR-0004](docs/adr/0004-eco-as-a-climate-preset.md).
- **Setup through a config flow**, host only: Home Assistant reads the panel's
  status once to learn which unit answers there. Panels already known to the
  router are offered by DHCP discovery. Reconfigure moves an existing panel to
  a new address and refuses to adopt a different unit that has taken it over.
  One option, the poll interval — 60 seconds by default, 30 seconds minimum.
- **A failure model where the poll is the sole judge of availability.** A
  status read is retried once inside a 10-second budget; the first poll that
  exhausts it makes the panel unavailable, and the next good poll brings it
  back, two log lines for a panel that was away all night. A panel answering at
  a configured address with the wrong device id is never accepted as data. A
  parameter this firmware does not return costs only its own entity.
- **Writes that show at once and are then checked.** A change applies the value
  the panel echoes back and schedules one refresh 1.5 seconds later, which is
  the authority. A write the panel acknowledges and then does not apply is
  logged once per parameter. Every write failure reaches the user as the
  panel's own words rather than a traceback.
- **One redaction function** over logging, diagnostics and fixture capture,
  scrubbing the device id, MAC, SSID and IP address. Raw response bytes are
  never logged at any level.
- **Tooling that keeps the repository honest**: `scripts/check.sh` as the one
  entry point CI also calls, so local and CI cannot drift; `scripts/probe.py`,
  the hardware conformance probe, with four ascending hazard tiers and a
  restore verified from a fresh status read; `scripts/capture_fixtures.py` for
  read-only fixture capture; `scripts/check_conformance.py`,
  `scripts/check_layout.py` and `scripts/check_release.py` as CI gates over the
  conformance register, the repository layout and the release itself.
- **A test suite built on captured bytes.** Every fixture is either a real
  panel's response or derived from one in test code; nothing is modelled,
  exposed or tested because a document said so. The client is exercised over
  HTTP, and the config flow, coordinator and entities against a real
  `hass` with the client faked from the same bytes.

### Verified

- Firmware **1.21**, on a 600 W wall panel. The claims the integration depends
  on are recorded row by row in the
  [conformance register](docs/conformance/checklist.md), each with the firmware
  it was verified at. A panel on any other version is unverified, not
  unsupported: it is added and driven exactly the same way.
