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
