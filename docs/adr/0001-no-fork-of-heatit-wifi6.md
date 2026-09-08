---
status: accepted
---

# No fork of heatit_wifi6

The originating brief proposed forking `mattik-gh/heatit_wifi6`, a HACS integration for the related Heatit WiFi6 thermostat, on the strength of an "almost identical" API. An audit of that repository (`docs/research/heatit-wifi6-prior-art.md`) found the premise does not hold: only 5 of the Panel's 15 writable parameters match in name, type, range and semantics; the divergences sit on the write path and two of them fail silently (the network block is `Network` on the Panel and `network` on the WiFi6; `panelMode` 2 is Eco where `operatingMode` 2 is Cool); roughly 30 of 38 current-standards rows fail, with no coordinator, no entity descriptions, no device, no config-flow validation, no tests and no CI; and the three artefacts worth inheriting (a parameter-to-entity table, a test setup, a config flow) do not exist there. We decided to **ignore** it: the integration is written from the spec and the observed panel, in this repository's own history, with no copied code, no forked history, and no acknowledgement owed or given.

## Consequences

- The spec never names `heatit_wifi6`. Device behaviours the audit surfaced (a wrong `Content-Type` on JSON responses, several Heatit devices timing out when polled together at Home Assistant restart) stand as claims about the device, verified against our own panel by the conformance checklist and sourced to the panel once verified.
- The README carries a one-line signpost telling WiFi6 thermostat owners this integration is not for their device. That is a routing aid, not credit.
- The handoff brief keeps its fork recommendation verbatim as the historical record, under a banner saying it is superseded and the fork was rejected.
- Coexistence with `heatit_wifi6` on the same Home Assistant is settled by the distinct domain `heatit_wifi_panel` and display name; nothing in code guards it.
