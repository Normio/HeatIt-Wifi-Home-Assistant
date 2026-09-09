---
status: accepted
---

# The panel's device id, not its MAC, is the Home Assistant unique id

The status carries two candidate identifiers: `id`, the panel's own 22-character mixed-case token, and `Network.mac`, which lives in the ESP32's eFuse and survives everything a user can do to the device. The MAC is the more stable of the two and Home Assistant's entity registry documentation accepts it, so choosing against it needs recording. We decided that **the device id is the config entry's `unique_id`**, used verbatim, and that the MAC goes into `DeviceInfo.connections` via `format_mac` where it identifies the hardware without being identity. The deciding evidence is that the device id survived `DELETE /api/reset/settings` on the live panel at firmware 1.21, that it is the identifier the vendor's own API and app are built around, and that a single opaque value already serves three separate jobs — the entry's unique id, the `{id}-{key}` prefix of all 21 entity unique ids, and the per-poll comparison that detects a foreign panel.

## Considered Options

- **`format_mac(Network.mac)` as the unique id.** Strictly more stable: burned into hardware, immune to a factory reset, and unaffected by re-provisioning. Rejected because it splits identity from the value every other layer already compares — the foreign-panel guard would have to be restated against a separately stored device id — and because it buys resilience only in the one scenario, a factory reset, where the user has deliberately wiped the device and can reasonably re-add it.
- **Device id as the unique id, with the MAC also checked for foreignness.** Would distinguish a panel that regenerated its device id from a genuinely different unit. Rejected as machinery for an event nobody has observed; if a firmware is ever found to churn the id, the MAC is already in `connections` and this becomes the migration path.

## Consequences

- The vendor's OpenAPI document describes `id` as 23 lowercase alphanumerics. The real value is 22 characters and mixed case, so it must never be lowercased or length-validated against the spec.
- Whether the device id survives a **factory reset** or a **firmware update** is untested and belongs to the hardware conformance checklist. A firmware that regenerates it would orphan every entity, and the MAC in `connections` is the only reason that would be recoverable rather than terminal.
- Because the DHCP discovery matcher yields only a MAC, `async_step_dhcp` cannot identify the entry from the packet alone: it reads the status at the discovered address to learn the device id before repointing the entry.
