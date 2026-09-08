# Heatit WiFi Panel Heater — Home Assistant integration handoff

> **Superseded.** This is the originating brief, kept verbatim as the historical record. The design spec at `docs/spec/heatit-wifi-panel-v1.md` supersedes it wherever the two differ. In particular, the recommendation below to fork or crib from `mattik-gh/heatit_wifi6` was **rejected** (see `docs/adr/0001-no-fork-of-heatit-wifi6.md`); do not consult that repository when implementing.

## Goal

Build a Home Assistant integration (HACS custom component) for the **Heatit WiFi Panel** wall heater using its local HTTP API. No cloud, no auth, plain HTTP on the LAN.

Currently no HACS integration exists for the panel heater. There is one for the closely related **Heatit WiFi6 thermostat**: `mattik-gh/heatit_wifi6` on GitHub. Its API surface is almost identical (`/api/status`, `/api/parameters`, `/api/reset/kwh`), so it is a good starting point to fork/adapt. Heatit's official Works-with-HA integration covers Z-Wave products only.

## References

- OpenAPI spec (source of truth): https://documents.heatit.no/5430477/api — also saved locally as `API_Panel__1_.yaml` (OpenAPI 3.0.0, spec version 12.0.0, title "Heatit WiFi Panel")
- WiFi6 thermostat HACS integration to crib from: https://github.com/mattik-gh/heatit_wifi6
- Base URL: `http://<panel-ip>` (device must first be joined to WiFi via the MyHeatit app)

## API summary

### `GET /api/status`

Returns everything. Relevant fields:

```json
{
  "id": "sdf87g4bnfc87a523rbsdf4",
  "name": "Panel hall",
  "room": "hall",
  "state": "Idle",              // "Idle" | "Heating"  (is the element on right now)
  "currentPower": 1500,         // W, 0–1500
  "totalConsumption": 624.25,   // kWh, cumulative
  "roomTemperature": 22.2,      // °C
  "parameters": {
    "panelMode": 1,             // 0=Off, 1=Heating, 2=Eco
    "sensorCalibration": 0.0,   // -6.0..6.0
    "temperatureDisplay": false,// false=show setpoint, true=show measured
    "sensorMode": false,        // false=internal sensor, true=external wireless sensor
    "externalSensorFallback": true,
    "activeDisplayBrightness": 10,   // 1..10
    "standbyDisplayBrightness": 5,   // 0..10
    "heatingSetpoint": 21.0,    // 5.0..40.0
    "ecoSetpoint": 18.0,        // 5.0..40.0
    "minimumTemperatureLimit": 5.0,
    "maximumTemperatureLimit": 40.0,
    "lowTemperatureProtection": {
      "lowTemperatureProtection": 0,   // 0=disabled, 1..10 = °C threshold
      "activeNow": "disabled"          // "disabled" | "Idle" | "Heating"
    },
    "OWD": {
      "openWindowDetection": false,
      "activeNow": false,
      "activeTime": 0           // seconds left
    },
    "loadLimit": 15,            // 1..15, ×100 W
    "maxLoad": 15,              // model max, 4..15
    "disableButtons": 0         // 0=enabled, 1=disabled, 2=lock menu
  },
  "Network": {
    "SSID": "Home WiFi",
    "mac": "aa:bb:cc:11:22:33",
    "ipAddress": "192.168.1.10",
    "wifiSignalStrength": "65dBm",   // string, note the unit suffix
    "status": "ok"
  },
  "firmware": "1.2"
}
```

Note the inconsistent casing: `OWD` and `Network` are capitalised, everything else is camelCase.

### `POST /api/parameters`

Parameters go in the **query string**, not the body. At least one is required (422 otherwise). Multiple can be set at once. Accepted names are exactly the keys under `parameters` above (flat, e.g. `lowTemperatureProtection=3`, `openWindowDetection=true`).

```
POST http://192.168.1.10/api/parameters?heatingSetpoint=21.5&panelMode=1
```

Floats use one decimal (`^\d+\.\d{1}$`). Responses:

- `200` `{ "status": "success", "heatingSetpoint": 21.5, ... }` (echoes what was set)
- `400` `{ "status": "failed", "reason": "out of range." | "invalid data." }`
- `422` `{ "status": "failed", "reason": "You need to change at least one parameter." }`

### Reset endpoints (all `DELETE`)

- `/api/reset/kwh` — zero the kWh counter (expose as a button entity)
- `/api/reset/settings` — settings to defaults, keeps network/app pairing
- `/api/reset/factory` — full factory reset. **Do not expose in HA.**

### BlueFusion / DirectLink (optional, phase 2)

The panel can act as a hub for BLE devices ("BlueFusion", e.g. `BLE-Temp3` thermostat) and link to other Heatit WiFi devices ("DirectLink", `relayControl` / `masterThermostat`).

- `GET /api/bluefusion/devices` → `[{ id, name, device }]`
- `GET /api/bluefusion/{id}/status`, `POST /api/bluefusion/{id}/parameters`, `DELETE /api/bluefusion/{id}/reset/{factory|settings|kwh}`
- `GET|POST|DELETE /api/directlink`

Skip these for v1.

## Integration design

Domain: `heatit_wifi_panel` (keep distinct from `heatit_wifi6` so both can coexist).

### Config flow

- User enters host/IP (optionally name). Validate by `GET /api/status`; use `id` as `unique_id`, `name` as the default title.
- Optional later: zeroconf/DHCP discovery if the device advertises anything (unknown — check with `avahi-browse` on the LAN).
- Options flow: poll interval (default 30 s; WiFi6 integration uses 60 s).

### Coordinator

`DataUpdateCoordinator` polling `GET /api/status`. Use `aiohttp` via `async_get_clientsession`. After any `POST`, request a refresh so entities update immediately.

### Entities

**climate** (the main one)

- `hvac_modes`: `OFF` (panelMode 0), `HEAT` (panelMode 1)
- `preset_modes`: `none`, `eco` (panelMode 2). Selecting eco preset sets panelMode=2; selecting none sets 1.
- `current_temperature` ← `roomTemperature`
- `target_temperature` ← `heatingSetpoint` when mode 1, `ecoSetpoint` when mode 2; setting temperature writes the matching field
- `hvac_action` ← `state`: `HEATING` / `IDLE`, or `OFF` when panelMode 0
- `min_temp`/`max_temp` ← `minimumTemperatureLimit` / `maximumTemperatureLimit`
- `target_temperature_step` 0.5 (spec allows 0.1; 0.5 is nicer in UI)
- `temperature_unit` Celsius

**sensor**

- `currentPower` → power, W, `measurement`
- `totalConsumption` → energy, kWh, `total_increasing` (feeds the Energy dashboard)
- `roomTemperature` → temperature (redundant with climate but handy)
- `wifiSignalStrength` → parse the number out of `"65dBm"`, signal_strength, dBm, diagnostic
- `OWD.activeTime` → duration s, diagnostic
- `lowTemperatureProtection.activeNow` → enum, diagnostic

**binary_sensor**

- `OWD.activeNow` → window open detected
- `state == "Heating"` → heating (optional, duplicates hvac_action)

**number** (config category)

- `ecoSetpoint` (5–40, 0.5 step)
- `loadLimit` (1..`maxLoad`, step 1, unit ×100 W — consider showing as W by multiplying)
- `sensorCalibration` (-6..6, 0.1)
- `activeDisplayBrightness` (1..10), `standbyDisplayBrightness` (0..10)
- `minimumTemperatureLimit`, `maximumTemperatureLimit`
- `lowTemperatureProtection` (0..10)

**switch** (config category)

- `openWindowDetection`
- `temperatureDisplay`
- `sensorMode` (external sensor)
- `externalSensorFallback`

**select** (config category)

- `disableButtons`: enabled / disabled / lock menu

**button**

- Reset kWh counter (`DELETE /api/reset/kwh`)

### Device info

`identifiers={(DOMAIN, id)}`, `manufacturer="Heatit"`, `model="WiFi Panel"`, `sw_version=firmware`, `connections={(CONNECTION_NETWORK_MAC, Network.mac)}`, `suggested_area=room`.

### Repo layout (HACS)

```
custom_components/heatit_wifi_panel/
  __init__.py
  manifest.json      # domain, name, version, iot_class: local_polling, config_flow: true, requirements: []
  config_flow.py
  const.py
  coordinator.py
  api.py             # thin aiohttp client: get_status(), set_parameters(**kw), reset_kwh()
  climate.py
  sensor.py
  binary_sensor.py
  number.py
  switch.py
  select.py
  button.py
  strings.json
  translations/en.json
hacs.json            # {"name": "Heatit WiFi Panel", "render_readme": true}
README.md
```

Bump `manifest.json` version with each release; HACS uses GitHub releases/tags.

### Testing without hardware

Write `api.py` against the spec and mock `/api/status` with the example JSON above. Verify the query-string POST behaviour against a real device early — the spec says query params, but confirm the device doesn't also expect/accept JSON.

## Fallback: plain YAML, no custom component

If you just need it working quickly, a YAML package per heater:

```yaml
rest:
  - resource: http://192.168.1.10/api/status
    scan_interval: 30
    sensor:
      - name: "Panel hall temperature"
        value_template: "{{ value_json.roomTemperature }}"
        unit_of_measurement: "°C"
        device_class: temperature
      - name: "Panel hall power"
        value_template: "{{ value_json.currentPower }}"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
      - name: "Panel hall energy"
        value_template: "{{ value_json.totalConsumption }}"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
      - name: "Panel hall setpoint"
        value_template: "{{ value_json.parameters.heatingSetpoint }}"
        unit_of_measurement: "°C"
      - name: "Panel hall mode"
        value_template: "{{ value_json.parameters.panelMode }}"
    binary_sensor:
      - name: "Panel hall heating"
        value_template: "{{ value_json.state == 'Heating' }}"
        device_class: heat

rest_command:
  panel_hall_set:
    url: "http://192.168.1.10/api/parameters?{{ query }}"
    method: POST
```

Then a template `climate` (or `generic_thermostat` with a `switch` template) calling `rest_command.panel_hall_set` with `query: "heatingSetpoint=21.5"` / `query: "panelMode=0"`. This is fine for one or two heaters; the custom component is worth it beyond that.
