# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

**Buttons**

- Reset the energy counter, off until you turn it on. Home Assistant checks
  afterwards that the counter actually went to zero and says so in the log once
  if it did not; a counter zeroed from the MyHeatit app or the panel is left
  alone.
- Restore the panel's default settings, off until you turn it on. The network
  and the panel's pairing are kept, and the panel applies the rest over about
  five seconds.

## [0.2.0] - 2026-09-11

Adds 8 numbers, 2 switches, 2 selects, 5 sensors and 1 binary sensor. The
room a panel is assigned to in the MyHeatit app now picks an area you already
have, instead of creating one.

### Added

**Numbers**

- Comfort setpoint
- Eco setpoint
- Lowest and highest temperature the setpoints may be set to
- Sensor calibration, to correct the temperature the panel measures
- Load limit, in watts
- Display brightness, in use and on standby

**Switches**

- Open window detection
- External sensor — needs a wireless sensor paired to the panel

**Selects**

- What the standby display shows: the setpoint, or the measured temperature
- The panel's buttons: enabled, disabled, or menu locked

**Sensors**

- Room temperature
- Power, in watts
- Energy, in kWh, ready for the Energy dashboard
- How much longer the panel will hold its setpoint down for an open window
- WiFi signal strength, off until you turn it on

**Binary sensor**

- Open window detected

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
