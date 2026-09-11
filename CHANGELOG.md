# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Four of the panel's own settings, on its device page: **Open window
  detection** and **External sensor** as switches, **Standby display**
  (setpoint or measured temperature) and **Buttons** (enabled, disabled or menu
  locked) as selects. Turning **External sensor** on with no wireless sensor
  paired does nothing on the panel, so the switch turns itself back off at the
  next reading, and the log says once that the panel accepted the change
  without applying it.
- The panel's readings, as five **sensors** and one **binary sensor**: room
  temperature, the power it is drawing, the energy it has consumed — ready for
  the Energy dashboard — the countdown on a detected open window, and whether
  it is detecting one. WiFi signal strength joins them as a diagnostic, off
  until you turn it on.

### Changed

- The room a panel is assigned to in the MyHeatit app now only **picks between
  the areas you already have** — matched by name, so `bedroom` finds `Bedroom`.
  It no longer creates an area automatically.

## [0.1.0] - 2026-09-11

First release: the **Heatit WiFi Panel** wall heater over its own HTTP API on
your local network — no cloud, no account, no vendor app. Only the thermostat
ships here; the remaining entities follow in later releases.

### Added

- The panel is added as a **device**: one **climate entity**, polled every 60
  seconds by default, and a **diagnostics download** on its device page with
  the panel's identifiers and its address replaced by placeholders.
- The climate entity has off and heat, with **comfort and eco as presets**. The
  target temperature follows whichever setpoint the panel is regulating to, so
  it moves with the preset and is blank while the panel is off
  ([ADR-0004](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/blob/main/docs/adr/0004-eco-as-a-climate-preset.md)). Whether the
  element is on comes from the panel's relay, not from its reported power.

### Verified

- Firmware **1.21** on a 600 W panel. What that rests on is recorded in the
  [conformance register](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/blob/main/docs/conformance/checklist.md).
