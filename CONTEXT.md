# Heatit WiFi Panel

A Home Assistant integration for the Heatit WiFi Panel wall heater, over its local HTTP API. One context: the panel, its modes and setpoints, as Home Assistant sees them.

## Language

**Status**:
The panel's complete state in one document. The panel's only read endpoint returns it, computed fresh on each request. Everything the integration knows about a panel comes from a status. A poll is one status read. Do not confuse it with the *relay state*, the connectivity field inside the network block, or the success key in a write response. The wire calls all of those "status" too.
_Avoid_: status response, state, payload, device info

**Panel mode**:
The panel's three-way state, chosen by the user: Off, Heating, or Eco. It is one field on the device. Off replaces whichever on-mode was active.
_Avoid_: operating mode, HVAC mode, thermostat mode

**Comfort setpoint**:
The temperature the panel heats to in Heating mode. Wire name `heatingSetpoint`.
_Avoid_: heating setpoint, normal temperature, target

**Eco setpoint**:
The temperature the panel heats to in Eco mode. Wire name `ecoSetpoint`.
_Avoid_: energy-save setpoint, eco temperature

**Live setpoint**:
Whichever of the comfort and eco setpoints the panel is heating to right now. There is none when the panel mode is Off.
_Avoid_: active bank, current target, target temperature

**Setpoint bank**:
Either stored setpoint, seen as storage, whether or not it is live. Both banks survive mode changes. Both can be written in any mode.
_Avoid_: setpoint slot, profile

**Temperature limits**:
The panel's minimum and maximum bounds. The device enforces them on both setpoint banks. If a limit is narrowed past a stored setpoint, the device clamps that setpoint.
_Avoid_: range, min/max

**Relay state**:
Whether the heating element is on right now. Wire name `state`, values Idle and Heating. It does not depend on the panel mode. It changes several seconds before the reported power does.
_Avoid_: heating state, status, demand

**Open window detection**:
An optional panel feature. It infers an open window from a drop in temperature, then lowers the live setpoint until a countdown runs out. Wire object `OWD`: the setting is `openWindowDetection`, the detection is `activeNow`, the countdown is `activeTime`.
_Avoid_: OWD (in prose), window sensor

**Low temperature protection**:
An optional frost guard. It heats whenever the room falls below a threshold of 1–10 °C, in any panel mode. A threshold of 0 turns it off. Its threshold and its live state share one wire name, so keep them apart in prose. The vendor documents it. No panel has returned it.
_Avoid_: frost protection, LTP

**Load limit**:
The most power the panel will draw, in watts. The user chooses it, up to the rated load. Wire name `loadLimit`, stored in units of 100 W.
_Avoid_: power limit, max power

**Rated load**:
The panel model's maximum power in watts. The device reports it. It is never written. Wire name `maxLoad`, in units of 100 W.
_Avoid_: max load, model wattage

**Energy counter**:
The panel's total consumption in kWh since it was last zeroed. Wire name `totalConsumption`. The panel publishes it in steps of about 0.04 kWh, not continuously, so it sits flat and then jumps. The kWh reset zeroes it at once, whether from Home Assistant or the app.
_Avoid_: total consumption, kWh meter, energy meter

**Observed parameter**:
A parameter a real panel has returned in its status. Only observed parameters are modelled, exposed, or tested. A captured status is the evidence that admits one.
_Avoid_: present parameter, supported parameter

**Unobserved parameter**:
A parameter the vendor's document lists but no panel has yet returned. It is not absent and not unsupported. It has simply never been seen, so it is not modelled until it is.
_Avoid_: absent parameter, missing parameter, spec-only parameter

**Device id**:
The panel's own identifier, returned as `id`. It is 22 mixed-case letters and digits. It is used as-is and never lowercased. It is Home Assistant's identity for the panel, and the prefix of every entity's unique id.
_Avoid_: serial number, panel id, device identifier

**Assigned room**:
The free-text room name the MyHeatit app stores on the panel. Wire name `room`. An empty string means no room is assigned. It is read once, when the panel is added, and only to pick between the areas Home Assistant already has. It never creates an area. After that, Home Assistant's own area wins.
_Avoid_: area, zone, location

**Foreign panel**:
A panel answering at a configured address whose device id is not the one that address was set up for. Another unit has taken over the address. Its status is never accepted as data.
_Avoid_: wrong device, id mismatch (in prose), swapped panel

**Required core**:
The parts of a status without which the panel cannot be described at all: the device id, the relay state, the room temperature, the panel mode and both setpoint banks. A status missing any of them is not a status. If anything else is missing, only that one reading is unknown.
_Avoid_: mandatory fields, minimum schema

**Poll budget**:
The longest a single status read may take, including a retry, before the panel counts as unreachable for that poll. There is no grace period beyond it. A poll that uses up its budget makes the panel unavailable.
_Avoid_: timeout, poll timeout, grace period

**Poll interval**:
How often the integration reads a status. The user chooses it. It is different from the poll budget, which limits one such read.
_Avoid_: scan interval, update interval, refresh rate

**Write echo**:
The parameter value the panel returns along with its success acknowledgement. It reports what was *applied*, not what was requested. An off-step setpoint echoes back snapped to the grid. It also normalises types, so a float may come back as an integer. It is honest for every parameter but one. That is why it is trusted for the optimistic update and never for state.
_Avoid_: response value, confirmation, acknowledgement

**Silent undo**:
A write the panel acknowledged as successful and then did not apply. The next status shows the old value. The *write echo* says one thing and the following status says another. Seen once, when the external sensor mode was enabled with no sensor paired.
_Avoid_: lying echo, phantom write, rejected write

**Verified firmware**:
A firmware version for which a captured status from a real panel exists. A panel running any other version is unverified, not unsupported.
_Avoid_: supported firmware, known firmware, tested firmware

**Conformance claim**:
A falsifiable statement about panel behaviour that the integration depends on. It is phrased so a real device can settle it. It is held in the conformance register with the firmware it was verified on. Verified always means verified on one panel at one firmware, never verified outright.
_Avoid_: conformance test, checklist item, requirement

**Contradicted claim**:
A conformance claim that a later run disproved on a real panel. This is different from a claim the vendor's document merely disagrees with. That one was never true. A contradicted claim stopped being true, and shipped code rests on it.
_Avoid_: failed check, broken claim, regression

**Probe tier**:
The hazard class of a conformance check, and so what it takes to run one: a read, a benign write that reverts itself, a write that destroys data, a write that turns the heater on, or manual work no script may do.
_Avoid_: probe level, safety flag, risk level
