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
| Open window detection (`open_window_detection`) | switch | Whether the panel drops to a low temperature when it senses a window opening. |
| External sensor (`external_sensor`) | switch | Whether the panel regulates to a paired wireless sensor instead of its own. With no sensor paired the panel accepts the change and ignores it, so the switch turns itself back off a second or two later. |
| Standby display (`standby_display`) | select | What the panel's display shows when nobody is touching it: the setpoint, or the measured temperature. |
| Buttons (`buttons`) | select | The panel's physical buttons: enabled, disabled, or working with the menu locked. |

Eco is a **preset**, not a second target temperature, and the target follows
whichever setpoint the panel is regulating to — so it changes when the preset
does, and is blank while the panel is off. The reasoning, and what was weighed
against it, is in [ADR-0004](docs/adr/0004-eco-as-a-climate-preset.md).

## Verified firmware

The panel reports its own firmware version. A version listed here is one a real
panel has answered on, with its captured responses kept in this repository's
test suite and the behaviour the integration depends on recorded row by row in
the [conformance register](docs/conformance/checklist.md). A panel on any other
version is *unverified*, not unsupported: it is added and driven exactly the
same way.

| Firmware | Verified on |
|---|---|
| 1.21 | 600 W wall panel (`maxLoad` 6) |

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
