---
status: accepted
---

# The panel's device id, not its MAC, is the Home Assistant unique id

The status carries two possible identifiers. `id` is the panel's own 22-character mixed-case token. `Network.mac` lives in the ESP32's eFuse and survives everything a user can do to the device. The MAC is the more stable of the two, and Home Assistant's entity registry documentation accepts it. So choosing against it needs a written reason.

We decided that **the device id is the config entry's `unique_id`**, used as-is. The MAC goes into `DeviceInfo.connections` via `format_mac`. There it identifies the hardware without being the identity. The deciding evidence:

- The device id survived `DELETE /api/reset/settings` on the live panel at firmware 1.21.
- It is the identifier the vendor's own API and app are built around.
- One opaque value already does three separate jobs: the entry's unique id, the `{id}-{key}` prefix of all 21 entity unique ids, and the per-poll comparison that detects a foreign panel.

## Considered Options

- **`format_mac(Network.mac)` as the unique id.** Strictly more stable. It is burned into hardware, immune to a factory reset, and unaffected by re-provisioning. Rejected for two reasons. It splits identity from the value every other layer already compares, so the foreign-panel guard would have to be restated against a separately stored device id. And it only buys resilience in one scenario, a factory reset, where the user has deliberately wiped the device and can reasonably re-add it.
- **Device id as the unique id, with the MAC also checked for foreignness.** This would tell a panel that regenerated its device id apart from a genuinely different unit. Rejected as machinery for an event nobody has observed. If a firmware is ever found to churn the id, the MAC is already in `connections`, and this becomes the migration path.

## Consequences

- The vendor's OpenAPI document describes `id` as 23 lowercase alphanumerics. The real value is 22 characters and mixed case. So it must never be lowercased or length-checked against the spec.
- Whether the device id survives a **factory reset** or a **firmware update** is untested. That belongs to the hardware conformance checklist. A firmware that regenerates the id would orphan every entity. The MAC in `connections` is the only reason that would be recoverable rather than terminal.
- The DHCP discovery matcher yields only a MAC. So `async_step_dhcp` cannot identify the entry from the packet alone. It reads the status at the discovered address to learn the device id before repointing the entry.
