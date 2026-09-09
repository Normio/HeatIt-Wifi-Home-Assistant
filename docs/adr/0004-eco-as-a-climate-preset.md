---
status: accepted
---

# Eco is a climate preset, not a second target temperature

The panel has one three-way *panel mode* and two *setpoint banks*, one of which is *live* depending on
that mode; Home Assistant's climate entity has one `target_temperature`. Something has to give, and
whichever way it gives is visible to the user every day and expensive to change afterwards. We decided
that **`hvac_modes` is `[OFF, HEAT]`, Eco is a preset, and `target_temperature` follows the live
setpoint** — jumping when the preset changes — with both banks *also* exposed as `EntityCategory.CONFIG`
number entities. Eco as a third `HVACMode` was never available: the enum is closed, core coerces
`set_hvac_mode` to it, and the entity's `state` property raises on a non-member, so the preset is the
only way Eco reaches the climate dialog or the thermostat card at all. Verified on the live panel at
firmware 1.21: Eco does regulate to the eco setpoint, and a write to the inactive bank is stored and
inert.

## Considered Options

- **`TARGET_TEMPERATURE_RANGE`, both banks exposed at once.** The serious rival, with precedent in the
  same product category (Nordic panel heaters in core). Nothing ever jumps and the recorded history
  stays honest. Rejected because a plain `climate.set_temperature` with `temperature:` **fails** under
  it, which breaks the most common heater automation and is a real support burden, and because it
  abuses heat/cool deadband semantics — forcing eco ≤ comfort, which the panel does not require. The
  two config numbers recover its honest per-bank history without that cost.
- **An eco `switch` beside the climate entity.** The shape a well-known AC integration ships. Rejected
  because that device's eco only caps power, so its dial never moves, whereas ours changes *which
  setpoint the dial edits* — and a switch gives the climate card no cue of that.
- **Exposing the eco setpoint only as a `number`, leaving `target_temperature` always on comfort.**
  Rejected: climate would then report a target the device is not chasing whenever the panel is in Eco.

## Consequences

- `target_temperature` is two-valued in the recorded history, and jumps when the preset changes. That
  is the documented behaviour of the closest precedent in core, and it is the price of the preset.
- `target_temperature` is `None` while the panel is Off, and a plain `set_temperature` raises
  `ServiceValidationError` rather than guessing a bank. This follows the dev's Heatit floor
  thermostats, whose dial is blank while Off, with one deliberate deviation: those drop the write
  silently, and we refuse loudly so an automation learns it did nothing.
- Selecting a preset while Off turns the panel on in that mode, because a preset is an explicit choice
  of on-mode. `turn_on` always lands in Heating: the panel has no "on" verb and remembers nothing, so
  Home Assistant invents no memory either.
- `hvac_modes` is fixed and never computed from live state, so the capability list cannot flap.
- `TURN_ON` / `TURN_OFF` must be declared explicitly. The compatibility shim that inferred them from
  `HVACMode.OFF in hvac_modes` was deleted in HA 2025.1, and an area-targeted service call now
  silently skips an entity that does not declare them.
- Reversing this decision later would change every user's automations and their recorded history, which
  is why it is written down rather than left implicit in the climate module.
