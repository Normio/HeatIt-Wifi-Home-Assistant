# Heatit WiFi Panel

A Home Assistant integration for the Heatit WiFi Panel wall heater over its local HTTP API. One context: the panel, its modes and setpoints, as Home Assistant sees them.

## Language

**Panel mode**:
The panel's three-way state selected by the user: Off, Heating, or Eco. One field on the device; Off replaces whichever on-mode was active.
_Avoid_: operating mode, HVAC mode, thermostat mode

**Comfort setpoint**:
The temperature the panel regulates to in Heating mode. Wire name `heatingSetpoint`.
_Avoid_: heating setpoint, normal temperature, target

**Eco setpoint**:
The temperature the panel regulates to in Eco mode. Wire name `ecoSetpoint`.
_Avoid_: energy-save setpoint, eco temperature

**Live setpoint**:
Whichever of the comfort and eco setpoints the panel is currently regulating to. There is none when the panel mode is Off.
_Avoid_: active bank, current target, target temperature

**Setpoint bank**:
Either stored setpoint considered as storage, independent of whether it is live. Both banks persist across mode changes and can be written in any mode.
_Avoid_: setpoint slot, profile

**Temperature limits**:
The panel's minimum and maximum bounds, enforced by the device on both setpoint banks. Narrowing a limit past a stored setpoint clamps that setpoint on the device.
_Avoid_: range, min/max

**Relay state**:
Whether the heating element is currently on. Wire name `state`, values Idle and Heating. Independent of panel mode; leads the reported power by several seconds.
_Avoid_: heating state, status, demand

**Open window detection**:
The panel's optional feature that infers an open window from a temperature drop and lowers the live setpoint until a countdown expires. Wire object `OWD`: the setting `openWindowDetection`, the detection `activeNow`, the countdown `activeTime`.
_Avoid_: OWD (in prose), window sensor

**Low temperature protection**:
An optional frost guard that heats whenever the room falls below a threshold of 1–10 °C, in any panel mode; a threshold of 0 turns it off. Its threshold and its live state share one wire name and must be kept apart in prose. Documented by the vendor; unobserved.
_Avoid_: frost protection, LTP

**Load limit**:
The maximum power the panel will draw, in watts, chosen by the user up to the rated load. Wire name `loadLimit`, stored in units of 100 W.
_Avoid_: power limit, max power

**Rated load**:
The panel model's maximum power in watts, reported by the device and never written. Wire name `maxLoad`, in units of 100 W.
_Avoid_: max load, model wattage

**Energy counter**:
The panel's cumulative consumption in kWh since it was last zeroed. Wire name `totalConsumption`. Published in steps of roughly 0.04 kWh rather than continuously, so it sits flat and then jumps; zeroed immediately by the kWh reset, from Home Assistant or the app.
_Avoid_: total consumption, kWh meter, energy meter

**Observed parameter**:
A parameter a real panel has returned in its status. Only observed parameters are modelled, exposed, or tested; a captured status is the evidence that admits one.
_Avoid_: present parameter, supported parameter

**Unobserved parameter**:
A parameter the vendor's document lists that no panel has yet returned. Neither absent nor unsupported: simply never seen, and so not modelled until it is.
_Avoid_: absent parameter, missing parameter, spec-only parameter

**Device id**:
The panel's own identifier, returned as `id`: 22 mixed-case alphanumerics, used verbatim and never lowercased. Home Assistant's identity for the panel, and the prefix of every entity's unique id.
_Avoid_: serial number, panel id, device identifier

**Assigned room**:
The free-text room name the MyHeatit app stores on the panel, wire name `room`, an empty string when no room is assigned. Read once when the panel is added, as a suggestion only; Home Assistant's own area wins from then on.
_Avoid_: area, zone, location

**Foreign panel**:
A panel answering at a configured address whose device id is not the one the address was set up for; another unit has taken over the address. Its status is never accepted as data.
_Avoid_: wrong device, id mismatch (in prose), swapped panel

**Required core**:
The parts of a status without which the panel cannot be described at all: the device id, the relay state, the room temperature, the panel mode and both setpoint banks. A status missing any of them is not a status; anything else missing leaves only its own reading unknown.
_Avoid_: mandatory fields, minimum schema

**Poll budget**:
The longest a single status read may take, retry included, before the panel counts as unreachable for that poll. There is no grace beyond it: a poll that exhausts its budget makes the panel unavailable.
_Avoid_: timeout, poll timeout, grace period

**Poll interval**:
How often the integration reads a status, chosen by the user. Distinct from the poll budget, which bounds one such read.
_Avoid_: scan interval, update interval, refresh rate

**Silent undo**:
A write the panel acknowledged as successful and then did not apply, so the next status shows the old value. Observed once, when the external sensor mode was enabled with no sensor paired.
_Avoid_: lying echo, phantom write, rejected write

**Verified firmware**:
A firmware version for which a captured status from a real panel exists. A panel running any other version is unverified, not unsupported.
_Avoid_: supported firmware, known firmware, tested firmware
