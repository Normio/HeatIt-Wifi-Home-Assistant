# Heatit WiFi Panel

Home Assistant integration for the **Heatit WiFi Panel** wall heater, over the
panel's own HTTP API on your local network. Home Assistant reads the panel's
status and writes its settings directly: no cloud service, no account, and no
vendor app in the path once the panel is on WiFi.

## Requirements

- Home Assistant **2026.3.1** or newer.
- A Heatit WiFi Panel joined to the same network as Home Assistant.

## Installation

This integration is downloaded through [HACS](https://hacs.xyz), as a custom
repository.

[![Open this repository inside your Home Assistant's HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Normio&repository=HeatIt-Wifi-Home-Assistant&category=integration)

The button opens HACS on this repository in your own Home Assistant. To do the
same by hand: in HACS, open the menu in the top right, choose
**Custom repositories**, paste this repository's address,
`https://github.com/Normio/HeatIt-Wifi-Home-Assistant`, pick the type
**Integration**, and add it. Then download **Heatit WiFi Panel** from HACS and
restart Home Assistant.

With the restart done, add the panel: **Settings** → **Devices & services** →
**Add integration** → **Heatit WiFi Panel**, then enter its address. Home
Assistant reads the panel's status once to learn which unit it is. If that
address changes later — a new DHCP lease after a power cut, say — Home
Assistant follows the panel to it without being asked.

## Entities

One panel is one device. Every entity below belongs to it, and each is named by
Home Assistant from the device's name and its own.

| Entity | Platform | What it is |
|---|---|---|
| Heatit WiFi Panel (`panel`) | climate | The thermostat: off and heat, the comfort and eco presets, the temperature the panel is regulating to, and whether the element is on right now. It carries the panel's own name, because it *is* the panel. |
| Comfort setpoint (`comfort_setpoint`) | number | The temperature the panel heats to in comfort. |
| Eco setpoint (`eco_setpoint`) | number | The temperature it heats to in eco. |
| Minimum temperature limit (`minimum_temperature_limit`) | number | The lowest either setpoint may be set to. |
| Maximum temperature limit (`maximum_temperature_limit`) | number | The highest either setpoint may be set to. |
| Sensor calibration (`sensor_calibration`) | number | An offset added to the temperature the panel measures, −6 to +6 °C. |
| Load limit (`load_limit`) | number | The most power the panel will draw, in watts, up to the rating of your model. |
| Active display brightness (`active_display_brightness`) | number | How bright the panel's display is while you are using it. |
| Standby display brightness (`standby_display_brightness`) | number | How bright it is the rest of the time; 0 turns it off. |
| Open window detection (`open_window_detection`) | switch | Whether the panel drops to a low temperature when it senses a window opening. |
| External sensor (`external_sensor`) | switch | Whether the panel regulates to a paired wireless sensor instead of its own. With no sensor paired the panel accepts the change and ignores it, so the switch turns itself back off a second or two later. |
| Standby display (`standby_display`) | select | What the panel's display shows when nobody is touching it: the setpoint, or the measured temperature. |
| Buttons (`buttons`) | select | The panel's physical buttons: enabled, disabled, or working with the menu locked. |
| Temperature (`temperature`) | sensor | The room temperature the panel measures, kept as its own history. The thermostat shows the same reading. |
| Power (`power`) | sensor | What the panel is drawing at this moment, in watts — the reading itself, not an average over the heating cycle. |
| Energy (`energy`) | sensor | What the panel has consumed since its counter was last zeroed, in kWh. It can be added to the Energy dashboard. |
| Signal strength (`signal_strength`) | sensor | The panel's own WiFi signal, in dBm. A diagnostic, and **turned off until you turn it on** from the device page: it moves with every poll and most homes never need it. |
| Open window time remaining (`open_window_time_remaining`) | sensor | How much longer the panel will hold its setpoint down for an open window it has detected. `0` whenever it has detected none. |
| Open window detected (`open_window_detected`) | binary_sensor | Whether the panel is inferring an open window from a drop in room temperature. On or off rather than open or closed: the panel watches the temperature, not a window. |
| Reset energy counter (`reset_energy`) | button | Zeroes the panel's energy counter, the same one the MyHeatit app and the panel's display show. **Turned off until you turn it on** from the device page. |
| Restore default settings (`restore_defaults`) | button | Puts every setting on this page back to the panel's default. Your network and the panel's pairing are kept. **Turned off until you turn it on** from the device page. |

Eco is a **preset**, not a second target temperature, and the target follows
whichever setpoint the panel is regulating to — so it changes when the preset
does, and is blank while the panel is off. The reasoning, and what was weighed
against it, is in [ADR-0004](docs/adr/0004-eco-as-a-climate-preset.md).

The two setpoint numbers are how you reach the *other* bank: either can be set
at any time, whichever mode the panel is in, and the panel goes on regulating
to the one the mode selects. They also keep a history per bank, which the
thermostat's single target cannot.

What each number will let you set follows the panel rather than a fixed range.
The setpoints stop at the temperature limits, each limit stops half a degree
short of the other, and the load limit stops at your model's rating — so Home
Assistant does not offer a value the panel is going to refuse.

The two buttons throw something away — the energy counter, or every setting —
and Home Assistant has no "are you sure?" for a button, so both arrive turned
off and stay that way until you enable them on the device page. Restoring the
defaults keeps your network and the panel's pairing, and the panel applies it
over about five seconds, so the settings on this page finish catching up a
poll later.

The panel publishes its energy counter in steps of roughly 0.04 kWh rather than
continuously, so the Energy sensor sits flat for minutes and then jumps. That is
the panel reporting, not Home Assistant waiting. Zeroing the counter — from
Home Assistant, the MyHeatit app or the panel itself — costs at most one of
those steps, the energy banked since the last one having never been published;
everything already recorded stays, because the sensor counts up and the panel
zeroes to exactly nothing.

## Verified firmware

The panel reports its own firmware version. A version listed here is one a real
panel has answered on, with its captured responses kept in this repository's
test suite and the behaviour the integration depends on recorded row by row in
the [conformance register](docs/conformance/checklist.md). A panel on any other
version is *unverified*, not unsupported: it is added and driven exactly the
same way.

| Firmware | Verified on |
|---|---|
| 1.21 | 600 W wall panel (`maxLoad` 6) and 1000 W wall panel (`maxLoad` 10) |

## Network

The panel serves plain HTTP on port 80 with **no authentication of any kind**.
Anyone who can reach it on the network can read its status and change its
settings, this integration included. It belongs on a network you trust.

Home Assistant reaches the panel at its IP address, so **give the panel a static
DHCP reservation** on your router. The address then stays the same across a
reboot of the panel, the router or the lease.

## Diagnostics

The panel's device page offers **Download diagnostics**. The file holds the
panel's status as the integration parsed it, the same status as raw bytes
exactly as the panel sent them, the firmware and whether it is one of the
versions above, and what the last poll did. The panel's `id`, MAC, WiFi SSID and IP address are
replaced with fixed placeholders on the way out, and so is the panel's address
in your configuration, so the download can be attached to an issue as it is.
The panel's name and room are kept: they are labels, not identifiers.

If your firmware is not in the table above, that download is what adds it: it
carries the panel's own bytes, fields this integration does not read included.

## Documentation

- [Design spec](docs/spec/heatit-wifi-panel-v1.md) — the whole integration, decision by decision.
- [Conformance register](docs/conformance/checklist.md) — every claim about the panel, and the firmware it was verified at.
- [Vocabulary](CONTEXT.md) — the words this project uses for the panel and its status.
- [Changelog](CHANGELOG.md).

## Licence

[MIT](LICENSE).
