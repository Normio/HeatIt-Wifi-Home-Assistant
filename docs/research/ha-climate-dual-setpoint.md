# HA climate contract for preset-switched dual setpoints

Research resolving [issue #6](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/6).
Sources are Home Assistant developer docs, `home-assistant/core` source at `dev`, and the
`home-assistant/architecture` discussion tracker. Read 2026-09-07 against core `dev`.

**Scope note.** This ticket establishes *what HA expects*. The decision for our integration is
[#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8); the recommendation at the end
is offered with its reasoning exposed so #8 can overturn it.

## The problem restated

The Heatit WiFi Panel stores two independent setpoints (`heatingSetpoint`, `ecoSetpoint`) and a
`panelMode` (0 = Off, 1 = Heating, 2 = Eco) selecting which is authoritative. `ClimateEntity`
exposes one `target_temperature`. Something has to give.

## Headline finding

**Both candidate modellings have direct core precedent, and they are not the two the handoff
imagined.** Core contains at least three distinct answers to this exact device shape, including one
the ticket did not enumerate: expose *both* setpoints simultaneously via
`TARGET_TEMPERATURE_RANGE`. See [Alternatives](#alternative-modellings).

---

## 1. The `ClimateEntity` contract

From [the climate entity docs](https://developers.home-assistant.io/docs/core/entity/climate) and
`homeassistant/components/climate/const.py`.

### Properties

| Property | Type | Default | Notes |
| --- | --- | --- | --- |
| `hvac_mode` | `HVACMode \| None` | required | Becomes the entity **state** |
| `hvac_modes` | `list[HVACMode]` | required | |
| `hvac_action` | `HVACAction \| None` | `None` | The action *currently being performed* |
| `target_temperature` | `float \| None` | `None` | "The temperature currently set to be reached" |
| `target_temperature_high` / `_low` | `float \| None` | required by `TARGET_TEMPERATURE_RANGE` | |
| `target_temperature_step` | `float \| None` | `None` | |
| `min_temp` / `max_temp` | `float` | `7` / `35` (`DEFAULT_MIN_TEMP`/`DEFAULT_MAX_TEMP`) | in `temperature_unit` |
| `current_temperature` | `float \| None` | `None` | |
| `preset_mode` / `preset_modes` | `str \| None` / `list[str] \| None` | required by `PRESET_MODE` | |

### `HVACMode` is a closed enum

```python
class HVACMode(StrEnum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    HEAT_COOL = "heat_cool"
    AUTO = "auto"
    DRY = "dry"
    FAN_ONLY = "fan_only"
```

— `homeassistant/components/climate/const.py`

This is decisive for one of the alternatives: **there is no way to add an `eco` HVAC mode.** "Eco as
a second `HVACMode`" can only mean re-purposing an existing member (`AUTO`, or a second `HEAT`-like
mode that does not exist). Any such modelling is an abuse of a fixed vocabulary that the frontend,
voice assistants, `climate.set_hvac_mode` selectors and `device_trigger`/`device_condition` all read
literally.

### `ClimateEntityFeature`

```python
class ClimateEntityFeature(IntFlag):
    TARGET_TEMPERATURE = 1
    TARGET_TEMPERATURE_RANGE = 2
    TARGET_HUMIDITY = 4
    FAN_MODE = 8
    PRESET_MODE = 16
    SWING_MODE = 32
    TURN_OFF = 128
    TURN_ON = 256
    SWING_HORIZONTAL_MODE = 512
```

Note `64` is absent — it was `AUX_HEAT`, removed after deprecation.

### Standard preset constants

```python
PRESET_NONE = "none"
PRESET_ECO = "eco"
PRESET_AWAY = "away"
PRESET_BOOST = "boost"
PRESET_COMFORT = "comfort"
PRESET_HOME = "home"
PRESET_SLEEP = "sleep"
PRESET_ACTIVITY = "activity"
```

`PRESET_ECO` is documented as "Device is running an energy-saving mode" — an exact fit for
`panelMode = 2`. Presets are a free-form `list[str]`, but using the standard constants is what buys
translated frontend labels and voice-assistant recognition.

### The `set_temperature` service — three traps

`async_service_temperature_set` in `climate/__init__.py` is a module-level *function*, not a method,
and that has consequences.

**(a) Core does range-check, and it raises.** Lines 827–853:

```python
if check_temp < min_temp or check_temp > max_temp:
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="temp_out_of_range",
        ...
    )
```

Bounds are **inclusive**, and the comparison happens in the **entity's** `temperature_unit` after
converting the caller's value from `hass.config.units.temperature_unit`. So `min_temp`/`max_temp`
must be returned in *our* unit (°C), while the *displayed* `min_temp`/`max_temp` attributes are
converted to the user's display unit by `show_temp`. Two different units for the same numbers,
depending on which side you are on.

**(b) `async_set_temperature` receives `entity_id` as a kwarg.** Because the handler is a function
rather than a method-name string, `helpers/service.py` never strips entity-targeting fields, and the
`for value, temp in service_call.data.items()` loop copies them into `kwargs`. **Always write
`async_set_temperature(self, **kwargs)` and pull values with `kwargs.get(ATTR_TEMPERATURE)`** — a
fixed positional signature will raise `TypeError` at runtime.

**(c) `hvac_mode` is passed through unvalidated and unapplied.** The schema accepts it
(`vol.Optional(ATTR_HVAC_MODE): vol.Coerce(HVACMode)`) but core neither checks it against
`hvac_modes` nor calls `async_set_hvac_mode` for us. If we want `climate.set_temperature` with an
`hvac_mode` to work, **our** `async_set_temperature` must handle it. (Removing this field was
proposed in [architecture#1154](https://github.com/home-assistant/architecture/discussions/1154) and
not adopted.)

The `services.yaml` selector (`min: 0, max: 250, step: 0.1, mode: box`) is unrelated to the entity's
`target_temperature_step`; the entity attribute governs the thermostat card's increment only.

### `preset_mode` is validated for us

`async_handle_set_preset_mode_service` is `@final` and calls `_valid_mode_or_raise`, which raises
`ServiceValidationError` / `not_valid_preset_mode` when the requested preset is not in
`preset_modes`. Matching is exact and case-sensitive. `PRESET_NONE` is **not** required in the list.
Note the guard is `if modes and mode in modes:` — an empty or `None` `preset_modes` makes every call
fail, so if we declare `PRESET_MODE` we must always return a non-empty list.

---

## 2. `hvac_action` vs `hvac_mode` — may `IDLE` be reported while `OFF`?

**No. When `hvac_mode` is `OFF`, `hvac_action` must be `HVACAction.OFF`.**

The docs define the two members unambiguously:

- `OFF` — "HVAC mode is `HVACMode.OFF`. The device will not perform any action unless the mode is
  changed."
- `IDLE` — "The device is not currently performing any action, but may start performing an action if
  conditions change."

`IDLE`'s "may start performing an action if conditions change" is false when the device is off — the
mode must change first, which is exactly what `OFF`'s definition carves out.

Core's own reference implementation, `homeassistant/components/generic_thermostat/climate.py`,
checks mode before device activity:

```python
if self._hvac_mode == HVACMode.OFF:
    return HVACAction.OFF
if not self._is_device_active:
    return HVACAction.IDLE
if self.ac_mode:
    return HVACAction.COOLING
return HVACAction.HEATING
```

The converse error — reporting `OFF` while the mode is active but the device is not calling for heat
— was filed as a bug against Nest in
[core#62797](https://github.com/home-assistant/core/issues/62797) and fixed
(PR [#62811](https://github.com/home-assistant/core/pull/62811)). The rule from that thread: `OFF`
only when `hvac_mode` is `OFF`; otherwise not-currently-heating is `IDLE`.

**There is no core validation enforcing this.** It is a convention the frontend and statistics rely
on, not a runtime check — so it is on us to get right.

**For the Panel:** `panelMode = 0` → `hvac_mode = OFF` **and** `hvac_action = OFF`. When
`panelMode` is 1 or 2, `hvac_action` is `HEATING` when the relay/duty indicates demand and `IDLE`
otherwise. Whether the device actually exposes a relay/demand signal is a **conformance-checklist
item** — if it does not, `hvac_action` should be omitted (`None`) rather than guessed from
`currentTemperature < setpoint`, which would fabricate hysteresis we cannot observe.

---

## 3. `ClimateEntityFeature.TURN_ON` / `TURN_OFF`

Introduced in **2024.2**
([developer blog, 2024-01-24](https://developers.home-assistant.io/blog/2024/01/24/climate-climateentityfeatures-expanded/)).
The blog describes a transition shim, and **most write-ups of this rule are now out of date.**

### The shim is gone — verified against core `dev`

Reading `climate/__init__.py` at successive release tags:

| Version | State |
| --- | --- |
| 2024.1 | Flags do not exist |
| **2024.2** | Flags added, plus `_report_turn_on_off` warning shim that *auto-adds* the flags |
| 2024.6 – 2024.12 | Shim present, comment: "Can be removed in 2025.1 after deprecation period" |
| **2025.1** | **Shim deleted entirely.** No warning, no auto-add |
| 2025.8 → `dev` | Even the `CHECK_TURN_ON_OFF_FEATURE_FLAG` constant is gone |

Current `dev` has no `_report_turn_on_off`, no `add_to_platform_start` override, and no
`_enable_turn_on_off_backwards_compatibility`. **Do not set that attribute in new code** — it is
dead.

### What the rule is now

The historical shim contained the `HVACMode.OFF` inference:

```python
if (modes := self.hvac_modes) and len(modes) >= 2 and HVACMode.OFF in modes:
    # turn_on/off implicitly supported by including more modes than 1 and one of these
    # are HVACMode.OFF
```

That inference **died with the shim**. Nothing in current core inspects `hvac_modes` to derive
feature flags. So the answer to "how do they interact with `hvac_modes` containing `OFF`?" is:
**they no longer interact automatically — the coupling is now purely our responsibility, and
failure is silent until a service call.**

Enforcement is the generic `required_features` gate at registration time
(`climate/__init__.py` 134–151), resolved in `helpers/service.py`:

```python
# Skip entities that don't have the required feature.
if required_features is not None and (...):
    # If entity explicitly referenced, raise an error
    if referenced is not None and entity.entity_id in referenced.referenced:
        raise ServiceNotSupported(call.domain, call.service, entity.entity_id)
    continue
```

- Targeting the entity **directly** → `ServiceNotSupported`.
- Targeting it via an **area or device** → the entity is **silently skipped**. This is the nasty
  failure mode: a user's "turn off all heaters in the bedroom" automation quietly does nothing.
- `climate.toggle` requires **both** flags in a single feature set.

### We usually do not need to implement the methods

Core ships working defaults. `async_turn_on`:

```python
# If there are only two HVAC modes, and one of those modes is OFF,
# then we can just turn on the other mode.
if len(self.hvac_modes) == 2 and HVACMode.OFF in self.hvac_modes:
    for mode in self.hvac_modes:
        if mode != HVACMode.OFF:
            await self.async_set_hvac_mode(mode)
            return
```

and `async_turn_off` falls back to `async_set_hvac_mode(HVACMode.OFF)`.

**For the Panel:** `hvac_modes = [HVACMode.OFF, HVACMode.HEAT]` is exactly the two-mode case, so
declaring `TURN_ON | TURN_OFF` in `supported_features` is sufficient — core's defaults will route to
`async_set_hvac_mode` correctly and we write no turn-on/off methods at all. Declaring the flags is
**not optional**; omitting them silently breaks area-targeted automations.

Corroborating issues from the transition: [core#109304](https://github.com/home-assistant/core/issues/109304),
[core#109865](https://github.com/home-assistant/core/issues/109865).

> **Aside — do not reuse `ClimateEntityFeature` value `64`.** It was `AUX_HEAT`, removed in 2025.6.
> The enum has a deliberate hole there.

---

## 4. May `min_temp` / `max_temp` be dynamic?

**Yes — nothing in core forbids it, and core explicitly acknowledges integrations already do it.**

Evidence:

1. **They are `cached_property` members of `CACHED_PROPERTIES_WITH_ATTR_`**, so writing
   `self._attr_min_temp` invalidates the cache and the new value propagates on the next
   `async_write_ha_state()`. No validation rejects a change.

2. **Core treats them as non-significant attributes.**
   `homeassistant/components/climate/significant_change.py` lists exactly which attributes count as
   a meaningful change:

   ```python
   SIGNIFICANT_ATTRIBUTES: set[str] = {
       CURRENT_HUMIDITY, CURRENT_TEMPERATURE, FAN_MODE, TARGET_HUMIDITY,
       HVAC_ACTION, PRESET_MODE, SWING_MODE, SWING_HORIZONTAL_MODE,
       TARGET_TEMP_HIGH, TARGET_TEMP_LOW, TARGET_TEMPERATURE,
   }
   ```

   `min_temp`, `max_temp`, `target_temp_step`, `hvac_modes` and `preset_modes` are deliberately
   **not** in that set. Changing them therefore does not trigger a cloud/assistant state report.

3. **Core maintainers have explicitly conceded the dynamic case.** In
   [architecture#1164](https://github.com/home-assistant/architecture/discussions/1164) (proposing
   user-overridable min/max), `farmio` raised:

   > "Integrations might have different min/max values based on the current modes (heat / cool) or
   > even different presets (comfort / building protection). Should this be considered when allowing
   > users to change the mi /max value?"

   `gjohansson-ST` (core climate maintainer) called it a "very valid point" needing a rethink, and
   `emontnemery` put the whole proposal **on hold** pending it. The feature is *still* on hold —
   i.e. dynamic min/max is the status quo core has to design *around*, not a violation.

4. Same theme in [architecture#1154](https://github.com/home-assistant/architecture/discussions/1154),
   where `PeteRager` argues:

   > "The underlying **climate data model is insufficient** for the use case. If the model
   > represented setpoint ranges for the available hvac_modes - this would be easy."

   and notes "min / max may be mode specific."

### But there are two real costs

**(a) Every change rewrites the entity registry entry.** `min_temp`/`max_temp` live in
`capability_attributes` (unconditionally, not gated on any feature flag):

```python
data: dict[str, Any] = {
    ClimateEntityCapabilityAttribute.HVAC_MODES: self.hvac_modes,
    ClimateEntityCapabilityAttribute.MIN_TEMP: show_temp(...),
    ClimateEntityCapabilityAttribute.MAX_TEMP: show_temp(...),
}
```

and `helpers/entity.py` rate-limits capability churn:

```python
if len(capabilities_updated_at) > CAPABILITIES_UPDATE_LIMIT:
    self.__capabilities_updated_at_reported = True
    _LOGGER.warning(
        "Entity %s (%s) is updating its capabilities too often, please %s", ...
    )
```

`CAPABILITIES_UPDATE_LIMIT = 100` per rolling hour, per entity. Our limits change only when a user
edits them, so we are nowhere near it — but it forbids any design that recomputes limits per poll.

**(b) Two different units.** `show_temp` converts to the *user's* display unit, so the
`min_temp`/`max_temp` **state attributes** are in display units, while the `set_temperature` range
check compares in the **entity's** unit. Our `min_temp`/`max_temp` properties must therefore return
**°C**, not the user's unit. Note `_attr_min_temp`, if set, is used **as-is with no conversion**.

**Good news on history:** `climate/__init__.py` explicitly excludes them from the recorder:

```python
_entity_component_unrecorded_attributes = frozenset({
    ClimateEntityCapabilityAttribute.HVAC_MODES,
    ...
    ClimateEntityCapabilityAttribute.MIN_TEMP,
    ClimateEntityCapabilityAttribute.MAX_TEMP,
    ...
    ClimateEntityCapabilityAttribute.TARGET_TEMP_STEP,
    ClimateEntityCapabilityAttribute.PRESET_MODES,
})
```

So changing limits costs no database bloat.

### The feedback loop we should flag

Ours come from device-writable `minimumTemperatureLimit` / `maximumTemperatureLimit`, which we also
plan to expose as `number` entities. That creates a real loop:

```
user drags number.min_temp_limit  →  device parameter write
                                  →  coordinator refresh
                                  →  climate.min_temp changes
                                  →  thermostat card range redraws under the user's cursor
```

Worse, the *current* `target_temperature` can fall outside the new bounds. Concrete hazards and the
mitigations that follow from the above:

- **Core already range-checks writes, and it is strict.** We do *not* need our own validation:

  ```python
  if check_temp < min_temp or check_temp > max_temp:
      raise ServiceValidationError(..., translation_key="temp_out_of_range")
  ```

  Bounds inclusive. Message: *"Provided temperature {check_temp} is not valid. Accepted range is
  {min_temp} to {max_temp}."* **This is the sharp edge of the loop**: if the user narrows
  `maximumTemperatureLimit` below the stored `heatingSetpoint`, every subsequent
  `climate.set_temperature` in the old range fails with a user-visible error — and the entity is
  left displaying a `target_temperature` that is outside its own advertised bounds.
- **Do not clamp `target_temperature` into range in the property.** Report what the device reports.
  A clamped read is a lie and will fight the device on the next poll. Accept the transient
  out-of-bounds display; it is truthful and self-corrects.
- **Order the refresh.** After a limit `number` write, refresh limits *before* the next climate
  state write so the card never briefly shows a slider inconsistent with its own bounds.
- **Use `EntityCategory.CONFIG`** on the limit `number` entities so they sit in the device page's
  configuration block rather than looking like primary controls.
- **Conformance checklist item:** does the device itself clamp a stored setpoint when the limits are
  narrowed below it, or does it keep an out-of-range setpoint? We do not know, and the two
  behaviours give very different user experiences after a limit change.
- **Conformance checklist item:** do `minimumTemperatureLimit` / `maximumTemperatureLimit` bound
  `ecoSetpoint` as well as `heatingSetpoint`, or does eco have its own range? If the ranges differ
  per setpoint, then under any preset-switched modelling `min_temp`/`max_temp` must *also* switch
  with the preset — which is precisely the case core put architecture#1164 on hold over.

---

## 5. `target_temperature_step` — 0.1 or 0.5?

The docs give no guidance beyond the definition ("the supported step size a target temperature can
be increased or decreased"). `precision` is separate and "defaults to tenths for
`UnitOfTemperature.CELSIUS`, whole number otherwise" — step controls the *card's increment*,
precision controls *display rounding*. They are independent knobs, and core integrations set them
independently (`nobo_hub`: `_attr_target_temperature_step = PRECISION_WHOLE` with
`_attr_precision = PRECISION_TENTHS`).

Three pieces of evidence favour **0.5** over 0.1:

1. **Core's own significance threshold for temperature is 0.5 °C.** In
   `climate/significant_change.py`, a target-temperature change is only significant at:

   ```python
   if ha_unit == UnitOfTemperature.FAHRENHEIT:
       absolute_change = 1.0
   else:
       absolute_change = 0.5
   ```

   A 0.1 step therefore produces card increments that core itself considers *insignificant* — four
   out of five taps would not even be reported to cloud assistants.

2. **Ergonomics.** A 0.1 step on the thermostat card's dial means 230 detents between 7 °C and
   30 °C. Nordic panel-heater peers ship coarse steps: `nobo_hub` uses whole degrees.

3. **Honesty about device resolution.** The step should describe what the *device* can act on. The
   Panel's control loop has hysteresis; advertising 0.1 °C implies a precision the hardware does not
   deliver.

Against 0.5: if the API genuinely accepts and stores 0.1 increments, a 0.5 step makes some
device-reachable values unreachable from the HA card (though still reachable via
`climate.set_temperature`, whose selector allows 0.1).

### Mechanics worth knowing

- `target_temperature_step` is a **capability attribute**, guarded by a walrus on *truthiness*:

  ```python
  if target_temperature_step := self.target_temperature_step:
      data[ClimateEntityCapabilityAttribute.TARGET_TEMP_STEP] = target_temperature_step
  ```

  A value of `0` therefore silently omits the attribute. There is **no core default** — when absent,
  the frontend picks its own step.
- **The step is never unit-converted.** `precision` is applied to temperatures via `display_temp`,
  but `target_temp_step` is passed through raw. A °C entity advertising `0.5` hands a Fahrenheit
  user a 0.5 °F step. Nothing we can do about it in the entity; just know it is a core wart, not
  our bug.
- `precision` is never exposed as an attribute — it only controls display rounding, and defaults to
  `PRECISION_TENTHS` for Celsius, `PRECISION_WHOLE` otherwise. `PRECISION_HALVES` (0.5) exists in
  `homeassistant/const.py` and is honoured by `display_temp`, but the climate component never
  references it.

**Recommendation:** `target_temperature_step = 0.5`, and leave `precision` at the Celsius default of
tenths so a device-reported `21.3` displays honestly rather than being rounded to `21.5`. Do **not**
set `precision = PRECISION_HALVES` to "match" the step — that would round away real device state.

Add a **conformance-checklist item**: what does the device do with a `21.3` write — store it, round
it, or reject it? That answer could justify revisiting 0.1.

---

## 6. Core integration survey — what integrations facing this actually do

**The core question — is a `target_temperature` that jumps on preset change acceptable, idiomatic,
or fought against? Answer: it is idiomatic. Multiple core integrations do it deliberately, one of
them documents it as the intended behaviour, and none of them fight it.**

Core contains three distinct patterns.

| Pattern | Integrations | Does `target_temperature` follow the preset? | `async_set_temperature` writes |
| --- | --- | --- | --- |
| **A. Preset selects the setpoint bank** — our shape | `zwave_js`, `overkiz` Somfy HTI, `overkiz` Atlantic Pass APC, `generic_thermostat` | **Yes, by design** | the *active* preset's stored setpoint |
| **B. Both setpoints exposed at once as a range** | `nobo_hub` | N/A — `target_temperature` is never implemented | **both** setpoints simultaneously |
| **C. One effective setpoint; a write creates an override** | `netatmo`, `tado`, `ecobee`, `honeywell`, `evohome`, `plugwise`, `homematicip_cloud`, `nexia`, `shelly` | Yes, but the *cloud* recomputes it | a temporary/permanent override, never the stored bank |

### Pattern A — the direct precedents

**`homeassistant/components/overkiz/climate/somfy_heating_temperature_interface.py`** — the closest
match to our device and the cleanest implementation. Two parallel tables, one to read the bank and
one to write it:

```python
MAP_PRESET_TEMPERATURES: dict[str, str] = {
    PRESET_COMFORT: OverkizState.CORE_COMFORT_ROOM_TEMPERATURE,
    PRESET_ECO: OverkizState.CORE_ECO_ROOM_TEMPERATURE,
    PRESET_AWAY: OverkizState.CORE_SECURED_POSITION_TEMPERATURE,
}

SETPOINT_MODE_TO_OVERKIZ_COMMAND: dict[str, str] = {
    OverkizCommandParam.COMFORT: OverkizCommand.SET_COMFORT_TEMPERATURE,
    OverkizCommandParam.ECO: OverkizCommand.SET_ECO_TEMPERATURE,
    OverkizCommandParam.SECURED: OverkizCommand.SET_SECURED_POSITION_TEMPERATURE,
}
```

The `target_temperature` property carries the design rationale in a comment — **this is the single
most load-bearing quote in this document**:

```python
# Allow to get the current target temperature for the current preset
# The preset can be switched manually or on a schedule (auto).
# This allows to reflect the current target temperature automatically
```

`async_set_temperature` writes the active bank, re-reading the live mode from device state rather
than trusting a cached property. `async_set_preset_mode` sends **mode only** — it never pushes a
temperature.

Overkiz also exposes the *same three setpoints* as `EntityCategory.CONFIG` numbers in
`homeassistant/components/overkiz/number.py`, so inactive banks remain reachable:

```python
# SomfyHeatingTemperatureInterface
OverkizNumberDescription(
    key=OverkizState.CORE_ECO_ROOM_TEMPERATURE,
    name="Eco room temperature",
    command=OverkizCommand.SET_ECO_TEMPERATURE,
    device_class=NumberDeviceClass.TEMPERATURE,
    native_min_value=6, native_max_value=29,
    entity_category=EntityCategory.CONFIG,
),
```

**This is the decisive finding: core does not treat preset-vs-number as either/or. Overkiz ships
both, for the same device, deliberately.**

**`homeassistant/components/zwave_js/climate.py`** — the strongest structural analogue, because
Heatit's own Z-Wave thermostats expose exactly this shape (Thermostat Setpoint CC has separate
`HEATING = 1` and `ENERGY_SAVE_HEATING = 11` setpoints). zwave_js merges Z-Wave's single mode list
into HA modes *and* presets by allowlist, then selects the setpoint through the active mode:

```python
@property
def _current_mode_setpoint_enums(self) -> list[ThermostatSetpointType]:
    """Return the list of enums that are relevant to the current thermostat mode."""
    if self._current_mode is None or self._current_mode.value is None:
        return [ThermostatSetpointType.HEATING]
    return THERMOSTAT_MODE_SETPOINT_MAP.get(int(self._current_mode.value), [])
```

with `ThermostatMode.HEATING_ECON: [ThermostatSetpointType.ENERGY_SAVE_HEATING]` in the map. So
**switching to the eco preset makes `target_temperature` start reporting the Energy Save Heating
setpoint**, and `async_set_temperature` writes whichever setpoint the active mode selects.

Its **notable failure** is instructive: `discovery.py` only creates a `Platform.CLIMATE` entity from
Thermostat Setpoint CC when Thermostat Mode CC is *absent*, so on a mode-capable thermostat the
**inactive setpoints are unreachable from the UI entirely** — you must switch preset first, or drop
to `zwave_js.set_value`. This is exactly the gap Overkiz's config numbers close.

**`homeassistant/components/generic_thermostat/climate.py`** — core's own reference thermostat
keeps a `_presets` name→temperature mapping, saves `_saved_target_temp` when entering a preset and
restores it on `PRESET_NONE`. Even the canonical example makes `target_temperature` jump on preset
change.

**`overkiz/climate/atlantic_electrical_heater_with_adjustable_temperature_setpoint.py`** —
acknowledges the ambiguity in two comments, and resolves it by making the read path and the write
path each pick a different state/command by mode:

```python
# core:TargetTemperatureState stays pinned to comfort in auto mode.
```
```python
# setTargetTemperature would overwrite comfort instead of the preset.
```

That second comment names the exact bug a naive implementation produces.

### Pattern B — `nobo_hub`, the option the ticket did not list

`homeassistant/components/nobo_hub/climate.py`. Nordic panel heaters — the **same product category
as ours** — storing `temp_comfort_c` and `temp_eco_c` per zone. It refuses the choice entirely:

```python
SUPPORT_FLAGS = (
    ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
)
PRESET_MODES = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]
```

`TARGET_TEMPERATURE` is **not** declared; `target_temperature` is never implemented. Both banks are
published at once:

```python
self._attr_target_temperature_high = int(self._nobo.zones[self._id][ATTR_TEMP_COMFORT_C])
self._attr_target_temperature_low = int(self._nobo.zones[self._id][ATTR_TEMP_ECO_C])
```

and `async_set_temperature` writes both together, ignoring a plain `ATTR_TEMPERATURE`. Preset
selects which is *live*; the numbers never move. Also note `hvac_modes = [HEAT, AUTO]` with no
`OFF`, and correspondingly **no `TURN_ON`/`TURN_OFF` flags** — consistent with §3.

Its `target_temperature_step` is `PRECISION_WHOLE` while `precision` is `PRECISION_TENTHS`,
confirming those are independent knobs.

### Pattern C and a useful borrow

Pattern C does not apply to us — we talk to a local device that stores banks, not a cloud that
computes an effective setpoint. But two ideas from it are worth stealing:

- **`ecobee`'s override sentinel.** When a hold is not based on a stored comfort setting, ecobee
  reports a synthetic preset: `PRESET_TEMPERATURE = "temp"`, commented `# Any hold not based on a
  climate is a temp hold`. If the Panel has a transient-override state, this is how to surface it.
- **`honeywell`'s retreat.** Its away setpoints live in **config entry options**, not on the device,
  with a docstring admitting why: *"Somecomfort does have a proprietary away mode, but it doesn't
  really work the way it should. For example: If you set a temperature manually it doesn't get
  overwritten when away mode is switched on."* A cautionary tale about trusting a device's bank
  semantics before we have hardware to check them against.

### Negative result: `mill`

`homeassistant/components/mill/climate.py` — Mill sells Nordic panel heaters with comfort/sleep/away
temperatures in its own app, and the HA integration models **none of it**. No `PRESET_MODE` feature,
no preset constants; just `_attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]` and the single live
setpoint. `mill/number.py` exposes only `max_heater_power`. A real integration in a real Nordic
panel heater shipped without solving this problem at all — evidence that "expose only the live
setpoint" clears the core bar, even if it is not the best answer.

### Prior art: `mattik-gh/heatit_wifi6` (not core)

The sibling-device HACS integration already picks **Pattern A**: `target_temperature` switches on
`operatingMode` (1 → heating setpoint, 2 → cooling, 3 → eco), with presets for eco and normal. Two
things it does that we should **not** copy:

- Its preset strings are `"ECO"` / `"NONE"` in that casing. Preset matching in core is exact and
  case-sensitive, and the translation/icon tables key on lowercase `eco` / `none` — so its presets
  render untranslated with the generic dot icon.
- It computes `hvac_modes` from current state (`[OFF, HEAT]` or `[OFF, COOL]` depending on the live
  mode), making the capability list flap. Ours are fixed: `[OFF, HEAT]`.

It also does not expose `min_temp`/`max_temp` from the device limits at all — it puts them in
`extra_state_attributes` instead, which is the thing §4 argues we should do properly.

---

## 7. Alternative modellings

### A. Eco as a preset, `target_temperature` follows the active bank (the handoff's proposal)

```
hvac_modes    = [OFF, HEAT]            panelMode 0 → OFF, 1/2 → HEAT
preset_modes  = [PRESET_COMFORT, PRESET_ECO]   panelMode 1 → comfort, 2 → eco
target_temperature = heatingSetpoint if panelMode==1 else ecoSetpoint
async_set_temperature writes the bank the device currently says is live
supported_features = TARGET_TEMPERATURE | PRESET_MODE | TURN_ON | TURN_OFF
```

**For**

- Directly precedented in core by `overkiz` Somfy HTI, `zwave_js`, `overkiz` Atlantic Pass APC and
  `generic_thermostat`. Not merely tolerated — the Somfy comment documents it as the *point*.
- `PRESET_ECO` is a standard constant with translations and an `mdi:leaf` icon in core's
  `icons.json`; the frontend and voice assistants understand it.
- The thermostat card does the obvious thing: the dial edits whatever is currently in charge.
- Survives the device changing bank on its own (a schedule, a physical button press) — the entity is
  a *view* onto whichever bank is live.

**Against**

- **`target_temperature` history becomes a step function** that mixes two physical quantities. A
  history graph of `temperature` shows 21 → 17 → 21 with no indication those are different stored
  values. Anyone charting it reads a setpoint change that never happened.
- **The inactive bank is unreachable** from the climate entity — precisely the `zwave_js` gap.
- **Automations reading `state_attr('climate.x','temperature')` become preset-dependent.** An
  automation that reads the target, adds 2, and writes it back will silently edit whichever bank
  happens to be live. This is the same class of bug as core#66071.
- If eco and heating have different device limits, `min_temp`/`max_temp` must jump too, compounding
  the §4 feedback loop.

### B. Eco as a second `HVACMode`

**This is not available.** `HVACMode` is a closed `StrEnum` (§1); there is no `eco` member and none
can be added by an integration. The only realisations are:

- `panelMode 2 → HVACMode.AUTO`. But `AUTO` is commented in core as *"The temperature is set based on
  a schedule, learned behavior, AI or some other related mechanism. User is not able to adjust the
  temperature"* — flatly untrue of an eco setpoint the user can edit. It would also mislead the
  frontend and every voice assistant.
- Abusing `COOL` or `DRY` — indefensible on a heater.

**Verdict: rule out.** The only argument for it was that `hvac_mode` is the entity *state* and so
gets first-class history — but that benefit is available under B′ (below) without lying about the
vocabulary. Note it would also *lose* preset translations and gain nothing that a preset does not
already provide.

### B′. Both setpoints at once via `TARGET_TEMPERATURE_RANGE` (`nobo_hub`'s answer)

```
supported_features = PRESET_MODE | TARGET_TEMPERATURE_RANGE   (no TARGET_TEMPERATURE)
target_temperature_high = heatingSetpoint
target_temperature_low  = ecoSetpoint
```

**For**

- **Nothing ever jumps.** Both banks are always visible, always editable, and history for
  `target_temp_high`/`target_temp_low` is honest — each series is one physical quantity.
- Core precedent from the *closest product category* we have (a Nordic panel heater).
- No unreachable bank, no `number` entities needed.
- Both are in `SIGNIFICANT_ATTRIBUTES`, so cloud assistants see changes to either.

**Against**

- **Semantic abuse.** The docs define `TARGET_TEMPERATURE_RANGE` as "a ranged target temperature.
  Used for HVAC modes heat_cool and auto" — a heat/cool deadband, not a comfort/eco bank. On a
  heat-only device there is no deadband. A core reviewer could legitimately object, and core
  inclusion is our stated bar.
- **Forces eco ≤ comfort.** Core raises `low_temp_higher_than_high_temp` if violated. That is
  *probably* physically sensible, but it is a constraint the device may not impose, and we cannot
  verify without hardware.
- Loses the single-setpoint dial: the thermostat card shows a range, and the user has no obvious
  "the temperature right now" number. For a wall heater this is a real UX regression.
- `climate.set_temperature` with a plain `temperature:` **fails** (core raises
  `missing_target_temperature_entity_feature`), breaking the most common automation people write
  against a heater. This is a significant compatibility cost.

### C. Eco setpoint as a separate `number`, climate stays single-setpoint

```
climate: target_temperature = heatingSetpoint always; preset still reports the live mode
number.eco_setpoint (EntityCategory.CONFIG) = ecoSetpoint
```

**For**

- Each entity is one physical quantity, so **history and statistics are clean** — and a `number`
  entity's state *is* its value, which means it gets first-class history without attribute
  archaeology.
- `async_set_temperature` is unambiguous; no read/write bank mismatch.
- Precedented — `overkiz/number.py` does exactly this.

**Against**

- **On its own it is a lie**: when `panelMode == 2` the device is chasing `ecoSetpoint`, but the
  climate entity would report `heatingSetpoint` as the target. The thermostat card would show a
  number the device is not pursuing. That is worse than a jump.
- The main dial does not control the device in eco mode, which users will report as a bug.

**C is not viable alone.** It is only viable as a *supplement*.

### The recommendation: A + C, which is what Overkiz actually ships

**Model eco as a preset with `target_temperature` following the live bank (A), and additionally
expose both stored setpoints as `EntityCategory.CONFIG` `number` entities (C).**

Reasoning, exposed for #8 to attack:

1. **A is the idiomatic core answer** and has the most precedent for our exact device shape. The
   Somfy HTI comment is core telling us this is the intended reading of `target_temperature`.
2. **C repairs A's two worst defects at low cost.** The unreachable-bank problem (`zwave_js`'s
   known gap) disappears, and the history problem is solved *in the right place*: automations and
   charts that care about a specific setpoint read `number.heating_setpoint` /
   `number.eco_setpoint`, which are single-quantity series, instead of a preset-dependent
   attribute.
3. **This combination already exists in core**, for a comfort/eco wall-heater interface, and passed
   review. That is the strongest possible answer to "will this clear the core bar?"
4. **B′ is the serious rival**, and #8 should weigh it rather than dismiss it. It is more honest
   about history and has same-category precedent. I rank it second because of the
   `set_temperature`-with-plain-`temperature` breakage and the deadband semantics — but if #8
   weights "never lie in history" above "never surprise an automation", B′ wins.

Implementation notes that fall out of the survey:

- **Re-read the active bank from device state inside `async_set_temperature`**, as Somfy HTI does,
  rather than trusting a cached `self.preset_mode` — otherwise a device-side bank switch racing the
  service call writes the wrong setpoint.
- **`async_set_preset_mode` must send mode only.** Every Pattern-A integration surveyed does this;
  pushing a temperature on preset change is what caused core#66071 (a preset switch clobbering the
  other bank until both read the same value).
- Use `PRESET_COMFORT` / `PRESET_ECO`, not `PRESET_NONE` / `PRESET_ECO`. `panelMode == 1` is a named
  state, not the absence of one, and `PRESET_COMFORT` gets a translation and `mdi:sofa`.
- The `number` entities must write the *named* bank unconditionally, never the live one.

### Consequences for history, statistics and automations

- **Long-term statistics are not affected either way.** Climate entities generate no long-term
  statistics; those come from `sensor` entities with a `state_class`. Only `number` and `sensor`
  entities would give a setpoint a durable statistical series — another point for C. Whether we
  *should* also mirror setpoints as `sensor`s is a genuine open question, not settled here.
- **Short-term recorder history** stores `temperature` as a state attribute on every climate state
  change. Under A it is a two-valued step function; under B′ it is two clean series; under A+C the
  clean series exist on the `number` entities.
- **`significant_change`** treats `preset_mode` as always significant and `temperature` as
  significant at 0.5 °C, so under A a preset switch and the accompanying setpoint jump are reported
  as one event to cloud assistants — no spurious churn.
- **Automations reading `state_attr(..., 'temperature')`** are the real hazard under A. The
  migration advice we should document for users: read
  `state_attr('number.…_heating_setpoint', 'state')` when they mean a specific bank, and the climate
  attribute only when they mean "whatever is live now".

---

## Open questions that deserve their own tickets

1. **Should the two setpoints also be mirrored as `sensor` entities** for long-term statistics?
   `number` gives history but the recorder's statistics engine treats `number` differently from
   `sensor`; if users want to chart setpoint-vs-consumption over months this matters. Not decided
   here.
2. **`hvac_action` source.** Does the Panel report relay/demand state at all? If not, `hvac_action`
   should be `None` rather than inferred. This is a conformance-checklist item that also changes the
   entity surface.
3. **Per-bank temperature limits.** If `minimumTemperatureLimit`/`maximumTemperatureLimit` bound the
   two setpoints differently, dynamic per-preset `min_temp`/`max_temp` follows — the case core has
   architecture#1164 on hold over.

## Sources

- [Climate entity — HA developer docs](https://developers.home-assistant.io/docs/core/entity/climate)
- [New entity features in Climate entity (2024-01-24)](https://developers.home-assistant.io/blog/2024/01/24/climate-climateentityfeatures-expanded/)
- `homeassistant/components/climate/{__init__,const,significant_change}.py`, `services.yaml`,
  `strings.json`, `icons.json` (core `dev`, plus tags 2024.1 – 2025.8 for the deprecation timeline)
- `homeassistant/components/{overkiz,zwave_js,nobo_hub,mill,generic_thermostat,netatmo,tado,ecobee,honeywell,evohome,plugwise,homematicip_cloud,nexia,shelly}/climate.py`
  and `overkiz/number.py`, `mill/number.py`, `zwave_js/discovery.py`
- `homeassistant/helpers/{entity,service,temperature}.py`
- [architecture#1164 — min/max in entity options](https://github.com/home-assistant/architecture/discussions/1164)
- [architecture#1154 — remove hvac_mode from set_temperature](https://github.com/home-assistant/architecture/discussions/1154)
- [architecture#1028 — generic precision configuration](https://github.com/home-assistant/architecture/discussions/1028)
- [core#62797 / #62811 — hvac_action off vs idle](https://github.com/home-assistant/core/issues/62797)
- [core#66071 — preset switch overwriting the other setpoint](https://github.com/home-assistant/core/issues/66071)
- [core#109304](https://github.com/home-assistant/core/issues/109304),
  [core#109865](https://github.com/home-assistant/core/issues/109865) — TURN_ON/TURN_OFF warnings
- [nobo_hub integration docs](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/nobo_hub.markdown)
- `mattik-gh/heatit_wifi6` `custom_components/heatit_wifi6/climate.py` (prior art, not core)
