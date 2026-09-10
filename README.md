# Heatit WiFi Panel

Home Assistant integration for the **Heatit WiFi Panel** wall heater, over the
panel's own HTTP API on your local network. Home Assistant reads the panel's
status and writes its settings directly: no cloud service, no account, and no
vendor app in the path once the panel is on WiFi.

## Requirements

- Home Assistant **2026.3.1** or newer.
- A Heatit WiFi Panel joined to the same network as Home Assistant.

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
panel's status as the integration parsed it, the status response exactly as the
panel sent it, the firmware and whether it is one of the versions above, and
what the last poll did. The panel's `id`, MAC, WiFi SSID and IP address are
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
