# The Heatit WiFi Panel API contract, as the OpenAPI spec actually states it

Research resolving [issue #5](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/5).

## Provenance

| | |
|---|---|
| Viewer page | <https://documents.heatit.no/5430477/api> — a Swagger UI HTML shell, **not** the document |
| Raw document | <https://documents.heatit.no/5430477/api-yaml> — served as `Content-Type: application/x-yaml` |
| Saved in-repo as | [`docs/api/heatit-wifi-panel-openapi.yaml`](../api/heatit-wifi-panel-openapi.yaml) |
| Retrieved | 2026-09-07 |
| SHA-256 | `af69a647148ea3a893d641b756149b29cd5193b9ef670ed853d92987e1f55433` |
| Size | 1174 lines / 39,974 bytes |
| `openapi` | 3.0.0 |
| `info.version` | 12.0.0 |
| `info.title` | Heatit WiFi Panel |

The viewer's inline script is the only pointer to the real document:

```js
const ui = SwaggerUIBundle({ url: "/5430477/api-yaml", dom_id: '#swagger-ui' });
```

The file parses cleanly as YAML. **Everything in §1–§11 is quoted or derived from that file**; where I state something the spec does *not* say, it is marked as such. Open questions about the *device* (as opposed to the *spec*) are collected in [§9](#9-what-the-spec-cannot-answer). [§12](#12-corroborating-evidence-from-the-sibling-device) is the one section drawing on outside evidence — code that runs against real Heatit hardware — and it is fenced off deliberately, because it concerns a *different product*.

**The headline finding, if you read nothing else:** the spec's transport claim (query-string parameters, no request body) is confirmed unambiguously at the source — and the only working integration for the sibling Heatit device ignores that identical claim and sends a JSON body instead. See §5.1 and §12.

### Transport, from `servers` and the absence of `security`

```yaml
servers:
  - description: Local HTTP API
    url: http://{APIUrl}
    variables:
      APIUrl:
        default: "192.168.1.100"
```

- Scheme is **`http`**, not https. No port in the template, so **port 80**.
- The string `security` appears **zero times** in the whole document, and there is no `components.securitySchemes`. **No authentication of any kind is specified** — anyone on the LAN can read status and write parameters.
- The base URL variable is a bare host/IP. There is no path prefix beyond `/api`.

---

## 1. Every endpoint

Twelve paths. Only the first five are in scope for v1 (see map issue #1: BlueFusion and DirectLink are out of scope).

| # | Method | Path | Params | Documented responses |
|---|---|---|---|---|
| 1 | `GET` | `/api/status` | none | **`200`** only |
| 2 | `POST` | `/api/parameters` | 15, **all `in: query`, all `required: false`** | `200`, `400`, `422` |
| 3 | `DELETE` | `/api/reset/factory` | `reset` (query, **not required**, enum `[Reset]`) | **`200`** only |
| 4 | `DELETE` | `/api/reset/settings` | `resetSettings` (query, **not required**, enum `[Reset]`) | **`200`** only |
| 5 | `DELETE` | `/api/reset/kwh` | `resetKwh` (query, **not required**, enum `[Reset]`) | `200`, `400` |
| 6 | `GET` | `/api/bluefusion/devices` | none | `200` |
| 7 | `GET` | `/api/bluefusion/{id}/status` | **none declared** (see defect D6) | `200` (example only, no schema) |
| 8 | `POST` | `/api/bluefusion/{id}/parameters` | **none declared at all** | `200`, `400`, `422` |
| 9 | `DELETE` | `/api/bluefusion/{id}/reset/factory` | `reset` (query, not required, enum `[Reset]`) | `200` |
| 10 | `DELETE` | `/api/bluefusion/{id}/reset/settings` | `resetSettings` (query, not required, enum `[Reset]`) | `200` |
| 11 | `DELETE` | `/api/bluefusion/{id}/reset/kwh` | `resetKwh` (query, not required, enum `[Reset]`) | `200` |
| 12 | `GET`/`POST`/`DELETE` | `/api/directlink` | GET none; POST `directLink`+`ipAddress` (both **required**); DELETE `directLink`+`device` (both optional) | `200` |

Four facts established by counting, which matter more than they look:

- **`requestBody` appears zero times in the document.** Not on `POST /api/parameters`, not anywhere. There is no JSON body contract for any operation.
- **`in: query` appears 25 times. `in: path` appears zero times.** Every documented parameter in the entire API is a query parameter.
- There is **no `GET /api/parameters`.** The `/api/parameters` path object contains only `post`. Parameters are readable *only* through `/api/status`.
- **`GET /api/status` documents no failure response at all** — no 4xx, no 5xx, no timeout semantics.

### 1.1 The reset endpoints have a query parameter the handoff omits

Each reset endpoint declares one optional query parameter whose schema is a string with an enum of exactly one value, `Reset`:

```yaml
  /api/reset/kwh:
    delete:
      parameters:
        - name: resetKwh
          description: Resets the Kwh counter to 0.
          in: query
          required: false
          schema:
            type: string
            enum:
              - Reset
```

Note the parameter *name changes per endpoint*: `reset` for factory, `resetSettings` for settings, `resetKwh` for kwh. `required: false` combined with a single-valued enum is self-defeating — it means the spec cannot tell us whether a bare `DELETE /api/reset/kwh` does the reset, or whether `?resetKwh=Reset` is the actual trigger and the bare call is a no-op. This is [Q7](#q7) and is the single highest-risk item for the kWh reset button.

### 1.2 Reset response shape is `reset`, not `status`

```yaml
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  reset:
                    $ref: "#/components/schemas/ResetInfo/properties/statusSuccess"
```

with

```yaml
    ResetInfo:
      properties:
        statusSuccess:
          type: string
          enum: [success]
        statusFailed:
          type: string
          enum: [failed]
```

So the **panel-level** resets return `{"reset": "success"}` (and `/api/reset/kwh` 400 returns `{"reset": "failed"}`), whereas **every other** endpoint in the API returns a `status` key. A client must not assume one envelope. `/api/reset/factory` and `/api/reset/settings` document **no failure response whatsoever**.

---

## 2. `GET /api/status` — the complete `DeviceInfo` schema

Top-level keys, in spec order: `id`, `name`, `room`, `state`, `currentPower`, `totalConsumption`, `roomTemperature`, `parameters`, `Network`, `firmware`.

| Field | Type | Pattern / enum | Range | Example | Notes |
|---|---|---|---|---|---|
| `id` | string | — | — | `sdf87g4bnfc87a523rbsdf4` | "Unique id for each device". No length, charset or format declared here (the `Devices` array's `id` does carry `format: id`; this one does not) |
| `name` | string | — | — | `Panel hall` | "Device name used in the MyHeatit app" — **not settable over this API** |
| `room` | string | — | — | `hall` | "The room the device is assigned to in the MyHeatit app" — **not settable over this API** |
| `state` | string | enum `Idle`, `Heating` | — | `Idle` | "Is the heating element currently on?" Capitalised values |
| `currentPower` | integer | `^\d+$` | 0 – **1500** | `1500` | "Power consumption in W" |
| `totalConsumption` | number (float) | `^\d+\.\d{2}$` — **two** decimals | none stated | `624.25` | "Total consumption in kWh". No max, no rollover documented |
| `roomTemperature` | number (float) | `^-?\d+\.\d{1}$` — **sign allowed** | none stated | `22.2` | "Current temperature measurement". No min/max: sub-zero readings are in-contract |
| `parameters` | object | — | — | — | §3 and §4 |
| `Network` | object | — | — | — | §2.2 |
| `firmware` | string | — | — | `"1.2"` | Quoted string in the spec |

### 2.1 Read-only members nested inside `parameters`

`parameters` mixes 15 writable settings with 4 read-only readings. The read-only ones:

| Field | Type | Enum / range | Example | Description (verbatim) |
|---|---|---|---|---|
| `parameters.maxLoad` | integer | 4 – 15, default 15 | — | "Maximum load the device can handle. Varies on the model of the device." |
| `parameters.lowTemperatureProtection.activeNow` | string | enum `disabled`, `Idle`, `Heating`; default `disabled` | `Idle` | "Shows the current state of the Low Temperature Protection." |
| `parameters.OWD.activeNow` | boolean | enum `false`, `true`; default `false` | `false` | "false = No open window detected. true = Open window detected. Setpoint is lowered." |
| `parameters.OWD.activeTime` | integer | `^\d+$`, default 0 | `3245` | "Seconds left until the Open Window Detection done." |

### 2.2 `Network`

Five fields, **none with an enum, pattern or format**:

| Field | Type | Example |
|---|---|---|
| `Network.SSID` | string | `"Home WiFi"` |
| `Network.mac` | string | `"aa:bb:cc:11:22:33"` — lowercase, colon-separated |
| `Network.ipAddress` | string | `192.168.1.10` — **no `format: ipv4`**, unlike DirectLink's `ipAddress` which does declare it |
| `Network.wifiSignalStrength` | string | `"65dBm"` — see §7 |
| `Network.status` | string | `ok` — **freeform, no enum.** `ok` is the only value the spec ever shows |

---

## 3. Every writable parameter

All 15 are declared under `components.parameters` (each `in: query`, `required: false`) and again under `components.schemas`. **This is the complete, authoritative table.**

| Parameter | Type | Range / enum | Default | Pattern | Unit / meaning | Read path in `/api/status` |
|---|---|---|---|---|---|---|
| `panelMode` | integer | enum `0`,`1`,`2`; min 0, max 2 | `1` | — | 0 = Off, 1 = Heating, 2 = Eco | `parameters.panelMode` |
| `sensorCalibration` | number (float) | −6.0 – 6.0 | `0.0` | `^-?\d+\.\d{1}$` | °C offset; step 0.1 implied by pattern | `parameters.sensorCalibration` |
| `temperatureDisplay` | boolean | enum `false`,`true` | `false` | — | false = display setpoint, true = display measured (**in standby mode**) | `parameters.temperatureDisplay` |
| `sensorMode` | boolean | enum `false`,`true` | `false` | — | false = internal sensor, true = external wireless sensor | `parameters.sensorMode` |
| `externalSensorFallback` | boolean | enum `false`,`true` | `true` | — | "what happens if the external sensor stops reporting": false = Off, true = internal sensor | `parameters.externalSensorFallback` |
| `activeDisplayBrightness` | integer | **1** – 10 | `10` | — | 1 = 10% … 10 = 100% | `parameters.activeDisplayBrightness` |
| `standbyDisplayBrightness` | integer | **0** – 10 | `5` | — | 0 = 0% … 10 = 100% | `parameters.standbyDisplayBrightness` |
| `heatingSetpoint` | number (float) | 5.0 – 40.0 | `21.0` | `^\d+\.\d{1}$` (**no sign**) | °C; step 0.1 implied | `parameters.heatingSetpoint` |
| `ecoSetpoint` | number (float) | 5.0 – 40.0 | `18.0` | `^\d+\.\d{1}$` | °C; step 0.1 implied | `parameters.ecoSetpoint` |
| `minimumTemperatureLimit` | number (float) | 5.0 – 40.0 | `5.0` | `^\d+\.\d{1}$` | °C | `parameters.minimumTemperatureLimit` |
| `maximumTemperatureLimit` | number (float) | 5.0 – 40.0 | `40.0` | `^\d+\.\d{1}$` | °C | `parameters.maximumTemperatureLimit` |
| `openWindowDetection` | boolean | *(no enum declared — see D5)* | `false` | — | false = disabled, true = enabled | **`parameters.OWD.openWindowDetection`** (nested) |
| `loadLimit` | integer | 1 – 15 | `15` | — | **×100 W**: "1=100W, 2=200W, etc." | `parameters.loadLimit` |
| `disableButtons` | integer | enum `0`,`1`,`2` | `0` | — | 0 = not disabled, 1 = disabled, 2 = lock menu | `parameters.disableButtons` |
| `lowTemperatureProtection` | integer | 0 – 10 | `0` | — | 0 = disabled; 1–10 = turn on below that value **in °C** | **`parameters.lowTemperatureProtection.lowTemperatureProtection`** (nested) |

Two asymmetries a client must hard-code:

- **`openWindowDetection`** is written flat (`?openWindowDetection=true`) but read from `parameters.OWD.openWindowDetection`.
- **`lowTemperatureProtection`** is written flat (`?lowTemperatureProtection=3`) but read from `parameters.lowTemperatureProtection.lowTemperatureProtection` — an object of the same name wrapping a scalar of the same name.

Every one of the 15 writable parameters is also readable. **There are no write-only parameters.**

---

## 4. Read-only vs writable, as a single list

**Writable (15):** `panelMode`, `sensorCalibration`, `temperatureDisplay`, `sensorMode`, `externalSensorFallback`, `activeDisplayBrightness`, `standbyDisplayBrightness`, `heatingSetpoint`, `ecoSetpoint`, `minimumTemperatureLimit`, `maximumTemperatureLimit`, `openWindowDetection`, `loadLimit`, `disableButtons`, `lowTemperatureProtection`.

**In `/api/status` but not settable (13):** `id`, `name`, `room`, `state`, `currentPower`, `totalConsumption`, `roomTemperature`, `parameters.maxLoad`, `parameters.lowTemperatureProtection.activeNow`, `parameters.OWD.activeNow`, `parameters.OWD.activeTime`, `Network.{SSID,mac,ipAddress,wifiSignalStrength,status}` (5), `firmware`.

`name` and `room` deserve special note: both are described as coming *from the MyHeatit app*, and there is no endpoint to change them. Home Assistant can read them but can never write them back, so they will drift if the user renames in the app.

---

## 5. The `POST /api/parameters` contract

### 5.1 Query string is confirmed, unambiguously

The operation object lists exactly 15 `$ref`s into `components.parameters`. **Every one of those resolves to a definition carrying `in: query`.** The operation has **no `requestBody`** — and neither does any other operation in the document. There is no schema, no content type, and no example anywhere describing a JSON body for a parameter write. The handoff's claim is correct and now verified at the source.

```
POST http://192.168.1.10/api/parameters?heatingSetpoint=21.5&panelMode=1
```

`description: Change parameters on the device. At least one parameter is required.` — but every parameter is `required: false`, because OpenAPI 3.0 cannot express "at least one of". That gap is exactly what the `422` exists to plug at runtime.

> ⚠️ **The spec is confirmed, and the only code known to work against real Heatit hardware ignores it.** The shipping HACS integration for the sibling WiFi6 thermostat sends parameter writes as a **JSON request body**, not a query string, and has done so since its first release. That does not overturn the reading above — it means the *spec's* transport claim and the *device's* accepted transport may be two different things. See [§12](#12-corroborating-evidence-from-the-sibling-device) before writing `api.py`.

### 5.2 The float pattern and what it implies

Four setpoint-family parameters carry `pattern: '^\d+\.\d{1}$'`; `sensorCalibration` carries `pattern: '^-?\d+\.\d{1}$'`.

Read literally, that regex requires: one or more digits, then a literal `.`, then **exactly one** digit, anchored at both ends. Therefore, *if the device enforces the documented pattern*:

| Sent | Matches `^\d+\.\d{1}$`? | Consequence |
|---|---|---|
| `21.5` | yes | accepted |
| `21.0` | yes | accepted |
| **`21`** | **no** — no decimal point | **rejected** (`400 invalid data.`) |
| **`21.50`** | **no** — two decimals | **rejected** |
| `21.55` | no | rejected |
| `.5` | no — `\d+` needs ≥1 digit before the dot | rejected |
| `5.` | no | rejected |
| `021.0` | yes — `\d+` permits leading zeros | accepted |
| `+21.0` | no | rejected |
| **`-1.0` as `sensorCalibration`** | yes (that schema has `-?`) | accepted |
| `-1.0` as `heatingSetpoint` | no (`-?` absent) | rejected — harmless, the minimum is 5.0 anyway |

**So yes: `21` fails where `21.0` succeeds**, on the spec's own terms. The client must format every float parameter as exactly one decimal place — `f"{value:.1f}"` — and must never let Python's default `str(21.0)` → `"21.0"` (fine) or `str(21)` → `"21"` (fatal) leak through. A 21.0 arriving from Home Assistant as an `int` 21 is the realistic failure mode.

Two caveats worth stating plainly:

- In JSON Schema, `pattern` applies **only to strings**, and these schemas declare `type: number`. So `pattern` on a `type: number` is formally inert — a spec-conformance validator would ignore it entirely. It is nonetheless the only statement we have about the device's *string* validator, and since query parameters are transported as text, treating it as the wire format is the right reading. But it is an inference, not a guarantee — see [Q1](#q1).
- **Integer parameters carry no pattern at all.** `panelMode`, `activeDisplayBrightness`, `standbyDisplayBrightness`, `loadLimit`, `disableButtons`, `lowTemperatureProtection` have `type: integer` and nothing else. Whether the device rejects `panelMode=1.0` — or, worse, silently truncates it — **the spec does not say** ([Q2](#q2)). Send bare integers.

### 5.3 Boolean serialisation is completely undefined — the biggest latent bug

Four parameters are `type: boolean` *query* parameters: `temperatureDisplay`, `sensorMode`, `externalSensorFallback`, `openWindowDetection`. A query string carries text, so a boolean must be rendered as characters, and the spec **never states which characters**. There is no `style`, no `explode`, no `pattern`, no `example` on any of the four parameter definitions. The response *examples* show JSON booleans (`temperatureDisplay: true`), which says nothing about the request encoding.

OpenAPI's default for a query parameter is `style: form, explode: true`, which for a boolean yields lowercase `true` / `false`. That is the best available reading. But:

```python
urllib.parse.urlencode({"openWindowDetection": True})   # -> 'openWindowDetection=True'
aiohttp.ClientSession().post(url, params={"x": True})   # -> TypeError in aiohttp
```

Python will not produce `true` for you. `aiohttp` outright refuses non-`str`/`int` param values. So the client must explicitly map `True → "true"`, `False → "false"`, and a conformance probe must establish whether the device also accepts `1`/`0` or `True`/`False`. See [Q3](#q3).

### 5.4 The documented `200` schema contradicts its own examples

```yaml
        "200":
          content:
            application/json:
              schema:
                oneOf:
                  -  $ref: "#/components/schemas/panelMode"     # type: integer
                  -  $ref: "#/components/schemas/sensorCalibration"  # type: number
                  ...
```

The `oneOf` branches resolve to **scalar** schemas — `panelMode` is `type: integer`, `heatingSetpoint` is `type: number`. But every example under the same response is an **object**:

```yaml
                Panel Mode (MODE):
                  value:
                    status: success
                    panelMode: 1
```

A schema validator would reject all sixteen of the spec's own examples against the spec's own declared schema. Worse, `oneOf` of scalars cannot express the documented "Multiple parameters at the same time" example, which echoes all 15 keys plus `status` in one object. **The examples are the usable contract; the declared schema is wrong.** Treat the real 200 body as:

```json
{ "status": "success", "<each parameter that was set>": <its new value> }
```

with `status` and the echoed values being the only things we can rely on — and note that even the echoed *key names* are not trustworthy on the BlueFusion side (see D7), which lowers confidence that the Panel side echoes exactly the names sent ([Q5](#q5)).

### 5.5 Error shapes

Both error responses declare an untyped two-string object. **Neither `status` nor `reason` carries an `enum` — `reason` is freeform.**

**`400 Failed`:**

```yaml
              schema:
                type: object
                properties:
                  status: { type: string }
                  reason: { type: string }
              examples:
                Failed:  { value: { status: failed, reason: out of range. } }
                Failed2: { value: { status: failed, reason: invalid data. } }
```

Two `reason` strings are exemplified — **`"out of range."` and `"invalid data."`, both with a trailing full stop** — but the schema does not constrain `reason` to them. There is no documented mapping from a failed parameter *name* to the error; if you set three parameters and one is bad, the spec does not say which failed, whether the other two applied, or whether the whole write is atomic ([Q4](#q4)).

**`422 Validation Error - At least one parameter needs to be changed`:**

```json
{ "status": "failed", "reason": "You need to change at least one parameter." }
```

Here `status` and `reason` carry `example:` values inline rather than `enum:` — still freeform.

**Client rule: branch on the HTTP status code and on `status == "success"`. Never parse or match `reason` strings** — they are unenumerated, punctuated inconsistently across the document, and are the vendor's to change.

Note the 422's description, "At least one parameter needs to be **changed**". If that is literal — as opposed to "at least one parameter must be supplied" — then re-writing a parameter to the value it already holds could return 422 rather than 200. That is a materially different contract for Home Assistant, which routinely writes idempotent values. [Q6](#q6).

---

## 6. Casing — confirmed exactly, and there is more of it than the handoff records

A parser must match these byte-for-byte. Verified against the schema source:

| Key | Casing | Where |
|---|---|---|
| `OWD` | **all caps** | `DeviceInfo.parameters.OWD` |
| `Network` | **PascalCase** | `DeviceInfo.Network` |
| `SSID` | **all caps** | `DeviceInfo.Network.SSID` — **the handoff does not flag this one** |
| `mac` | all lowercase, and it is `mac`, **not `macAddress`** | `DeviceInfo.Network.mac` — while `/api/directlink` uses `macAddress` for the same concept |
| `ipAddress` | camelCase | `Network.ipAddress` |
| `status` | lowercase | `Network.status` |
| everything else | camelCase | — |

So `Network` is internally inconsistent on its own: `SSID` all-caps, `mac` all-lower, `ipAddress`/`wifiSignalStrength`/`status` camel. And the same concept is named `mac` here and `macAddress` in DirectLink. Value casing matters too: `state` is `"Idle"`/`"Heating"` (capitalised), and `lowTemperatureProtection.activeNow` mixes cases within one enum — `"disabled"` lowercase but `"Idle"`/`"Heating"` capitalised.

---

## 7. `wifiSignalStrength` — the sign question

The complete declaration is four lines:

```yaml
            wifiSignalStrength:
              type: string
              description: Wifi signal strength
              example: "65dBm"
```

What is established:

1. It is a **`type: string`**, not a number. Confirmed.
2. There is **no `pattern`**, no `enum`, no `format`. The only evidence about its shape in the entire document is the single example `"65dBm"`.
3. The example is **`"65dBm"` — unsigned, no space, suffix `dBm`, lowercase `d`, capital `B`, lowercase `m`**.
4. **The sign is not documented anywhere.** Neither the description nor any pattern says whether the device emits `-65dBm`, `65dBm`, or something else.

This matters because Home Assistant's `SensorDeviceClass.SIGNAL_STRENGTH` with `dBm` expects a **negative** number; WiFi RSSI is essentially always negative (roughly −30 dBm excellent to −90 dBm unusable). A raw `65` charted as dBm is not just cosmetically wrong, it inverts the good/bad reading.

Three possibilities, and the spec cannot distinguish them:

- The device emits `"-65dBm"` and the spec's example simply dropped the minus (common in hand-written examples).
- The device emits `"65dBm"` meaning −65 dBm, i.e. the magnitude with the sign implied.
- The device emits an unsigned value that is genuinely not RSSI-in-dBm.

**Recommended client behaviour**, pending hardware: parse with a signed regex such as `^\s*(-?\d+)\s*dBm\s*$` (case-insensitively, tolerating whitespace), take the captured integer, and if it is **positive, negate it** before publishing as `signal_strength`; if negative, pass through. Log once at debug when the negation fires, so a firmware that starts emitting the sign is visible. And treat a parse failure as `None` rather than raising — a diagnostic sensor must never take the coordinator down. This is a *workaround for an ambiguity*, and it must be recorded as such in the conformance checklist, not baked in silently. [Q10](#q10).

---

## 8. Where the spec contradicts itself — defect register

Independent of the device, the document has internal defects. A downstream implementer will hit these.

| ID | Defect |
|---|---|
| **D1** | `POST /api/parameters` `200` declares `oneOf` of **scalar** schemas while all sixteen of its own examples are **objects**. The declared schema is unusable; the examples are the real contract. (§5.4) |
| **D2** | `pattern` is applied to `type: number` schemas, where JSON Schema defines `pattern` as string-only. Formally inert; treated here as the device's wire-format validator. (§5.2) |
| **D3** | `currentPower` has a hard `maximum: 1500`, but `maxLoad` ranges 4–15 (i.e. 400 W–1500 W models). On a 400 W panel the documented maximum is meaningless. Likewise `loadLimit`'s `maximum: 15` does not scale down with `maxLoad`. |
| **D4** | Reset endpoints return a `reset` key; everything else returns a `status` key. `/api/reset/factory` and `/api/reset/settings` document **no** failure response. (§1.2) |
| **D5** | Three of the four boolean schemas (`temperatureDisplay`, `sensorMode`, `externalSensorFallback`) declare `enum: [false, true]`; `openWindowDetection` does not. Cosmetic, but it shows the schemas were maintained by hand. |
| **D6** | Five BlueFusion paths contain `{id}`, and **`in: path` appears zero times in the document** — the path parameter is never declared. Invalid OpenAPI. |
| **D7** | The BlueFusion examples are mutually inconsistent: status shows `minimumTemperatureLimit` / `operatingMode` while the POST echo shows `minimumTemperature` / `operationMode`; `heatingSetpoint`, `coolingSetpoint` and `ecoSetpoint` all echo back as a single key `setpoint`; `disableButton` is `0` in one example and `true` in another; `OWD.openWindowDetection` is integer `0` there but boolean on the Panel. **Direct evidence that these examples are hand-written and not generated from the firmware** — which is the reason to distrust the Panel examples too. |
| **D8** | `status` values are punctuated inconsistently across the document: `"success"` on parameters, `"success."` **with a trailing period** on DirectLink POST and DELETE. Another reason never to match on strings loosely. |
| **D9** | `Network.ipAddress` has no `format`, while `/api/directlink`'s `ipAddress` declares `format: ipv4`. Same concept, different rigour. |
| **D10** | `POST /api/bluefusion/{id}/parameters` declares **no parameters and no requestBody** — the operation is undocumented apart from its responses. |
| **D11** | Every parameter on `POST /api/parameters` is `required: false`, yet the description says at least one is required. Unrepresentable in OpenAPI 3.0; enforced only at runtime by the 422. |
| **D12** | Reset query parameters are `required: false` with a single-valued enum, leaving it undefined whether the parameter is what triggers the reset. (§1.1) |

---

## 9. What the spec cannot answer

Thirty-eight questions the document leaves open. Every one is a question **only a real device settles**. This is the seed for the hardware conformance checklist (issue #13). Each is phrased so a probe script can answer it, and each is numbered so downstream tickets can cite it.

Q8, Q3, Q7 and Q13 are the four that can each independently break a user-visible feature, and should lead the probe script.

### Encoding and the write path

<a id="q1"></a>**Q1. Is the float pattern actually enforced?** Send `heatingSetpoint=21` (no decimal). Does it return `400 invalid data.`, or does it succeed? Then send `21.50` (two decimals) and `21.55`. The spec's `^\d+\.\d{1}$` predicts all three fail; the device may be laxer. *If `21` is accepted, the one-decimal formatting rule is a nicety rather than a requirement — but we should keep it either way.*

<a id="q2"></a>**Q2. Do integer parameters reject decimals?** Send `panelMode=1.0`, `loadLimit=5.0`, `activeDisplayBrightness=7.5`. Does the device 400, truncate, round, or accept? The spec says nothing — the integer schemas carry no pattern.

<a id="q3"></a>**Q3. How must booleans be spelled on the wire?** For each of `temperatureDisplay`, `sensorMode`, `externalSensorFallback`, `openWindowDetection`, try `true`/`false`, `True`/`False`, `1`/`0`, `TRUE`/`FALSE`, `yes`/`no`. Which are accepted? Which are silently misread (e.g. does `False` parse as truthy)? **A silent misread is worse than a rejection** and would produce a switch entity that appears to work and does the opposite.

<a id="q4"></a>**Q4. Is a multi-parameter write atomic?** Send one valid and one out-of-range parameter in the same request (e.g. `?heatingSetpoint=22.0&loadLimit=99`). Does the valid one apply? Does the response say which one failed? Does the echo include the applied one? This decides whether the integration may batch writes at all, or must send one parameter per request.

<a id="q5"></a>**Q5. Does the 200 echo use the exact parameter names that were sent?** BlueFusion's examples rename keys in the echo (D7). Confirm the Panel does not. Also: does the echo carry the *requested* value or the *device's clamped* value?

<a id="q6"></a>**Q6. Does writing a parameter to its current value return 200 or 422?** The 422 is described as "at least one parameter needs to be **changed**". If unchanged writes 422, the integration must diff against coordinator state before writing, and must not treat that 422 as an error. This is a real Home Assistant pattern (a user re-selecting the current preset) and is easy to get wrong.

<a id="q7"></a>**Q7. Do the reset endpoints need their query parameter?** Compare `DELETE /api/reset/kwh` against `DELETE /api/reset/kwh?resetKwh=Reset`. Does the bare call reset the counter, no-op with a 200, or 400? Is the enum value case-sensitive (`Reset` vs `reset`)? **Getting this wrong means a kWh reset button that returns success and does nothing.**

<a id="q8"></a>**Q8. Which transport does the Panel actually accept — query string, JSON body, or both?** *This is now the highest-priority probe in the whole checklist.* The spec says query only (no `requestBody` anywhere); the shipping WiFi6 integration uses a JSON body exclusively and works (§12). Probe all four cells: query-only, body-only, both together, neither (expect 422). Record the status code and body for each. **A client that guesses wrong here does nothing at all**, and — because the WiFi6 code never inspects HTTP status codes — it may fail *silently*.

<a id="q9"></a>**Q9. What HTTP hygiene does the firmware need?** Does `POST` with `Content-Length: 0` and no body work at all (aiohttp's default for a body-less POST — the exact shape a query-string-only client produces)? Does it require or reject `Content-Type: application/json`? Does it tolerate `Connection: keep-alive` and connection reuse, or must each request open a fresh TCP connection? Does it need a trailing slash? Does it handle HTTP/1.1 chunked, `Expect: 100-continue`, or a HEAD request? **Does it set a correct `Content-Type` on its own responses?** — the WiFi6 device does not (§12), which makes `aiohttp`'s `response.json()` unusable. Embedded HTTP stacks routinely fail on one of these.

<a id="q36"></a>**Q36. Is the success sentinel `"success"` or `"Success"`?** The Panel spec says lowercase `success` everywhere. The working WiFi6 client matches on capital-`S` `"Success"` and would log an error on every write if the device disagreed (§12). Case-insensitive comparison is the obvious defence, but confirm the actual byte string — and confirm the same for `"failed"`.

<a id="q37"></a>**Q37. Is the `200` body of a parameter write `{status, <echoed param names>}` as the Panel spec's examples show, or `{status, value}` as the WiFi6 client expects?** These are incompatible shapes (§12, D1). A client must tolerate both, or we must know which.

### The `Network` block

<a id="q10"></a>**Q10. Is `wifiSignalStrength` signed?** Read `/api/status` at strong and weak signal. Record the *exact* string. Is it `"-65dBm"` or `"65dBm"`? Is there whitespace? Is the suffix always `dBm`? Does it ever return an empty string, `"0dBm"`, or a non-numeric value while reconnecting? (§7)

<a id="q11"></a>**Q11. What are the real values of `Network.status`?** The spec shows only `ok` and declares no enum. Observe during a WiFi drop and reconnect. Any value we might want to surface as a diagnostic or use to detect degraded connectivity.

<a id="q12"></a>**Q12. What casing does `Network.mac` actually use?** The example is lowercase-with-colons, but DirectLink's `macAddress` example is uppercase. Home Assistant's `CONNECTION_NETWORK_MAC` expects a normalised form; confirm what to normalise from.

### Semantics the spec never states

<a id="q13"></a>**Q13. Which setpoint governs in `panelMode=2` (Eco)?** The spec never links `panelMode` to `ecoSetpoint`. Does the panel regulate to `ecoSetpoint` in Eco mode? Does `heatingSetpoint` still show in the display? **The handoff's climate design depends entirely on this** and has no support in the spec.

<a id="q14"></a>**Q14. Does writing `heatingSetpoint` while in Eco mode succeed, and does it do anything?** And conversely, `ecoSetpoint` while in Heating mode. This decides whether the climate entity may write the setpoint without first switching mode.

<a id="q15"></a>**Q15. Are `minimumTemperatureLimit` / `maximumTemperatureLimit` actually enforced on setpoints?** Set min to 18.0, then try `heatingSetpoint=10.0`. Is it rejected with 400, clamped to 18.0, or accepted? And is `min < max` itself enforced — can you set `minimumTemperatureLimit=30.0` while `maximumTemperatureLimit` is 20.0?

<a id="q16"></a>**Q16. Do the temperature limits also constrain `ecoSetpoint` and `lowTemperatureProtection`?** Unstated. `lowTemperatureProtection` ranges 1–10 °C, which can sit below a `minimumTemperatureLimit` of, say, 15.0 — do they interact?

<a id="q17"></a>**Q17. Can `loadLimit` exceed `maxLoad`?** Its schema max is a static 15 regardless of model. On a device reporting `maxLoad: 4`, does `loadLimit=15` return 400, clamp to 4, or succeed and misbehave? **The handoff's number entity assumes a dynamic 1..maxLoad range — that is a design choice the spec does not license.**

<a id="q18"></a>**Q18. What does `state` report when `panelMode=0` (Off)?** The enum is only `Idle`/`Heating` — there is no `Off`. Presumably `Idle`, but that must be confirmed before mapping `hvac_action`.

<a id="q19"></a>**Q19. What does `state` report while OWD or low-temperature protection is actively overriding?** `OWD.activeNow: true` lowers the setpoint; `lowTemperatureProtection.activeNow` has its own `Heating` value. Do the two `Heating` indicators agree? Can `lowTemperatureProtection.activeNow == "Heating"` while `state == "Idle"`?

<a id="q20"></a>**Q20. Does `currentPower` report instantaneous draw or a duty-cycle average?** And is it exactly 0 when idle and exactly `loadLimit × 100` when heating, or does it vary? This decides whether `state_class: measurement` on a power sensor produces anything meaningful, and whether HA's Riemann-sum integration would be a better energy source than `totalConsumption`.

<a id="q21"></a>**Q21. How does `totalConsumption` behave across a kWh reset and a reboot?** Does `DELETE /api/reset/kwh` zero it immediately? Does it survive a power cycle? Does it ever decrease on its own, or roll over at some maximum? **`state_class: total_increasing` in Home Assistant treats any decrease as a meter reset** — this is the discontinuity flagged as unresolved fog in map issue #1, and it is a device question, not a spec one.

<a id="q22"></a>**Q22. Is `totalConsumption` really two decimals, and what is its update cadence?** The `^\d+\.\d{2}$` pattern implies 10 Wh resolution. Does it tick every poll, or only every few minutes? A stale-looking energy sensor is a support burden.

<a id="q23"></a>**Q23. Does `sensorCalibration` shift `roomTemperature` in `/api/status`, or only the display?** Determines whether the temperature sensor is pre- or post-calibration.

<a id="q24"></a>**Q24. What does `roomTemperature` return when `sensorMode=true` (external sensor) and the external sensor is absent or silent?** Does it fall back per `externalSensorFallback`, return the last value, return `0.0`, or omit the field? **Does it ever return `null`, or omit a field entirely?** The spec declares no `required` list on `DeviceInfo`, so *every field is formally optional* — a client must tolerate any of them being missing. Which ones actually can be?

<a id="q25"></a>**Q25. Is `OWD.activeTime` a countdown, and what is it when inactive?** Described as "seconds left until the Open Window Detection done", default 0, example 3245. Does it count down while `activeNow` is true and sit at 0 otherwise? A monotonic-per-poll countdown makes a poor sensor unless we know its cadence.

### Identity, discovery and lifecycle

<a id="q26"></a>**Q26. Is `id` stable?** Does it survive a reboot, a settings reset, a firmware update, a WiFi change? Does `DELETE /api/reset/factory` change it? It is the proposed Home Assistant `unique_id`; if it churns, every entity is orphaned. What is its actual charset and length (the example is 23 lowercase alphanumerics)?

<a id="q27"></a>**Q27. What do `name` and `room` contain before the device is assigned in the MyHeatit app?** Empty string, `null`, or a default? The config flow uses `name` as the title and `room` as `suggested_area`.

<a id="q28"></a>**Q28. Does the panel advertise anything discoverable — mDNS/zeroconf, SSDP, a recognisable DHCP hostname or MAC OUI?** Nothing in the spec touches discovery. This decides whether the config flow can offer zeroconf/DHCP discovery, which affects the HACS/core quality tier.

<a id="q29"></a>**Q29. What does the device return for an unknown path, e.g. `GET /api/nonexistent`?** JSON, an HTML error page, or a connection reset? The config flow must distinguish "this is a Heatit panel" from "this is some other web server at that IP" — and `GET /api/status` documents **no** error response, so we have nothing to go on. What is the cheapest reliable fingerprint?

<a id="q30"></a>**Q30. Are there rate limits, and how many concurrent connections does it accept?** No 429, no 503, and no concurrency guidance anywhere in the document. Embedded HTTP servers commonly serve one connection at a time. What poll interval is safe? What happens if a write lands while a status poll is in flight? **The proposed default of 30 s across multiple panels needs a real answer** — and the WiFi6 evidence (§12) is that simultaneous connections to several units cause timeouts, which is why that integration staggers startup by 2 s per device and opens a fresh session per request. Probe: how many parallel requests before failures, and does keep-alive/connection reuse work at all?

<a id="q31"></a>**Q31. How long after a successful write does `/api/status` reflect the new value, and how long does a write itself take?** If there is a lag, the "refresh immediately after write" pattern will read back stale data and the UI will visibly bounce. The WiFi6 client uses a **20 s** POST timeout against a **5 s** GET timeout and carries an explicit anti-stale guard for setpoints (§12) — evidence that writes are slow (likely a flash commit) and that read-back-after-write did misbehave for someone. Measure both; they determine the timeout budget and whether we need optimistic state or a delayed refresh.

<a id="q38"></a>**Q38. Is a retried write idempotent?** If a write times out but was in fact applied, is re-sending it harmless? The WiFi6 client retries POSTs up to 4 times with no idempotency guard (§12). For a setpoint this is harmless; think about whether it is harmless for every parameter, and for `DELETE /api/reset/kwh` in particular.

<a id="q32"></a>**Q32. What happens on reboot or WiFi loss?** Does the HTTP server come up before WiFi associates? Does it hold connections open and time out, or refuse fast? This shapes retry/backoff and `ConfigEntryNotReady`.

<a id="q33"></a>**Q33. Does the device only answer on port 80, plain HTTP?** Any HTTPS listener, any alternate port, any redirect?

<a id="q34"></a>**Q34. Does `DELETE /api/reset/settings` change `id`, `name`, `room`, or the parameter defaults to exactly the spec's stated defaults?** The spec's per-parameter `default:` values are our only claim about post-reset state; confirm at least a sample of them.

<a id="q35"></a>**Q35. Does the firmware version in `/api/status` correspond to the spec version 12.0.0?** The example device reports `firmware: "1.2"`, which is nowhere near 12.0.0 — so the two are independent numbering schemes. Which firmware(s) does spec 12.0.0 describe? Is there any endpoint or header exposing an API version? **Without this we cannot gate features on firmware**, which map issue #1 lists as open fog.

---

## 10. Disagreements with the handoff's paraphrase

`.orca/drops/heatit-wifi-panel-ha-integration.md` is accurate in its main lines — the endpoint list, the query-string write, the `parameters` example JSON field-for-field and in spec order, the flat-write/nested-read asymmetry, the `loadLimit` ×100 W scaling, the `maxLoad` range, the `disableButtons` and `panelMode` enums, and the OWD/Network casing flag are all correct. The following are wrong, incomplete, or overreach.

| # | Handoff says | Spec says | Severity |
|---|---|---|---|
| 1 | Reset endpoints are just `DELETE /api/reset/{kwh,settings,factory}` | Each declares an optional query parameter with enum `[Reset]`, differently named per endpoint (`reset`, `resetSettings`, `resetKwh`). Whether it is required in practice is undefined | **High** — a kWh button that silently no-ops |
| 2 | (silent on reset responses) | Panel resets return **`{"reset": "success"}`**, not `{"status": ...}`; only `/api/reset/kwh` documents a 400 | **High** — an `api.py` checking `status` sees nothing |
| 3 | "Floats use one decimal (`^\d+\.\d{1}$`)" — stated once, globally | Correct for the four setpoint params. **`sensorCalibration` is `^-?\d+\.\d{1}$`** (sign permitted). A client applying the unsigned pattern to a negative calibration would reject its own valid value | **High** |
| 4 | (silent) | Boolean query serialisation is **undefined**. Python's natural encoding produces `True`, not `true` | **High** — four switch entities |
| 5 | `400 { "reason": "out of range." \| "invalid data." }` reads as a closed set | `reason` has **no enum**; those are `examples`, freeform, and the document punctuates status strings inconsistently elsewhere (`"success."`) | Medium — don't branch on `reason` |
| 6 | Casing note covers `OWD` and `Network` | Also **`SSID`** all-caps, and `Network.mac` is `mac` here but `macAddress` in DirectLink | Medium |
| 7 | (silent on defaults) | Every writable parameter has an explicit `default:` — `panelMode` 1, `heatingSetpoint` 21.0, `ecoSetpoint` 18.0, `min` 5.0, `max` 40.0, `activeDisplayBrightness` 10, `standbyDisplayBrightness` 5, `loadLimit` 15, `sensorCalibration` 0.0, `externalSensorFallback` **true**, the rest false/0 | Medium — free information the handoff drops |
| 8 | `roomTemperature: 22.2  // °C` | Pattern is `^-?\d+\.\d{1}$` with **no min or max** — sub-zero readings are in-contract | Low–Medium — don't clamp or assume positive |
| 9 | `totalConsumption: 624.25 // kWh, cumulative` | Pattern is `^\d+\.\d{2}$` — **two** decimals, unlike every other float in the API. "Cumulative" is the handoff's word; the spec only says "Total consumption in kWh" and documents no rollover | Low–Medium |
| 10 | `wifiSignalStrength: "65dBm" // string, note the unit suffix` | Correct as far as it goes, but the handoff's sensor design then says "parse the number out" with **no negation and no acknowledgement that the sign is undocumented**. `65 dBm` published to HA is wrong in the direction that matters | **High** (see §7) |
| 11 | `"externalSensorFallback": true` with no gloss | false = **Off**, true = fall back to **internal sensor**. A switch labelled "External sensor fallback" is ambiguous without this | Low |
| 12 | `temperatureDisplay` "false=show setpoint, true=show measured" | Correct, but the spec adds **"in standby mode"** — it does not change the active display | Low |
| 13 | Number entity: `loadLimit` (1..`maxLoad`) | The spec's `loadLimit` maximum is a **static 15** irrespective of `maxLoad`. Deriving the range from `maxLoad` is a sensible design choice but is **not** licensed by the spec — record it as an assumption, not a reading | Medium (design) |
| 14 | Climate: `target_temperature` ← `ecoSetpoint` when mode 2 | The spec **never connects `panelMode` to `ecoSetpoint`**. Nothing states which setpoint governs in Eco. The whole preset design rests on an unverified assumption | **High** (design) |
| 15 | Climate: `min_temp`/`max_temp` ← the limit parameters | Plausible, but the spec never says the limits constrain `heatingSetpoint`; both limits and both setpoints independently span 5.0–40.0 | Medium (design) |
| 16 | "spec allows 0.1 [step]; 0.5 is nicer in UI" | Confirmed — the one-decimal pattern permits 0.1 for all four setpoint params and for `sensorCalibration` | ✅ correct |
| 17 | "Parameters go in the query string, not the body" | **Confirmed as a reading of the spec**: `requestBody` occurs zero times in the document; all 15 params resolve to `in: query`. But the handoff presents this as settled fact about the *device*, and the shipping WiFi6 integration — the only code known to work against real Heatit hardware — sends a **JSON body** against an identically-worded spec (§12) | ✅ correct about the spec; **unsafe as an assumption about the device** |
| 19 | "Verify the query-string POST behaviour against a real device early — the spec says query params, but confirm the device doesn't also expect/accept JSON" | The handoff was right to flag this, and understated it. It is not a "confirm the device doesn't also accept JSON" — there is positive evidence the sibling device accepts *only* what the spec doesn't document (§12) | Credit where due; severity raised |
| 20 | Coordinator: "Use `aiohttp` via `async_get_clientsession`" | The WiFi6 client deliberately opens a **fresh session and connector per request** with `trust_env=False` and a `ThreadedResolver`, and staggers multi-device startup, after filed issues about simultaneous connections timing out (§12). A shared pooled session may be exactly wrong here | Medium (design) |
| 21 | (silent) | The WiFi6 device returns JSON with a **wrong or missing `Content-Type`**, so `response.json()` fails; that client parses `response.text()` instead and tolerates empty/HTML bodies (§12) | Medium — a one-line trap in `api.py` |
| 18 | Also saved locally as `API_Panel__1_.yaml` | That file is not in this repo. The document is now vendored at `docs/api/heatit-wifi-panel-openapi.yaml` with a recorded SHA-256 | Housekeeping |

---

## 11. Consequences for the design sketched in the handoff

Things in the spec that suggest the handoff's design is wrong or under-determined:

1. **The Eco preset is built on sand.** Mapping `preset_mode: eco` → `panelMode=2` and re-pointing `target_temperature` at `ecoSetpoint` assumes a relationship the spec never asserts (Q13, Q14). If Eco in fact regulates to something else, the climate entity misreports the setpoint in one of its two modes. This needs either hardware or a deliberately conservative design (e.g. expose `ecoSetpoint` only as a `number`, and keep `target_temperature` always on `heatingSetpoint`).
2. **`state` has no `Off` value.** The enum is `Idle`/`Heating` only, so `hvac_action` when `panelMode=0` has to be synthesised from `panelMode`, not read (Q18). The handoff does this correctly but does not note that the spec forces it.
3. **The `loadLimit` number entity's dynamic range is invented.** Defensible, but it is a decision, not a reading (Q17).
4. **`totalConsumption` + `total_increasing` + a reset button is a genuinely unresolved interaction** (Q21), and the reset button may not even fire without its query parameter (§1.1). Two independent hazards stacked on one entity.
5. **The `wifiSignalStrength` sensor as specified will publish a positive dBm** (§7). Needs the negation rule and a conformance note.
6. **Batching writes is unvalidated.** The handoff's `set_parameters(**kw)` signature implies multi-parameter writes, which the spec's "Multiple parameters at the same time" example supports — but partial-failure behaviour is undefined (Q4). The API client's error contract cannot be finalised until that is known.
7. **The `422`-on-unchanged reading (Q6)** would make every idempotent write an error. Worth designing defensively for now: treat 422 as non-fatal and re-poll.
8. **Nothing in the spec supports discovery** (Q28), so the config flow is manual-host-entry only until hardware says otherwise — relevant to the HACS/core quality tier the map is targeting.
9. **The transport itself may be wrong** (§12, Q8). The handoff's `api.py` sketch is fine structurally, but the one line inside it that matters most — `params=` vs `json=` — is the one the spec is least trustworthy about. Design that call site to be swappable and probe it first.
10. **The coordinator's session strategy may be wrong** (§12.2, Q30). `async_get_clientsession` with keep-alive is the idiomatic Home Assistant answer and may be the wrong answer for this hardware.

### Decisions that deserve their own ticket

- **The `POST /api/parameters` wire encoding** (Q1–Q3, Q8, Q9, Q37). This is the single decision map issue #1 identifies as concentrating the hardware risk, and §12 turns it from a theoretical worry into a documented instance of this vendor's spec being wrong about exactly this. It is now sharp enough to ticket on its own, and it is bigger than "floats and booleans": it is **query string vs JSON body vs both**, plus the float format, plus the boolean spelling, plus response parsing that cannot rely on `Content-Type`. Pick a default, state the fallback, and specify the probe that settles it in its first five requests.
- **HTTP client posture** (Q9, Q30, Q31, Q38) — shared pooled `aiohttp` session vs a fresh connection per request, timeouts (asymmetric read/write?), retry policy and its idempotency, and startup staggering across multiple panels. The handoff assumes `async_get_clientsession`; the prior art deliberately does the opposite after real failures. This interacts with the multi-panel topology fog already noted in map issue #1.
- **The `wifiSignalStrength` sign policy** (§7, Q10) — negate-if-positive vs publish-raw vs omit the sensor until confirmed. Small, but it is a user-visible correctness call being made on an undocumented field.
- **Whether the integration writes parameters singly or batched** (Q4), which is really "what is the `api.py` error contract".
- **Reset-endpoint invocation form** (§1.1, Q7) — whether to always send `?resetKwh=Reset`, and whether the button entity should verify by re-polling `totalConsumption`.

---

## 12. Corroborating evidence from the sibling device

Everything above §11 is derived from the Panel spec alone. This section is different in kind: it is evidence from **code that demonstrably runs against real Heatit hardware**, namely [`mattik-gh/heatit_wifi6`](https://github.com/mattik-gh/heatit_wifi6) (v1.1.2, `iot_class: local_polling`) and the fork [`lvlie/heatit_wifi6`](https://github.com/lvlie/heatit_wifi6).

**Read the caveat first.** The WiFi6 is a *different product* with a *different spec* (the repo vendors `Heatit_WiFi6_OpenAPI_v70.yaml` — version 7.0, against our 12.0.0). Its parameter set genuinely diverges: `operatingMode` instead of `panelMode` (with a fourth value, 3 = Eco), three separate temperature readings instead of one `roomTemperature`, `sizeOfLoad` instead of `loadLimit`/`maxLoad`, and no `lowTemperatureProtection` at all. So nothing here *proves* anything about the Panel. What it does is tell us **which parts of a Heatit OpenAPI document have historically turned out not to match the firmware** — and that is exactly the signal we need, given that we are designing against a spec with no device to check it on.

### 12.1 The transport disagreement

The WiFi6 spec declares its parameters `in: query` with no `requestBody`, **exactly as our Panel spec does**. The working client sends a JSON body anyway:

```python
async def _post(self, endpoint, data, timeout=15, retries=2):
    url = f"{self.__host}{endpoint}"
    ...
    async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
```

```python
async def set_parameter(self, parameter, value) -> dict:
    data = {parameter: value}
    response = await self._post(API_PARAMETERS.rstrip("/"), data, timeout=20, retries=3)
```

So the wire call is `POST /api/parameters` with body `{"heatingSetpoint": 21.5}` and `Content-Type: application/json`, **one parameter per request** — it never batches. This is not a recent regression: the first published commit (Sept 2025) already used `json=`, `params=` has never appeared in the file's history, and the independent `lvlie` rewrite also chose `json=`. Across roughly a year, three contributors and several bug reports about other things, nobody has reported "writes don't work".

**The honest reading:** the WiFi6 firmware accepts a JSON body. Whether it *also* accepts the query string is untested by that code, and whether the **Panel** accepts a body is entirely unknown. Two products, two firmwares. But a vendor spec that is wrong about transport on one device is weak evidence for the same spec family on another, and the cost of guessing wrong is a completely non-functional integration.

**Recommended posture for the Panel spec document:** specify the query string as primary (it is what *our* spec documents, and it is the only thing we have a source for), but design `api.py` so the transport is a single swappable call site, and make [Q8](#q8) the first item on the conformance checklist. Sending both simultaneously is tempting and should be *considered but not assumed safe* — a firmware that parses both could apply one and echo the other.

### 12.2 Other places the WiFi6 spec proved wrong about its own device

Each of these is a place where the vendor document and the working code disagree, and the code wins. Every one has a direct analogue in our Panel spec.

| WiFi6 spec says | Working code does | Panel analogue |
|---|---|---|
| `status: success` (lowercase) in reset examples | matches `response.get("status") == "Success"` — **capital S**. A lowercase device reply would make every write log an error and return `{}`, i.e. visibly broken. So the device almost certainly returns `"Success"` | Our spec says lowercase `success` throughout, and `ResetInfo` even pins it with `enum: [success]`. [Q36](#q36) — compare case-insensitively |
| POST 200 returns a parameter object | code reads back a **`value`** key: `response.get("value", ...)` — implying `{"status": ..., "value": ...}` | Our spec's declared 200 schema is already self-contradictory (D1). [Q37](#q37) |
| `state` is `type: boolean` | code matches the strings `"Idle"` / `"Heating"` / `"Cooling"` — the declared type is simply wrong | Our `state` is correctly `type: string` with enum `Idle`/`Heating`. Probably fine, but it shows schema types are not reliable |
| `network` (lowercase) | `data.get("network", {})` | **Our spec says `Network`, capitalised.** Either the two devices genuinely differ or one spec is wrong. A parser must not guess — [Q12](#q12) extended: confirm the exact top-level key. *Defensive option: look up both keys.* |
| — | `OWD` capitalised on both, and `SSID` capitalised inside the network object on both | Consistent with our reading in §6 — good corroboration |
| — | JSON responses arrive with a **wrong or missing `Content-Type`**, so `response.json()` cannot be used. The code has an explicit workaround with a comment saying so, and also tolerates empty and non-JSON (HTML) bodies | Directly applicable. Parse `await response.text()` and `json.loads` it; never `response.json()`. Folded into [Q9](#q9) |
| — | fresh `TCPConnector` + `ClientSession` **per request**, no keep-alive, no pooling; `trust_env=False`; `ThreadedResolver` instead of aiodns | Suggests a single-connection embedded server. [Q30](#q30) |
| — | POST timeout **20 s** with **3 retries** and linear backoff, versus a 5 s GET timeout — added explicitly after observed "POST call timeout errors" | Writes are slow. [Q31](#q31), [Q38](#q38) |
| — | startup staggered `index * 2 + 2` seconds per device, after two filed issues about simultaneous connections timing out most units | **Directly relevant to the multi-panel topology fog in map issue #1.** [Q30](#q30) |
| — | HTTP status codes are **never inspected** — no `raise_for_status()`, no `response.status`. A 400 or 422 is parsed as if it were a 200 | Which is *why* that repo can tell us nothing about error behaviour. Our client should do better, and our checklist must cover it ([Q4](#q4)) |

### 12.3 What the prior art does *not* settle

- **Boolean encoding ([Q3](#q3)) is still open.** The WiFi6 integration never writes a boolean parameter — its two booleans are read-only there. And because it uses a JSON body, it would have emitted a real JSON `true` anyway, which is precisely the case that a query-string client gets wrong (`urlencode` yields `True`). No help.
- **`wifiSignalStrength` ([Q10](#q10)) is still open, and now more firmly so.** Neither repo parses it: upstream exposes the raw string as an attribute, and the fork deliberately publishes it as a sensor with *no* unit and *no* device class. Nobody has ever been forced to discover the sign. The WiFi6 spec's example is also unsigned. So the ambiguity is real, not an artefact of one hand-written example — and the negate-if-positive rule in §7 remains a workaround, not a fact.
- **Float formatting ([Q1](#q1), [Q2](#q2)) is untested.** The WiFi6 code applies no formatting at all; Python's float repr happens to keep `21.0` as `21.0` inside JSON. Over a query string that accident does not hold.
- **kWh reset behaviour ([Q7](#q7), [Q21](#q21)) is untested.** The WiFi6 `reset_device()` sends `DELETE /api/reset/kwh` with **no query parameter** — which matches our spec's `required: false` — but it is **dead code**, never wired to any entity, so it has plausibly never run against hardware.

### 12.4 The one thing this changes in the design

The map (issue #1) states that the hardware risk "concentrates in a single decision — how a parameter write is encoded". That was the right call, and this evidence sharpens it from a theoretical worry into a **known, documented instance of this vendor's spec being wrong about exactly that**. The Panel spec document should therefore treat the encoding as a *parameterised* decision with a stated default and a stated fallback, not as settled fact — and the probe script should answer it in its first five requests.
