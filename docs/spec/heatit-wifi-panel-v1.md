# Heatit WiFi Panel — Home Assistant integration, v1 design spec

A Home Assistant custom integration (HACS custom component) for the **Heatit WiFi Panel** wall
heater, over the panel's local HTTP API. Domain `heatit_wifi_panel`. Python, async, `aiohttp`.

This document is complete enough to build v1 from with **no decisions left to make**. Where it
states a device behaviour, that behaviour was observed on a real panel; where it states a Home
Assistant convention, that convention was read from `docs/core/integration-quality-scale/rules/*` or
from core source, not from the "Building integrations" documentation pages.

---

## 0. How to read this document

**It is frozen at v1.** Corrections go into [§15 Amendments](#15-amendments), dated, rather than
being edited into the body — so a reviewer comparing shipped code against this document can see
which parts were corrected under fire and which were right from the start.

**It does not contain the conformance checklist.** That is a *living* register at
[`docs/conformance/checklist.md`](../conformance/checklist.md), which grows and whose rows flip; a
frozen document cannot hold it. [§12](#12-hardware-conformance) introduces it and links it, and the
probe script it drives is specified there.

**Three claims are kept apart throughout**, and the difference matters:

| | |
|---|---|
| *the vendor document says X* | evidence, never truth. Ten places it is simply wrong are catalogued in the register as `disagrees`. |
| *this panel does X* | one 600 W unit at firmware **1.21**. Every measurement here carries that qualifier. |
| *every panel does X* | never claimed. The register exists so a second panel can find out where we were wrong. |

**Observed beats documented.** The parameter registry, the entity table and every test fixture hold
only what a real panel has **returned**. A parameter enters with a captured fixture or not at all.
The vendor's OpenAPI document proposes; hardware disposes.

Vocabulary is defined once, in [`CONTEXT.md`](../../CONTEXT.md). Terms in *italics* on first use
here are glossary entries — *panel mode*, *comfort setpoint*, *live setpoint*, *relay state*,
*required core*, *silent undo*, *write echo* and the rest. Use them; do not drift to the synonyms
each entry lists under *Avoid*.

---

## 1. Scope and non-goals

### In scope for v1

The whole panel as the local API exposes it: one climate entity, both *setpoint banks*, the
*temperature limits*, display and button settings, the *load limit*, *open window detection*, power,
energy and diagnostics — **21 entities** across eight platforms. Config flow with DHCP IP-follow, a
reconfigure flow, an options flow, diagnostics, a full offline test suite, CI, and HACS packaging.

The quality bar is a **HACS default repository** listing, and nothing beyond it.

### Out of scope, and why

| Excluded | Reason |
|---|---|
| **BlueFusion** (`/api/bluefusion/*`, the panel as a BLE hub) | Deferred. The vendor document's own BlueFusion examples disagree with each other on field names, so it would need its own research effort. |
| **DirectLink** (`/api/directlink`, `relayControl` / `masterThermostat`) | Deferred for the same reason. |
| **`DELETE /api/reset/factory` as an entity** | A factory reset unpairs the panel from the MyHeatit app and strands it off WiFi. A mis-tapped dashboard button is an unacceptable way to trigger that. The endpoint is also **not implemented** on firmware 1.21 — the ruling holds by construction as well as by discipline. |
| **Home Assistant core inclusion** | Priced and rejected. Core requires all device code in a published PyPI package with sdists and a public CI publish pipeline, forbids the `version` key HACS requires, rejects the `documentation` URL core itself mandates (so no single `manifest.json` serves both), and limits a new integration's first PR to a single platform against our eight-platform surface. If core is ever wanted it is a fresh effort, not a resumption. |
| **The API client as a published library** | Existed only to serve core. HACS imposes nothing and the split gates the platinum tier alone. The client is a module inside the integration; the *discipline* of keeping device I/O free of `homeassistant` imports survives, justified by testability (§3.2). |
| **A `home-assistant/brands` pull request** | The brands repository auto-closes new `custom_integrations/` PRs, and since HA 2026.3 custom integrations ship brand assets in-tree. Authoring the assets is in scope (§10); opening that PR is a wasted cycle. |
| **A YAML `rest:` / `rest_command:` fallback** | Solves a different problem — one or two heaters, right now — and competes with this integration rather than leading to it. |
| **Executing the conformance checklist in full** | Specifying it is in scope (§12) and is a required deliverable. Running every row, across more than one firmware, is a separate effort — though it *is* a gate on HACS submission (§11). |

---

## 2. The device

Everything in this section was observed on a real panel at firmware **1.21**, `model`
`"Heatit WiFi Panel Heater"`, `maxLoad: 6` (a 600 W unit), except where marked *unobserved*. The
vendor's OpenAPI document (version 12.0.0) is vendored at
[`docs/api/heatit-wifi-panel-openapi.yaml`](../api/heatit-wifi-panel-openapi.yaml) and is cited only
where it is the sole source or where the device overturned it.

### 2.1 Transport

- **Plain HTTP on tcp/80.** No TLS, no alternate port, no redirect, no authentication of any kind:
  anyone on the LAN can read and write. Of tcp 22/23/80/443/1900/5000/5353/8080/8123/8266/9999/49152
  only 80 answers.
- **HTTP/1.1 only.** An HTTP/1.0 request is refused with `505 Version Not Supported`.
- Responses carry `Content-Length`; the panel never uses chunked transfer. Response headers are
  `Content-Type` and `Content-Length` **only** — no `Date`, no `Server`, no API-version header.
- **Keep-alive is honoured.** An idle socket was still served after 65 s.
- Read latency 28–213 ms fresh, 52–214 ms reused — bimodal around ~30 ms and ~205 ms. **Connection
  reuse buys nothing measurable.**
- **Accept backlog ≈ 4–5.** Two and four parallel connections are served cleanly; at eight, three
  waited 1.2 s for a SYN retransmit before being accepted. No request failed at any count.
- **`GET /api/status` is computed per request**, not served from a cache: over 24 samples across
  120 s, `wifiSignalStrength` alternated between consecutive 5 s reads.

### 2.2 Endpoints

Four, and only four, are used:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/status` | The whole *status*. The only read. `HEAD` returns `405`. |
| `POST` | `/api/parameters?<name>=<value>` | One parameter per request (§2.4). |
| `DELETE` | `/api/reset/kwh?resetKwh=Reset` | Zeroes the *energy counter*. |
| `DELETE` | `/api/reset/settings` | Parameters to defaults; keeps network, pairing, `id`, `name`, `room`. |

There is **no `GET /api/parameters`** — parameters are readable only through the status. An unknown
path returns `404`, `Content-Type: text/html`, body `Nothing matches the given URI` (a CherryPy
default). `GET /`, `GET /api`, `GET /api/status/` and `GET /api/Status` are all that same 404, so
paths are case-sensitive, a trailing slash is not tolerated, and **the panel serves no web UI** —
which is why the integration ships no `configuration_url`.

`/api/reset/factory` is **absent** on this firmware.

### 2.3 The status document

Success carries `Content-Type: application/json` with **no `charset`**, and the body contains real
non-ASCII UTF-8 (a room name such as `"Päämakuuhuone 1"`). Error paths serve `text/html` with a
plain-text body. **The client therefore reads bytes and decodes UTF-8 explicitly, never
`response.json()`** (§3.2).

Top level:

| Field | Observed | Notes |
|---|---|---|
| `id` | `"FU2yTQsAVW8cYBgrehc2z4"` | 22 chars, **mixed case**. The vendor document says 23 lowercase and is wrong in both directions. Never lowercased, never length-validated. |
| `name` | free text, non-ASCII | The MyHeatit app's device name. Not writable over this API. |
| `room` | `""` unassigned, else free text (`"Bedroom"`) | The *assigned room*. Not writable over this API. |
| `model` | `"Heatit WiFi Panel Heater"` | **Undocumented** and present only because we looked. Used for `DeviceInfo.model`; **never** as a fingerprint (§4.2). |
| `firmware` | `"1.21"` | Independent of the document's own version numbering. |
| `state` | `"Idle"` / `"Heating"` | The *relay state*. No `Off` value exists. |
| `currentPower` | integer W | Instantaneous draw (590–601 W heating, 0 idle), **not** a duty-cycle average. Trails the relay by ~15 s. |
| `totalConsumption` | float, **two decimals on the wire** (`0.00`) | The *energy counter*. Published in ~0.04 kWh steps, not continuously. |
| `roomTemperature` | float °C | Sub-zero readings are in contract. |
| `parameters` | object | §2.4. |
| `Network` | object | `SSID`, `mac`, `ipAddress`, `wifiSignalStrength`, `status`. |

`Network` details: `mac` is **UPPERCASE** with colons (`E4:B3:23:6A:D9:08`) — normalise through
`dr.format_mac` before it reaches `connections`. `wifiSignalStrength` is a **signed** string
(`"-65dBm"`); no sign fix-up is needed or wanted. `status` reads `"ok"` on a connected panel; no
other value is reachable without dropping WiFi. The OUI `E4:B3:23` is **Espressif**, not Heatit.

**No status field has ever been `null`**, and the key set never changed across a 24-sample sweep. The
integration therefore models no third state: `null` is treated exactly as absent (§6.3).

### 2.4 The parameters

**Thirteen** *observed parameters*. The vendor document lists fifteen; `externalSensorFallback` and
`lowTemperatureProtection` have never been returned by any panel and are therefore *unobserved* —
**not modelled, not exposed, not tested**. They are neither absent nor unsupported: simply never
seen. Whether they ever appear is register rows Q48 and Q49, and a positive answer arrives as a
captured fixture, not as a checkbox.

| Wire name | Type | Range / values | Read path under `parameters` | Serialisation on the wire |
|---|---|---|---|---|
| `panelMode` | int | 0 Off, 1 Heating, 2 Eco | `panelMode` | bare integer |
| `heatingSetpoint` | float °C | 5.0–40.0, **step 0.5** | `heatingSetpoint` | quantise 0.5, then `f"{v:.1f}"` |
| `ecoSetpoint` | float °C | 5.0–40.0, **step 0.5** | `ecoSetpoint` | quantise 0.5, then `f"{v:.1f}"` |
| `minimumTemperatureLimit` | float °C | 5.0–40.0, **step 0.5** | `minimumTemperatureLimit` | quantise 0.5, then `f"{v:.1f}"` |
| `maximumTemperatureLimit` | float °C | 5.0–40.0, **step 0.5** | `maximumTemperatureLimit` | quantise 0.5, then `f"{v:.1f}"` |
| `sensorCalibration` | float °C | −6.0–6.0, **step 0.1** | `sensorCalibration` | quantise 0.1, then `f"{v:.1f}"` |
| `loadLimit` | int ×100 W | 1–15, capped by `maxLoad` | `loadLimit` | bare integer |
| `activeDisplayBrightness` | int ×10 % | 1–10 | `activeDisplayBrightness` | bare integer |
| `standbyDisplayBrightness` | int ×10 % | 0–10 | `standbyDisplayBrightness` | bare integer |
| `disableButtons` | int | 0 enabled, 1 disabled, 2 lock menu | `disableButtons` | bare integer |
| `temperatureDisplay` | bool | false = setpoint, true = measured (**in standby only**) | `temperatureDisplay` | lowercase `true`/`false` |
| `sensorMode` | bool | false = internal, true = external wireless | `sensorMode` | lowercase `true`/`false` |
| `openWindowDetection` | bool | — | **`OWD.openWindowDetection`** | lowercase `true`/`false` |

Read-only members of `parameters`: `maxLoad` (the *rated load*, ×100 W), `OWD.activeNow` (bool),
`OWD.activeTime` (int seconds, **`0` while `activeNow` is false**).

**One read/write asymmetry to hard-code:** `openWindowDetection` is *written* flat
(`?openWindowDetection=true`) and *read* nested at `parameters.OWD.openWindowDetection`.

### 2.5 Write semantics

**Query string, flatly.** Both a query string and a JSON body apply correctly at firmware 1.21;
the query string is what the vendor document specifies and what we ship. There is **no transport
hedge** — no setup probe, no options override, no per-write fallback. That a JSON body also worked is
recorded in the register as a documented lever should a future firmware break the query path; it is
a note, not a code path.

**One parameter per request.** Batching is structurally inexpressible: the client's write method
takes a single parameter. Atomicity is unprobed (register Q4) and a multi-parameter partial failure
would leave indeterminate state. This also makes a firmware defect unreachable — a parameter-less
`POST` gets **no response at all** (the firmware closes the connection; the documented `422` does not
exist), and a single-parameter API can never emit that request.

**Verdict = HTTP 200 *and* `status` matched case-insensitively** after stripping whitespace and
trailing punctuation. This is mandatory, not defensive: the device ships `"Success"` **capitalised**
and `"failed"` **lowercase**, contradicting the document (`enum: [success]`) and itself. **One
envelope for the whole API**, resets included — there is no `reset` key.

**Never branch on `reason`.** Five punctuation conventions have been observed on one device
(`is invalid!`, `is not in range 0~10`, `must be step values of 0.5`,
`outrange of temperature limit(min or max)`,
`minimumTemperatureLimit is greater than current max temperature limit or equal to it`). It is
freeform and the vendor's to change. **Surface it verbatim to the user; never match it.**

**The *write echo* reports what was applied, not what was requested**, using the exact parameter
names sent, and **normalises types** (`19` for `19.0`, `-1` for `-1.0`). It is the basis of the
optimistic update (§5.4). It is not universally honest: `sensorMode=true` on a panel with no external
sensor paired echoes `true` while the device keeps `false` — a *silent undo* (§6.5).

**Quantisation is real and undocumented, and the family is not internally consistent.** Temperatures
are quantised to **0.5**, not the 0.1 the document's `^\d+\.\d{1}$` pattern implies; `heatingSetpoint`
and `ecoSetpoint` **silently snap** an off-step value, while the two limits **reject** it with a 400.
`sensorCalibration` is genuinely step **0.1**. The pattern's strictness is fiction in the other
direction too: bare `39`, `39.00` and `039.0` are all accepted; only a leading `+` is rejected as the
regex predicts. A decimal on an integer parameter (`standbyDisplayBrightness=1.0`) is rejected.
**Client-side quantisation is what makes the silent snap harmless** — we never send an off-step value,
so the device never has to snap one.

**Booleans are lenient.** `true`/`True`/`TRUE`/`1` and the false equivalents all apply correctly;
`yes`/`no` are cleanly rejected. The feared silent misread — `False` parsing as truthy — **does not
occur**. Lowercase is a robustness choice, not a bug fix.

**Writing a parameter to the value it already holds returns 200**, not 422. No diff-before-write is
needed.

**A write is reflected in the status within 1.5 s** (measured 305 ms and 632 ms). An immediate
read-after-write returns **stale** data — observed directly. Writes themselves complete in
46–319 ms.

**The limits bind both banks.** They bound `heatingSetpoint` and `ecoSetpoint` identically, bounds
are inclusive, `min < max` is enforced, and **narrowing a limit past a stored setpoint clamps that
setpoint on the device** within the write→status lag. That eco also clamps is inferred by symmetry,
not observed.

**Eco regulates to `ecoSetpoint`** — the founding assumption of the climate design, now observed:
in `panelMode 2` with eco raised 1.3 °C above room temperature the relay closed within 2 s and drew
598 W. **Cross-bank writes are stored and inert**: writing `heatingSetpoint` while in Eco is accepted,
stored, and changes nothing about regulation.

**Resets.** The bare `DELETE /api/reset/kwh` zeroes the counter (verified with 0.04 kWh banked;
`0.04 → 0.0` within 5 s). `?resetKwh=Reset`, `?resetKwh=reset` and `?resetKwh=bogus` are all accepted
identically — the enum is not enforced. **Send `?resetKwh=Reset` anyway**: it costs one parameter,
matches the documented contract, and is provably ignored, so it is free insurance against a firmware
that starts enforcing it. `DELETE /api/reset/settings` returns the same uniform envelope, does **not**
reboot the panel, leaves `id` / `name` / `room` / `Network` untouched, and applies **staggered over
~5 s** — so the 1.5 s post-write refresh sees a *partial* reset and the next poll completes it. On the
600 W unit the post-reset `loadLimit` stays clamped at `maxLoad` rather than the document's default
of 15.

---

## 3. Architecture

### 3.1 Repository layout

```
custom_components/heatit_wifi_panel/
├── __init__.py            async_setup_entry / async_unload_entry / PLATFORMS
├── manifest.json
├── const.py               DOMAIN, LOGGER, VERIFIED_FIRMWARES, tuning constants
├── api.py                 the client — imports nothing from homeassistant
├── registry.py            the parameter registry (§3.3)
├── coordinator.py         HeatitWifiPanelConfigEntry alias + HeatitWifiPanelCoordinator
├── entity.py              base CoordinatorEntity + DeviceInfo
├── config_flow.py
├── diagnostics.py
├── climate.py  number.py  switch.py  select.py  sensor.py  binary_sensor.py  button.py
├── icons.json
├── quality_scale.yaml
├── translations/
│   └── en.json            fully expanded; there is NO strings.json
└── brand/
    ├── icon.png           256×256
    └── icon@2x.png        512×512
scripts/
├── probe.py               hardware conformance probe (§12)
├── check_conformance.py   CI gate over the register (§12)
├── check_quality_scale.py CI gate over quality_scale.yaml (§9)
├── capture_fixtures.py    read-only fixture capture (§8)
└── check.sh               the one shared local/CI entry point (§9)
tests/                     §8
docs/                      this spec, the register, the ADRs, the research
hacs.json  LICENSE  README.md  CHANGELOG.md  AGENTS.md  CONTEXT.md
```

**We must not ship `strings.json`.** For custom integrations it and its `[%key:...%]` placeholder
syntax are build-time features that nothing resolves at runtime; shipping either makes the config
flow show raw keys. The authored artifact is a fully-expanded `translations/en.json`.

No `services.yaml`: v1 registers no service actions.

### 3.2 The client — `api.py`

**Imports nothing from `homeassistant`.** Not for portability (there is no library and no core
submission) but for testability: the client is exercised over `aioresponses` with no `hass`, and
`scripts/capture_fixtures.py` imports it directly without booting Home Assistant.

Public surface, exactly four methods:

```python
async def get_status(self) -> PanelStatus       # the only method with a retry
async def set_parameter(self, key: str, value: object) -> object   # returns the applied value
async def reset_kwh(self) -> None
async def reset_settings(self) -> None
```

There is deliberately **no public request method taking a retry count**, so a retried reset cannot be
written by accident (§3.6).

**Session.** The client takes `session=async_get_clientsession(hass)` and never creates one. This
satisfies `inject-websession`. The concern that a pooled session would hurt a small embedded server
has no observed basis on this device: keep-alive works, idle sockets survive ≥ 65 s, and reuse is no
faster than a fresh connection. What would reverse this: a panel observed refusing or dropping a
reused connection.

**One request in flight per panel.** The client holds an `asyncio.Lock`; every request to one panel —
poll, write, reset, and the post-write refresh — waits its turn in arrival order. A single HA instance
therefore never presents a panel with more than one connection, the accept backlog cannot fill, and
write-then-refresh ordering is guaranteed rather than left to the device. The lock is per client
instance, and there is one client per config entry; the config flow's validation client is a separate
instance sharing no lock, so a validation `GET` may overlap a poll — which the device tolerates.

**Response handling.** Read bytes, `.decode("utf-8")` explicitly, then `json.loads`. Never
`response.json()`: success carries no `charset` and real non-ASCII, and error paths serve `text/html`.

**Exceptions** (device vocabulary, no HA types):

| Exception | Raised for |
|---|---|
| `HeatitConnectionError` | timeout, refused, dropped, OS-level |
| `HeatitResponseError` | unexpected HTTP status; carries `status_code` and the raw `reason` |
| `HeatitParameterRejected` (subclass, 400) | additionally carries the parameter name **we sent** — because `reason` cannot be parsed |
| `HeatitProtocolError` | a 200 whose body we could not make sense of |

The client retains the **last raw status body and headers** for diagnostics (§7.3).

### 3.3 The parameter registry — `registry.py`

A module-level table of frozen descriptors, one per *observed parameter*. Each carries:

- the **wire name** and the Python type;
- the **serialiser and step** (§2.4) — per parameter, not per type;
- **bounds or enum** for client-side validation;
- the **dotted read path** into the status;
- a **scale** where the user-facing unit differs from the wire (`loadLimit` ×100 W, the brightnesses
  ×10 %);
- a **presence flag**.

It earns its place four times over: the read/write asymmetry (`openWindowDetection`) lives once; the
per-parameter step rules have one home; client-side validation turns an out-of-range value into a
local error rather than a device `400`; and the entity surface (§5) is driven from the same table
instead of restating thirteen ranges.

**The presence flag guards a *drop*, not a spec-only parameter.** The registry holds observed
parameters only; a future firmware that stops returning one of the thirteen must not break setup, and
§8 tests that per observed parameter.

### 3.4 Config entry and coordinator

```python
# coordinator.py
type HeatitWifiPanelConfigEntry = ConfigEntry[HeatitWifiPanelCoordinator]
```

The alias name is **regex-constrained** to `^[A-Za-z][A-Za-z0-9]+ConfigEntry$` — alphanumeric only,
so an underscore fails. Ours is exactly `HeatitWifiPanelConfigEntry`.

```python
# __init__.py
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR, Platform.BUTTON, Platform.CLIMATE, Platform.NUMBER,
    Platform.SELECT, Platform.SENSOR, Platform.SWITCH,
]

async def async_setup_entry(hass, entry: HeatitWifiPanelConfigEntry) -> bool:
    client = HeatitClient(entry.data[CONF_HOST], session=async_get_clientsession(hass))
    coordinator = HeatitWifiPanelCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
```

Order matters: first refresh → assign `runtime_data` → forward platforms. **Do not clear
`runtime_data` on unload** — core removes it. `hass.data` is untouched.
`async_forward_entry_setup` (singular) and `async_setup_platforms` are removed from core; do not use
them. **No sleep of any kind in setup** (§3.6).

The coordinator subclasses `DataUpdateCoordinator[PanelStatus]`, carries a class-level
`config_entry: HeatitWifiPanelConfigEntry` annotation to narrow away the inherited `| None`, passes
`config_entry=` to `super().__init__` (ignored for custom integrations but it wires
`async_on_unload(self.async_shutdown)` and honours `pref_disable_polling`), and marks
`_async_update_data` with `@override`. `async_config_entry_first_refresh()` is called **only** from
`__init__.py`'s `async_setup_entry` — it asserts `SETUP_IN_PROGRESS` and hard-raises anywhere else.
The coordinator is built in `__init__.py`, never inside a platform's `async_setup_entry`.

`update_interval` comes from the options *poll interval* (§4.5). Option changes take effect through
the update listener → `async_reload`; `coordinator.update_interval` is never retimed in place.

### 3.5 Entities — `entity.py` and the platform modules

A base `CoordinatorEntity[HeatitWifiPanelCoordinator]` supplying `DeviceInfo` and the availability
rule (§6.3). Per platform:

- `_attr_has_entity_name = True` on every entity, no exceptions.
- **Names come from `translation_key` resolved in `translations/en.json`, never from `_attr_name`
  literals.** `_attr_name` is checked *before* `translation_key` in core's name resolution and
  `_attr_name = None` counts as set, so setting both silently ignores the key. The one entity that
  sets `_attr_name = None` is the climate entity, marking it the main feature; its
  `translation_key` then serves state and icon translations only.
- `_attr_unique_id = f"{device_id}-{description.key}"`.
- Entity descriptions are `@dataclass(frozen=True, kw_only=True)`, declared in the platform module,
  carrying `value_fn` / `set_value_fn` callables.
- `PARALLEL_UPDATES = 0` in `sensor.py` and `binary_sensor.py`; `PARALLEL_UPDATES = 1` in
  `climate.py`, `number.py`, `switch.py`, `select.py`, `button.py`. This sits *on top of* the client's
  per-panel lock: `PARALLEL_UPDATES` only serialises within a platform.

`DeviceInfo`, built once from the first status:

```python
DeviceInfo(
    identifiers={(DOMAIN, status.id)},
    connections={(dr.CONNECTION_NETWORK_MAC, status.network.mac)},   # format_mac applied by core
    manufacturer="Heatit",
    model=status.model,          # "Heatit WiFi Panel Heater", from the device
    name=status.name,
    sw_version=status.firmware,
)
```

No `configuration_url` (§2.2). `via_device` **was removed from the `DeviceInfo` TypedDict in HA
2026.8** and is a typing error; we have no hub, so nothing replaces it. `format_mac` is applied
automatically inside `connections` — call it yourself only for `unique_id` or `identifiers`, which
here use the *device id* instead. Keeping `sw_version` live across a firmware update is **not** done
in v1; a firmware change is picked up on reload (§6.3).

### 3.6 Timeouts, retries and startup

| | |
|---|---|
| `GET /api/status` | `ClientTimeout(total=5, connect=3)` per attempt, **retried once** on any `aiohttp.ClientError` or `TimeoutError`, no backoff → **poll budget 10 s** |
| `POST /api/parameters` | `ClientTimeout(total=10, connect=3)`, **one attempt, never retried** |
| `DELETE /api/reset/*` | `ClientTimeout(total=10, connect=3)`, **one attempt, never retried** |

Measured reads and writes complete in well under a third of a second, so these numbers cover WiFi
loss, not device speed.

**Lock wait is outside the budget.** Timeouts cover wire time only; queueing behind the lock adds to
the caller's wait but is never a failure by itself. Worst case is a write queued behind a fully
retried poll — 20 s, in a state where the panel is already failing polls.

**Writes are never retried.** A write is idempotent in effect, but a retry doubles the user's wait and
buys certainty about *sending*, not *applying* — the echo can lie, and the 1.5 s refresh is the
authority. A successful retry of a *poll* logs one debug line naming the panel and the first attempt's
error; a retry is a dropped packet, not a device anomaly.

**Keep-alive is left at defaults.** No `force_close`, no `Connection: close`, no custom keep-alive
timeout. With a poll interval of 30 s or more every poll opens a fresh connection anyway; reuse
occurs only between a write and its 1.5 s refresh, or between a failed attempt and its retry, and the
device holds idle sockets far longer than either gap.

**No startup stagger, ever, and no sleep in setup.** Multi-device restart failures on related Heatit
hardware were traced to swallowed exceptions and a missing `ConfigEntryNotReady`, not to the device:
at restart each panel receives exactly one connection, which the measured accept backlog cannot
choke. Our first refresh goes through `async_config_entry_first_refresh`, which raises
`ConfigEntryNotReady` and lets Home Assistant retry with its own backoff; the status read has its own
retry; and `DataUpdateCoordinator` already jitters every scheduled refresh by a random 0.05–0.5 s, so
steady-state lockstep across entries needs nothing from us. No global semaphore, no jittered first
refresh.

### 3.7 Named constants (`const.py`)

| Constant | Value | Justified by |
|---|---|---|
| `POST_WRITE_REFRESH_DELAY` | `1.5` s | write→status lag 305–632 ms (register Q31) |
| `RESET_VERIFY_DELAY` | `5` s | counter reads 0.00 within 5 s of the ack (Q45) — recorded as the upper bound it is |
| `POLL_BUDGET` | `10` s (5 s × 2 attempts) | status read completes in under 5 s, observed 30–210 ms (Q43) |
| `MIN_POLL_INTERVAL` | `30` s | three times the poll budget |
| `DEFAULT_POLL_INTERVAL` | `60` s | §4.5 |
| `VERIFIED_FIRMWARES` | `{"1.21"}` | mirrors `tests/fixtures/observed/fw-*/` and the README table; asserted by a test (§8.6) |

---

## 4. Config flow, identity and options

### 4.1 Identity — the device id, verbatim

Recorded as **[ADR-0003](../adr/0003-device-id-as-unique-id.md)**.

| | |
|---|---|
| `unique_id` | the status `id` — 22 chars, **mixed case, never lowercased** |
| Entity unique ids | `{id}-{key}` |
| `DeviceInfo.identifiers` | `{(DOMAIN, id)}` |
| `DeviceInfo.connections` | `{(CONNECTION_NETWORK_MAC, Network.mac)}` — hardware, not identity |
| *Foreign panel* | status `id` ≠ entry `unique_id` → permanent setup failure, and a failed poll (§6.2) |

The MAC is strictly the more stable identifier and was rejected deliberately, not overlooked: it
sits in `connections` so that a firmware found to churn the device id has a migration path rather than
a dead end. That the id survives a **factory reset** or a **firmware update** is untested (register
Q52) and is the one identity claim ADR-0003 rests on. It *is* known to survive a settings reset.

### 4.2 The user step — host only

No name field; the title comes from the device (§4.4).

Validation is a **`GET` through the client's own parser**: 200, decodable, and the *required core*
present (`id`, `state`, `roomTemperature`, and under `parameters`: `panelMode`, `heatingSetpoint`,
`ecoSetpoint`). Nothing else is required. This is deliberately stricter than setup (§6.2): someone
typing an address gets an immediate answer rather than a retry loop. Validation must be a `GET` —
`HEAD /api/status` returns 405.

| Outcome | Result |
|---|---|
| Timeout / refused / dropped | error `cannot_connect` |
| 200 but required core absent, or undecodable | error `invalid_response` |
| Valid, `id` already configured | abort `already_configured` |
| Valid, new | create entry |

`_abort_if_unique_id_configured()` is called **bare**, without `updates=`. Adding is adding; changing
an address is the reconfigure flow's job. Re-adding a moved panel therefore aborts rather than
silently rewriting an existing entry's connection data.

**`model` never gates setup.** It is the strongest available evidence that a host is a Heatit panel
and it is wholly undocumented — gating on it would lock out any unit whose string differs or whose
firmware drops the key, with no workaround. It is spent on `DeviceInfo.model`, where its absence costs
nothing.

### 4.3 Discovery — `registered_devices` and nothing else

```json
"dhcp": [{ "registered_devices": true }]
```

**No `zeroconf` key, no `ssdp` key.** `registered_devices: true` matches only devices already in Home
Assistant's registry via `CONNECTION_NETWORK_MAC`, which §3.5 populates — automatic IP-follow for a
configured panel, zero false positives, no claim to new-device discovery, one manifest line.

`async_step_dhcp`, given a `DhcpServiceInfo` carrying only ip / hostname / macaddress:

1. `GET /api/status` at the discovered IP.
2. `async_set_unique_id(id)`.
3. `_abort_if_unique_id_configured(updates={CONF_HOST: ip})`.
4. Any failure → **quiet abort**. Home Assistant re-fires on the next DHCP event, so a panel still
   booting after a fresh lease is picked up shortly after.

The status read is not optional: the *device id* is not in the DHCP packet, and matching on the
packet's MAC alone would repoint an entry without the id verification that foreign-panel safety rests
on.

**Why no mDNS or SSDP matcher.** Unicast mDNS to the panel's `:5353` — from an ephemeral port and
from source port 5353, for `_services._dns-sd._udp.local`, `_http._tcp.local` and `_heatit._tcp.local`
— drew no reply; unicast SSDP to `:1900` drew no reply; only tcp/80 is open. Both negatives are
**soft**: the probing host sat on a different VLAN, and link-local mDNS (224.0.0.251, TTL 1) cannot
cross a routed boundary, so the multicast half was untestable rather than silent. Independently, the
Espressif OUI kills a `macaddress: "E4B323*"` matcher outright — it would fire on every ESP32 device
on a user's LAN. The on-segment check is register row Q28 / procedure P-2; **it does not gate v1**,
and if it ever turns up an advertisement it amends this spec rather than having delayed it.

`quality_scale.yaml`: `discovery-update-info` **done** (`async_step_dhcp` in `config_flow.py`);
`discovery` **exempt**, with the finding above as the comment.

### 4.4 Naming and area — read once, then frozen

`name` becomes the entry title **and** the device name; a non-empty `room` becomes `suggested_area`.
Both are read **at creation only** and never rewritten by a poll.

Home Assistant's convention is that the user owns the entry title and device name once the entry
exists — which is why the rediscovery idiom updates `CONF_HOST` and never the title. Following an app
rename would silently destroy a rename made in Home Assistant, and there is no way to distinguish "the
user renamed this in HA" from "the user never touched it". An app rename therefore simply diverges.

### 4.5 Reconfigure — host only, and it never adopts

The mechanism is fixed by Home Assistant's documentation, not by preference: `async_step_reconfigure`
must *update the current entry and abort* and *should not create a new entry*, and there is no
documented route to adopting a different device — the `_abort_if_unique_id_mismatch` helper exists to
forbid it.

Host-only step, `await self.async_set_unique_id(id)` then
`self._abort_if_unique_id_mismatch(reason="wrong_panel")`, finished with
`async_update_reload_and_abort(self._get_reconfigure_entry(), data={CONF_HOST: host})`.

The translated `config.abort.wrong_panel` string **names both the expected and the found device id
and states that a replaced unit must be added as a new entry**. A replaced panel means
delete-and-re-add, with the history loss that implies; that is the platform's answer, and the
alternative is a button that quietly rewrites device identity.

The host is **not** an options field. A static DHCP reservation is recommended in the README.

### 4.6 Options — the poll interval, alone

| | |
|---|---|
| Field | *poll interval*, seconds |
| Default | **60 s** |
| Minimum | **30 s** |
| Applied by | update listener → `async_reload` |

60 s because every write already schedules its own 1.5 s refresh, so the interval governs only how
fast Home Assistant notices *external* changes: the physical buttons, the MyHeatit app, open window
detection firing, and the relay flipping. It halves the traffic against a wall heater whose room
temperature moves slowly, and it is unambiguously safe at HACS review, where an aggressive default is
a documented rejection reason. Anyone wanting faster feedback opts down to 30 s — which is the
justification for the option existing at all.

**Nothing else belongs in options.** Every other user preference is a CONFIG-category entity (§5), and
bronze `config-flow` reserves `ConfigEntry.options` for preferences and `ConfigEntry.data` for
connection info. So `data` = `{CONF_HOST}` and `options` = `{poll interval}`.

All 21 entities go briefly unavailable on an option change. That is a rare, deliberate action, and a
fair price for never shipping a stale-config bug; it also reuses the unload path the test suite
already exercises.

### 4.7 Multiple panels

One config entry per panel, one device, one coordinator each. **Nothing is global** — the HA session
is shared and HA-managed, concurrency is bounded per panel by the client lock, and `hass.data` is
untouched. Each entry titles from its own `name` and takes its area from its own `room`;
`has_entity_name` composes display names from the device name.

---

## 5. The entity surface

**21 entities** at firmware 1.21, of which **3 are disabled by default**. This is the table an
implementer works straight down.

### 5.1 Not entities, by decision

`panelMode` (owned by climate), `state` (climate `hvac_action`), `maxLoad` (surfaces as the load
limit's maximum), `Network.SSID` / `ipAddress` / `status`, `name`, `room`, `id`, `firmware`, `model`.
The diagnostic edge stops at signal strength.

### 5.2 The table

Names come from `translations/en.json` at `entity.<platform>.<translation_key>.name`; icons from
`icons.json`, keyed the same way, and only where a device class does not supply one. "Key" is both
the `translation_key` and the `{id}-{key}` unique-id suffix. "On" = `entity_registry_enabled_default`.

| Platform | Key | Name | Read path | Device class · unit · state class | Category | On | Bounds / options / notes |
|---|---|---|---|---|---|---|---|
| climate | `panel` | *(`_attr_name = None`)* | §5.3 | — | — | yes | §5.3. `translation_key` serves icon/state translation only |
| number | `comfort_setpoint` | Comfort setpoint | `parameters.heatingSetpoint` | temperature · °C | CONFIG | yes | step 0.5; min/max = the device limits, **dynamic** |
| number | `eco_setpoint` | Eco setpoint | `parameters.ecoSetpoint` | temperature · °C | CONFIG | yes | as above |
| number | `minimum_temperature_limit` | Minimum temperature limit | `parameters.minimumTemperatureLimit` | temperature · °C | CONFIG | yes | 5.0 .. (current max − 0.5), step 0.5, **dynamic** — so HA never offers a value the device rejects for min ≥ max |
| number | `maximum_temperature_limit` | Maximum temperature limit | `parameters.maximumTemperatureLimit` | temperature · °C | CONFIG | yes | (current min + 0.5) .. 40.0, step 0.5, **dynamic** |
| number | `sensor_calibration` | Sensor calibration | `parameters.sensorCalibration` | **none** · °C | CONFIG | yes | −6.0 .. 6.0, step 0.1. **No device class on purpose**: it is an offset, and °F conversion of an offset is wrong. Icon `mdi:thermometer-plus` |
| number | `load_limit` | Load limit | `parameters.loadLimit` | power · W | CONFIG | yes | 100 .. `maxLoad × 100`, step 100, **dynamic max**. Registry reads ×100, writes ÷100, bare integer on the wire |
| number | `active_display_brightness` | Active display brightness | `parameters.activeDisplayBrightness` | none · % | CONFIG | yes | 10 .. 100, step 10. Registry ×10 / ÷10. Icon `mdi:brightness-6` |
| number | `standby_display_brightness` | Standby display brightness | `parameters.standbyDisplayBrightness` | none · % | CONFIG | yes | 0 .. 100, step 10. Registry ×10 / ÷10. Icon `mdi:brightness-4` |
| switch | `open_window_detection` | Open window detection | `parameters.OWD.openWindowDetection` | — | CONFIG | yes | Written **flat** as `openWindowDetection` |
| switch | `external_sensor` | External sensor | `parameters.sensorMode` | — | CONFIG | yes | Safe to expose: the write is **inert without a paired sensor**. The echo lies here, so the switch flips on and back off at the 1.5 s refresh — accepted, §5.4 |
| select | `standby_display` | Standby display | `parameters.temperatureDisplay` | options `setpoint`, `measured_temperature` | CONFIG | yes | `false` ↔ `setpoint`, `true` ↔ `measured_temperature`. A select, not a switch: both states are meaningful |
| select | `buttons` | Buttons | `parameters.disableButtons` | options `enabled`, `disabled`, `menu_locked` | CONFIG | yes | 0 / 1 / 2. **Named as the device and the app name it**, not inverted into a "lock" |
| sensor | `temperature` | Temperature | `roomTemperature` | temperature · °C · measurement | — | yes | The one mirror of climate state, per the floor-thermostat precedent |
| sensor | `power` | Power | `currentPower` | power · W · measurement | — | yes | Instantaneous draw, not a duty-cycle average |
| sensor | `energy` | Energy | `totalConsumption` | energy · kWh · **total_increasing** | — | yes | §5.5 |
| sensor | `signal_strength` | Signal strength | `Network.wifiSignalStrength` | signal_strength · dBm · measurement | DIAGNOSTIC | **no** | Parse `^\s*(-?\d+)\s*dBm\s*$` case-insensitively; **no sign fix-up** — the device emits a signed value. Parse failure → `None` plus one debug line, **never** an exception |
| sensor | `open_window_time_remaining` | Open window time remaining | `parameters.OWD.activeTime` | duration · s · **no state class** | DIAGNOSTIC | yes | `0` when inactive (observed). Whether it counts down is register Q47 |
| binary_sensor | `open_window_detected` | Open window detected | `parameters.OWD.activeNow` | **no device class** | — | yes | On/Off, not Open/Closed: it is an inference, not a contact. Icons `mdi:window-open-variant` (on) / `mdi:window-closed-variant` (off) |
| button | `reset_energy` | Reset energy counter | `DELETE /api/reset/kwh?resetKwh=Reset` | — | CONFIG | **no** | §5.5. Never retried. Icon `mdi:counter` |
| button | `restore_defaults` | Restore default settings | `DELETE /api/reset/settings` | — | CONFIG | **no** | Keeps network and pairing; applies **staggered over ~5 s**, so the 1.5 s refresh sees a partial reset and the next poll completes it. Icon `mdi:restore` |

Counts: 1 climate, 8 numbers, 2 switches, 2 selects, 5 sensors, 1 binary sensor, 2 buttons.

### 5.3 The climate entity

```
hvac_modes         = [HVACMode.OFF, HVACMode.HEAT]     fixed, never computed from state
preset_modes       = [PRESET_COMFORT, PRESET_ECO]      panelMode 1 → comfort, 2 → eco
preset_mode        = None while Off
current_temperature = roomTemperature
target_temperature = the live setpoint (comfort in Heating, eco in Eco); None while Off
target_temperature_step = 0.5      precision left at the Celsius default (tenths)
temperature_unit   = UnitOfTemperature.CELSIUS
supported_features = TARGET_TEMPERATURE | PRESET_MODE | TURN_ON | TURN_OFF
```

**Why the preset and not a temperature range.** Eco cannot be a third `HVACMode`: the enum is closed,
core coerces `set_hvac_mode` to it, and the entity's `state` property raises on a non-member. The
preset is therefore the *only* way Eco appears inside the climate dialog or on the thermostat card.
`TARGET_TEMPERATURE_RANGE` — which would expose both banks at once and keep history honest — was
weighed seriously and rejected: under it a plain `climate.set_temperature` with `temperature:` **fails**,
which breaks the most common heater automation, and it forces eco ≤ comfort, which the panel does not.
The two config `number` entities give that shape's honest per-bank history back without the cost.
Recorded as **[ADR-0004](../adr/0004-eco-as-a-climate-preset.md)**.

**`hvac_modes` is fixed and never computed from live state**, so the capability list cannot flap.

**`TURN_ON` / `TURN_OFF` are mandatory and explicit.** The 2024.2 compatibility shim that inferred
them from `HVACMode.OFF in hvac_modes` was **deleted in 2025.1**; there is now no warning and no
auto-add, and area-targeted service calls **silently skip** an entity that does not declare them.
Core's default `async_turn_on` / `async_turn_off` route correctly for a two-mode entity, so no turn
methods are written.

| HA call | Panel write |
|---|---|
| `set_hvac_mode(OFF)` / `turn_off` | `panelMode=0` |
| `set_hvac_mode(HEAT)` / `turn_on` from Off | **`panelMode=1`, always.** Turning on means comfort; the panel has no "on" verb and remembers nothing, so HA invents no memory either |
| `set_hvac_mode(HEAT)` while already Heating **or Eco** | **no-op.** Never flips Eco to comfort |
| `set_preset_mode(comfort)` / `(eco)` in any mode, **including Off** | `panelMode=1` / `=2`. A preset is an explicit choice of on-mode, so selecting one while Off turns the panel on in it |
| `set_preset_mode` | **sends the mode only**, never a temperature |

**Setpoint writes.**

- `set_temperature` writes the **live bank**, and the live bank is **re-read from device state inside
  the call**, never from a cached preset — a device-side mode change racing the call must not write
  the wrong bank.
- With `hvac_mode` in the call: switch mode **first**, then write the bank *that mode* uses. Core
  passes `hvac_mode` through unvalidated and unapplied; handling it is ours.
- **While Off**: `target_temperature` is `None` and a plain `set_temperature` raises
  `ServiceValidationError` (`set_temperature_while_off`), telling the user to turn on or pass
  `hvac_mode`. This follows the Heatit floor thermostats, whose dial is blank while Off, with one
  deliberate deviation: they drop the write *silently*, and we refuse *loudly* so an automation
  learns it did nothing.
- The signature is `async_set_temperature(self, **kwargs)` — core leaks `entity_id` into kwargs.
- The `number` entities write their named bank **unconditionally, in any mode**. Verified safe: a
  comfort write made in Eco is stored and does not change regulation.

**Limits.** `min_temp` / `max_temp` come from the device's limits, reported truthfully, **no
client-side clamping**. The device bounds both banks itself, enforces min < max, and clamps a stored
setpoint when a limit narrows past it — so the out-of-bounds-display hazard does not arise; a limit
change is followed by a refresh and the card is consistent again.

**`hvac_action` comes from the relay, with one synthesis.** `state` leads `currentPower` by ~15 s, so
the action is derived from `state` and **never** from power.

| `state` | *Panel mode* | `hvac_action` |
|---|---|---|
| `Heating` | any | `HEATING` — the element is on, and that stays true if a future firmware's frost protection heats while Off |
| `Idle` | Off | `OFF` — synthesised; the device has no Off value |
| `Idle` | Heating / Eco | `IDLE` |

This is the one place we deliberately differ from the floor thermostats, which report `idle` for an
Off thermostat; we follow core's convention and report `off`.

### 5.4 Rules that apply across the table

- **Units are real units.** Load limit in W, brightness in %. The registry descriptor carries the
  scale; the wire sees the device's integers. Nothing dimensionless is exposed.
- **Bounds are dynamic wherever they come from device state** — the setpoints' bounds are the limits,
  each limit's inner bound is the other limit ± 0.5, the load limit's max is `maxLoad × 100`. All
  read from coordinator data, never cached at setup.
- **Presence-gated creation.** A descriptor becomes an entity only if its read path resolves in the
  **first** status at setup. A parameter appearing later is picked up on **reload**, not live; a
  parameter that vanishes at runtime makes its entity **unavailable** (§6.3).
- **Mirrors of climate state: only the temperature sensor.** No heating binary sensor (power and
  `hvac_action` already say it), no setpoint sensors (the config numbers record history; long-term
  statistics for setpoints were judged not worth two entities). Anything not in the table is
  **omitted**, not created disabled.
- **Optimistic updates are uniform:** apply the **echoed** value immediately, coerced back to the
  registry's declared type, then a debounced refresh at **1.5 s** as the authority. If the echo is
  missing or unparseable, fall back to the requested value; the refresh corrects either way. This
  stays one rule even though the echo lies for `sensorMode` — a per-parameter honesty flag was
  weighed and rejected in favour of keeping the contract at one rule; the *silent undo* warning
  (§6.5) is what surfaces the exception.
- **Disabled by default means one of two things**, and nothing else: a **noisy diagnostic** (signal
  strength) or a **button whose press discards device state** (energy reset, settings reset). Any
  future reset-shaped button inherits opt-in without a new decision. It is not a general "dangerous"
  marker.
- **Two concepts, two names.** For open window detection: the *setting* is "Open window detection"
  (switch), the *detection* is "Open window detected" (binary sensor), the *countdown* is "Open
  window time remaining" (sensor). The same discipline applies to *low temperature protection* if it
  is ever observed — its wire name means both a threshold and a live state, and they must never share
  a name in prose or in the UI.

### 5.5 Energy and its reset

**The energy sensor stays `total_increasing`.**

- `state_class: total` with `last_reset` is **rejected**: the counter can be zeroed from the MyHeatit
  app, and possibly by a power cycle, and Home Assistant can never learn when those happened. Only
  our own button presses are known, so a `last_reset` attribute would be wrong the first time anyone
  else resets it.
- HA's **10 % dip tolerance** (a decrease smaller than 10 % is read as noise, not a reset) is safe
  here **because the device resets to exactly `0.0`**. A partial reset would be misread; this panel
  does not do one. That precondition is register row Q21.
- **One publication step, ~0.04 kWh, is lost per reset.** The counter publishes in lumps (274 s flat
  at ~591 W before the first step) while a reset writes through within 5 s, so energy banked since the
  last published step never reaches HA's statistics. Bounded by one step, unfixable from our side,
  **documented rather than worked around**.
- Long-run statistics otherwise survive a reset intact: the drop starts a new meter cycle with zero
  point 0 and the running `sum` continues from the pre-reset total.

**The reset button stays, and is opt-in.** An action mirroring `zwave_js.reset_meter` was rejected —
that shape is dictated by Z-Wave's generic meter command class, not by preference, and it would put
`services.yaml`, `action-setup` and `docs-actions` back on the plate for nothing. Dropping the reset
entirely was rejected because the app and the panel's own display show the counter, and parity with
them is the legitimate reason to press it. A confirmation dialog is not available to a button entity,
so **disabled by default is the only guard Home Assistant offers**, and a mis-tap is bounded: at most
one unpublished step lost in HA, the panel's own counter zeroed.

**Verification: warn once, at a later poll.** A parameter write has an echo to compare against; a
reset has none, so the only check is *did the counter drop below its pre-reset value*.

1. On press, record the **pre-reset value** (the last coordinator reading) and the **ack time**.
2. The **first poll completing `RESET_VERIFY_DELAY` (5 s) or later after the ack** judges it. Any
   refresh completing earlier — scheduled or write-triggered — is ignored for judging.
3. If the pre-reset value was **non-zero** and the judged reading is **not below it**, log a
   **warning once per entry lifetime** naming the pre-reset and current values; later occurrences are
   debug until reload.
4. If the pre-reset value was zero, clear the pending record and log nothing.
5. A second press before judgement replaces the pending record.
6. **No retry, no availability effect.** The button's call has already returned; the warning is the
   only consequence.

Pressing at `0.0` still sends the request — the last reading may be a poll interval stale and the
request is harmless; only the verification is skipped. Accumulation within 30 s cannot reach a new
publication step, so "not below" is a reliable test at the poll-interval floor.

**Counter drops Home Assistant did not cause are never logged.** A reset from the app is a legitimate
act, the statistics engine already treats the drop as a new cycle, and it is not the device
misbehaving.

---

## 6. Failure and availability

**The governing idea: the poll is the sole judge of availability.** Setup, writes and resets never
decide whether the device is there; they raise to whoever called them and let the next status read
settle it.

### 6.1 Poll-time failure

A failed `_async_update_data` raises `UpdateFailed`; **every entity goes unavailable on the first
failed poll.** No coordinator-level grace, no hand-rolled failure counter, no stale data served as
fresh. The tolerance for a single dropped packet lives **one layer down** — the status `GET` is
retried once inside the poll budget (§3.6), so a poll fails only when the device was unreachable for
the whole budget.

Recovery is the next good poll. The coordinator logs the two transitions itself — one `error` line on
failure, one `info` on recovery, nothing in between — and **we add no lines of our own** to that path.
A panel that is off all night costs two log lines.

### 6.2 Setup-time failure — everything retries except a foreign panel

`async_setup_entry` runs `async_config_entry_first_refresh()`; its failure becomes
`ConfigEntryNotReady`, retried at 5 s, 10 s, 20 s … capped at 10 min, forever, with the exception's
translation key propagated.

| Condition | Result | Why |
|---|---|---|
| Host unreachable (timeout, refused, dropped) | `ConfigEntryNotReady` | A DHCP renew or a reboot; the panel may return at this address by itself |
| Host answers but is not a panel (404, `text/html`, unparseable) | `ConfigEntryNotReady` | A captive page or a mid-reboot stack looks identical, and a permanent error would strand a panel that comes back |
| Status parses but lacks a *required core* field | `ConfigEntryNotReady` | Treated as drift or a transient; retrying is free |
| Status carries an `id` different from the entry's unique id | **`ConfigEntryError`**, naming both ids | A *foreign panel* owns this address. Retrying can never fix it; the fix is the reconfigure step (§4.5) |

**The id check runs on every poll, not only at setup.** A status whose `id` is not the entry's is
`UpdateFailed` (key `foreign_panel`, placeholders `expected_id` / `actual_id`), never data — the
alternative is writing one bedroom's setpoints into another room's entities. A `ConfigEntryError`
raised from a scheduled refresh is caught and logged by the coordinator, never escalated, so at poll
time the user sees the device unavailable and one error line; a reload turns it into the permanent
setup error.

### 6.3 Malformed or partial status

- **Required core**: `id`, `state`, `roomTemperature`, and under `parameters`: `panelMode`,
  `heatingSetpoint`, `ecoSetpoint`. Missing any of them, or a body that is not JSON, fails the poll
  (`UpdateFailed`, key `missing_field` with the dotted path, or `invalid_response`); everything goes
  unavailable and one log line names the field.
- **Every other observed field is optional.** Absent means that entity alone is unavailable and the
  poll succeeds. `firmware` absent is treated as unverified (§7.2), not as an error.
- **`null` is absent.** No panel has ever returned one; the parser maps `null` to the same
  missing-path outcome and the integration models no third state. Revisited only if an observed
  fixture ever contains a `null`.
- **Unknown keys are ignored**, at top level and under `parameters`.
- **Presence is decided once, at setup.** A parameter appearing later is logged at debug and picked up
  on the next reload or restart — no dynamic entity addition, no automatic reload. A parameter that
  vanishes and returns makes its entity unavailable and then available again; nothing is removed from
  the entity registry either way.

Per-entity availability is therefore `super().available and <read path resolves in coordinator.data>`.
**Nothing stays available while the coordinator is failed**, the reset buttons included — pressing one
against an absent device is a request with no meaning.

### 6.4 Write-time failure

All write errors are `HomeAssistantError`, all carrying translation keys in `translations/en.json`,
with the device's `reason` passed through **verbatim and never parsed**:

| Client exception | HA exception | Translation key | Placeholders |
|---|---|---|---|
| `HeatitParameterRejected` (400) | `HomeAssistantError` | `parameter_rejected` | `parameter` (the name **we sent**), `reason` |
| `HeatitConnectionError` | `HomeAssistantError` | `cannot_connect` | — |
| `HeatitProtocolError`, `HeatitResponseError` | `HomeAssistantError` | `unexpected_response` | `status` |
| *(local)* plain `set_temperature` while Off | `ServiceValidationError` | `set_temperature_while_off` | — |

A 400 is **not** a user error: HA's number and climate layers validate ranges before we are called and
the registry quantises and bounds locally, so a rejection that still reaches the device means our
bounds and the device's disagree — drift, surfaced as an error, in the device's own words.
`ServiceValidationError` stays reserved for the one local case above.

**After any write, success or failure, the same debounced 1.5 s refresh is scheduled.** The device
commits within 300–600 ms, so a timeout on the *response* does not mean the value did not stick; the
refresh converges HA to whatever the device did. **The write path never touches availability** — a
failed write raises to the caller and the next poll decides whether the device is gone.

### 6.5 Silent undo

When the post-write refresh disagrees with the echoed value, the coordinator logs a **warning once
per parameter per entry lifetime**, naming the parameter, the echoed value and the refreshed value;
later occurrences for the same parameter are debug until reload.

Client-side quantisation has already removed the snap case, so every mismatch that remains is a
genuine device refusal disguised as success. The one known instance is `sensorMode=true` with no
external sensor paired.

### 6.6 No repair issues in v1

`repair-issues` is exempt. The foreign panel surfaces as `ConfigEntryError` on the integrations page
at setup and as the coordinator's error line at poll time; an unverified firmware is an info line. No
repairs platform, no issue registry, no fix flow.

---

## 7. Logging, redaction and diagnostics

### 7.1 One redaction function

A single function — shared by logging, diagnostics and fixture capture — scrubs exactly **`id`,
`Network.mac`, `Network.SSID`, `Network.ipAddress`**. **`name` is kept**, and so is `room`: they are
human-readable labels, not identifiers, and `name` is the evidence that the charset-less UTF-8 decode
is required.

**Raw response bytes are never logged, at any level.** When parsing fails the line carries content
type, byte length and the exception; the documented way to obtain the bytes is
`scripts/capture_fixtures.py` or a diagnostics download, both of which scrub.

One function means the HACS security review — where leaked SSIDs, MACs and PII in debug output are
the most frequently cited rejection reason — has a single surface to read.

### 7.2 Log levels

| Level | Line | Cadence |
|---|---|---|
| `error` / `info` | device unavailable / recovered | the coordinator's own, once per transition |
| `error` | first-refresh failure | the config-entry machinery's own |
| `warning` | a parameter present at setup **vanished** from status (entity → unavailable) | once per transition; `info` when it returns |
| `warning` | **echo mismatch** after the post-write refresh (§6.5) | once per parameter per entry lifetime, then debug |
| `warning` | **energy reset not observed** (§5.5) | once per entry lifetime, then debug |
| `info` | setup met a firmware with no observed fixture — names the firmware and `VERIFIED_FIRMWARES` | once per setup |
| `debug` | per poll: request line, status code, byte length, the parsed status **after redaction** | every poll |
| `debug` | per write: parameter and value sent, status code, echoed value | every write |
| `debug` | a successful retry of a status read | per occurrence |
| `debug` | a parameter appeared after setup | once per transition |

**Nothing routine logs above debug. Nothing repeats per poll.**

### 7.3 Diagnostics

`diagnostics.py` implements **`async_get_config_entry_diagnostics` only** — one entry is one device,
so device diagnostics would duplicate it. The download contains:

- `entry_data` and `options` (host, poll interval) through the shared redaction;
- `status`: the coordinator's parsed data;
- `firmware`, and whether it is in `VERIFIED_FIRMWARES`;
- `observed_parameters` at setup and `vanished_parameters` since;
- `last_poll`: outcome, duration, whether the retry was used;
- **`raw`: the last status response body and headers as received**, through the same **wire-level**
  scrub. `async_redact_data` redacts dict keys, not text, so the raw section goes through our scrub,
  not HA's helper.

A download from a user on an unverified firmware is therefore a **fixture candidate** that preserves
fields the parser does not model — which is the point of shipping the raw section at all.

---

## 8. Testing

**One panel at one firmware is not the fleet.** The answer to that is not a bigger suite; it is a
**provenance discipline** — every fixture says where it came from, and nothing in the registry, the
entity table or the tests exists because a document said so.

### 8.1 Two tiers, and no third

| Tier | Runs | Talks to hardware | Writes |
|---|---|---|---|
| **Offline suite** — `pytest` | CI, every PR | never | never |
| **Conformance probe** — `scripts/probe.py` (§12) | by hand, dev present | yes | opt-in, approved, self-reverting |

There is **no third tier** — no opt-in live pytest marker, no env-var-gated hardware run. The gap one
would fill (*does the integration's own client still read this panel?*) is filled by a read-only
capture script, `scripts/capture_fixtures.py`:

- reads `.local/device.json`, imports the client **directly** (no HA boot), performs the status read
  through the real read path;
- writes the raw response bytes and headers under `tests/fixtures/observed/fw-<firmware>/`, scrubbing
  on the way (§8.3);
- prints a diff against what is committed;
- is **read-only by construction** — it has no code path that issues anything but `GET /api/status`,
  and it never runs in CI.

**The diff must separate the volatile fields**, or it is worthless. The status is computed per
request, and four fields move on their own — `wifiSignalStrength`, `roomTemperature`, `currentPower`,
`totalConsumption` — none of which is on the scrub list. The script prints them in a separate **live
values** block, reported for information and never counted as drift; a difference **outside** those
four is the drift signal. Excluding them outright was rejected: a field that stops moving is itself
worth seeing.

A **new observed directory** appears only when a real panel produced it. A second panel or a new
firmware means a new `fw-<version>/` directory, and its capture is the admission ticket for anything
it shows that 1.21 did not.

### 8.2 The spec-derived mock is rejected

Generating a device simulator from the OpenAPI document (Prism or equivalent), booting HA against it
and asserting a clean log is **not adopted**, and the reason is recorded so it is not re-litigated:

- The document it would simulate has already lost to the device on the success sentinel, the reset
  envelope, the non-existent 422, idempotent writes and the float pattern. A spec-derived double would
  serve every one of those errors as truth — so a client that matches the panel would fail against it,
  and a client that passes it would fail against the panel.
- Its one unique offer, the full HA-boot path with no hardware, is already covered by
  `pytest-homeassistant-custom-component`, which boots a real `hass` in-process against a fake client
  fed from **observed** bytes.
- It brings a Node toolchain into a Python project's CI.

### 8.3 Fixtures — observed or synthesised, never invented

```
tests/fixtures/
  observed/
    fw-1.21/
      manifest.json      captured_at, firmware, model, maxLoad, scrubbed_fields, capture-script version
      status.json        raw wire bytes, scrubbed — NOT re-serialised
      status.headers     raw response headers (a charset-less Content-Type is evidence)
  synthesised/
    manifest.json        per file: what it is, derived from which observed file, or transcribed from what
    write-echo-*.json
    error-400-*.txt
```

Observed files are the bytes the device sent, byte-for-byte outside the scrubbed fields. **They are
never round-tripped through `json.dumps`**: the wire says `"totalConsumption": 0.00` and a round-trip
would silently rewrite it.

**Scrub list — exactly five fields**, replaced by fixed, shape-preserving placeholders through
targeted substitution on the raw bytes:

| Field | Placeholder | Why this shape |
|---|---|---|
| `Network.SSID` | `"SSID-REDACTED"` | never parsed |
| `Network.mac` | `"02:00:00:00:00:01"` | locally administered, valid for `format_mac` |
| `Network.ipAddress` | `"10.0.0.2"` | valid RFC 1918 IPv4 |
| `id` | `"FIXTUREFIXTUREFIXTUREX"` | same length (22) and mixed case as a real id, so `{id}-{key}` unique ids are exercised verbatim |
| `name` | `"Näytehuone 1"` | **stays non-ASCII** — this field is the evidence the charset-less UTF-8 decode is required |

`room` is kept as captured, for the same reason as `name`. A CI test asserts every
`observed/*/status.json` holds exactly the placeholder in each of the five fields, so an unscrubbed
capture cannot merge.

**Synthesised variants are derived, not written.** Off mode, Eco engaged, open window detection
active, a dropped parameter, an unknown extra key, a malformed body, a WiFi drop — nobody is turning
on a bedroom heater to capture these. They are produced **in test code by mutating an observed
fixture** (load the reference bytes, parse, change the named fields, re-encode) and never hand-written
as standalone JSON, so every unobserved part of a synthesised fixture is real. A synthesised value may
only take a form the device has been seen to emit for that field. **No synthesised fixture may
introduce a field no observed fixture contains.**

**Write echoes are transcribed now and replaced by the probe.** The write-path responses (the 200
echo with its type normalisation, the 400 punctuation styles, the reset envelope, the `text/html`
404/405 bodies, the connection drop on a parameter-less POST) start life in `synthesised/`, their
manifest naming the source. The probe, run with writes enabled, saves each write and reset response as
raw bytes into `observed/fw-<version>/` and those replace the transcriptions.

**Reference fixture.** The suite pins one observed directory — the newest by version, named
explicitly in `conftest.py` — for state assertions. A **parse-only sweep** runs the status parser over
*every* observed directory, so a second panel's capture extends the suite with no test edits.

### 8.4 Two seams, split by layer

| Tests of | Seam | Mechanism | Fixture source |
|---|---|---|---|
| The client (`tests/client/`) | **HTTP** | the real client over `aioresponses`, no `hass` | observed bytes + synthesised write responses |
| Config flow, coordinator, entities (`tests/integration/`) | **Client** | `FakeHeatitClient` patched in | the same observed bytes, parsed by the **real** parser |

One source of truth: the fake is constructed from an observed fixture's bytes *through the client's
real parser*, so its status shape can never drift from what the client produces. It records every
write, answers a write with an echo built from the request (the device's own behaviour), and takes
scripted failures — raise on next read, return a mutated status after a write — for the coordinator
and optimistic-update tests.

### 8.5 What must be asserted

A reviewer checks this named list, not a percentage.

**Client, at the HTTP seam** — these are what a careless refactor would undo:

- The exact request for each serialisation class: `heatingSetpoint=19.0` (0.5-quantised, one decimal),
  `sensorCalibration=1.1` (0.1), `standbyDisplayBrightness=5` (bare integer, **never** `5.0`),
  `openWindowDetection=false` (lowercase); `loadLimit` scaled ÷100 and the brightnesses ÷10 on the wire.
- Client-side quantisation and bounds: an off-step or out-of-range value raises **locally** and **no
  request is emitted**.
- **No code path emits a parameter-less `POST`** — across the full write surface the mock never sees a
  `POST /api/parameters` without a query.
- Verdict = HTTP 200 **and** `status` matched case-insensitively after stripping whitespace and
  trailing punctuation: `"Success"`, `"success"`, `"Success."` pass; `"failed"` fails.
- Echo handling: the **applied** value is returned, coerced to the declared type (`19` → `19.0`,
  `-1` → `-1.0`); a missing or unparseable echo → the requested value.
- Bytes decoded as UTF-8 with **no charset** in `Content-Type`; the observed non-ASCII `name` survives.
- `400` → `HeatitParameterRejected` carrying the parameter name *we sent* and `reason` verbatim;
  `text/html` 404/405 → `HeatitResponseError` with `status_code`; timeout / refused / dropped →
  `HeatitConnectionError`; 200 with an unparseable body → `HeatitProtocolError`.
- Resets: `DELETE /api/reset/kwh?resetKwh=Reset` and `DELETE /api/reset/settings` exactly, uniform
  `status` envelope, **never retried** — one request even on failure.
- Status parsing: every registry read path resolves against the reference fixture; the parse-only
  sweep over every observed directory.
- Signal strength: `"-67dBm"` → `-67`; no sign fix-up; garbage → `None` and no exception.

**Integration, at the client seam:**

- **Config flow: every path in §4, at 100 % line coverage.**
- Setup against the reference fixture yields exactly **21 entities**. The entity table is a single
  test parametrised over a **test-side literal table** transcribed from §5.2 — unique id `{id}-{key}`,
  name, platform, device class, unit, state class, category, enabled-by-default, initial state. **By
  rule it is never derived from the integration's descriptor table**, so the test compares two
  independent encodings.
- **Dropped-parameter tolerance**, parametrised over every observed parameter: remove it from the
  reference fixture, setup succeeds, exactly that entity is absent, every other entity present. Plus:
  an unknown extra key at top level and under `parameters` is ignored.
- Climate: `hvac_modes == [OFF, HEAT]`; preset switching writes `panelMode`; `set_temperature` writes
  the **live** bank; `target_temperature is None` and `set_temperature` raises while Off;
  `hvac_action` for all three cases; turn on lands in Heating; HEAT while in Eco is a no-op; a preset
  chosen while Off turns the panel on in that mode.
- **Dynamic bounds**: number min/max follow the limits, each limit follows the other ± 0.5, the load
  limit's max follows `maxLoad × 100` — all from coordinator data, verified by changing the fake's
  status and reading the bounds again.
- **Optimistic update**: after a write the state shows the echoed value immediately; exactly **one**
  refresh is scheduled at 1.5 s (asserted by advancing `hass`'s clock, never by sleeping); the
  refreshed value wins. Includes the `sensorMode` inert case — echo `true`, refresh `false`, state
  returns to off — and the once-per-parameter warning.
- Coordinator failure handling per §6: unavailable on the first failed poll, recovery on the next good
  poll, a foreign id is `UpdateFailed`, a missing required-core field is `UpdateFailed`, an optional
  missing field is per-entity unavailability, `null` == absent, and the §7.2 table is the must-assert
  list for logging.
- Energy reset verification: a press records the pre-reset value; a poll completing before 5 s does
  not judge; a later poll showing no drop warns exactly once.
- Buttons: reset-energy emits the exact `DELETE`; both buttons are disabled by default.
- Fixture hygiene: every observed fixture carries the five placeholders.
- **Three-way firmware consistency**: the README `## Verified firmware` table's version set ==
  `tests/fixtures/observed/fw-*/` == `VERIFIED_FIRMWARES`.

### 8.6 What is not asserted

Recorded so this spec does not license coverage theatre:

1. **Home Assistant's own machinery** — that the coordinator polls on schedule, that entities
   register, that a config entry unloads. Framework behaviour, tested upstream.
2. **The `reason` text of a 400** — never parsed, never branched on; asserted only as surfaced
   verbatim.
3. **The vendor document's regexes and enums** — they are not the device's rules; a test that a value
   matches `^\d+\.\d{1}$` pins fiction.
4. **Translation strings and icon choices** — reviewed, not tested.
5. **Wall-clock timing** — the 1.5 s refresh is asserted by advancing the clock and counting
   refreshes, never by sleeping and measuring.
6. **Any firmware that did not produce a fixture** — no test asserts fleet-wide behaviour; every
   assertion is scoped to an observed directory.
7. **Log wording**, beyond the presence of one line when a device goes unavailable and one when it
   recovers.

### 8.7 Gate, framework and CI matrix

**Hybrid gate.** Two things block a merge: `config_flow.py` at **100 % line coverage**
(`coverage report --fail-under=100 --include='*/config_flow.py'`) — a small module where a missed path
is a user-facing bug — and the named list in §8.5, checked by the reviewer. Overall coverage is
**measured and reported**, not gated; core's silver 95 % is not inherited.

**Framework.** `pytest` + `pytest-homeassistant-custom-component` (which provides `hass`,
`enable_custom_integrations`, `aioclient_mock`) + `aioresponses` for the client tests + `pytest-cov`.
`syrupy` is present through the harness but **unused**: explicit assertions everywhere, no snapshots.
Layout: `tests/conftest.py`, `tests/fakes.py`, `tests/client/` (no `hass`), `tests/integration/`,
`tests/fixtures/`.

**Matrix — two rows.** `pytest-homeassistant-custom-component` releases in lockstep with HA core, one
package version per HA release, each pinning that HA exactly, so a row is one HA release plus its
Python.

| Row | Install | Python | Blocks merge | Also runs |
|---|---|---|---|---|
| **floor** | `requirements_test.txt`, `pytest-homeassistant-custom-component==0.13.317` (HA 2026.3.1) | 3.14 | **yes** | — |
| **latest** | `pytest-homeassistant-custom-component` **unpinned** | 3.14 | no (`continue-on-error`) | **monthly cron** |

The floor row is what a developer installs locally. The latest row is the early warning for a monthly
HA release deprecating something we use; red there is a signal, not a blocker.

---

## 9. Quality and tooling

The quality scale is a **borrowed checklist, enforced by us**. `hassfest` returns early on
`if not integration.core` and never parses `quality_scale.yaml` for a custom integration, and no
reviewer will either — so the adopted set is checked by our own CI or by nobody.

### 9.1 Which rules

**Every bronze, silver, gold and platinum rule that is about the code is adopted**, unless listed
below as `exempt` with a one-line reason. The burden of proof sits on leaving a rule out.

| Exempt | Reason (verbatim into the yaml) |
|---|---|
| the 15 `docs-*` rules | require a `home-assistant.io` page; HACS-only integration, the README carries the facts |
| `strict-typing`, `dependency-transparency`, `async-dependency` | assume a published PyPI requirement; the client is a module inside the integration. Typing itself is enforced by mypy strict below, not by this rule |
| `repair-issues` | no repairs platform in v1 |
| `reauthentication-flow` | the local API has no authentication |
| `action-setup` | no custom service actions in v1 |
| `dynamic-devices`, `stale-devices` | one config entry is one fixed device |
| `discovery` | the panel advertises no mDNS or SSDP response to unicast probing; link-local multicast was untestable across the VLAN boundary; the Espressif OUI makes a MAC-prefix matcher unusable (§4.3) |

`test-coverage` (silver, > 95 %) is adopted **as reported, not gated**, and the yaml comment says so.
`discovery-update-info` is **done**. Everything else is `done`, or `todo` until the release that ships
it.

Consequences the rules impose on the implementer, gathered in one place:

- `entity-translations` + `has-entity-name`: names from `translation_key` in `translations/en.json`,
  never `_attr_name` literals. §5.2's Name column is the English string that lands in `en.json`.
- `icon-translations`: `icons.json` keyed by the same translation keys.
- `common-modules`: coordinator in `coordinator.py`, base entity in `entity.py`.
- `runtime-data`: the `HeatitWifiPanelConfigEntry` alias.
- `integration-owner`: `codeowners: ["@Normio"]`.
- `parallel-updates`, `config-entry-unloading`, `unique-config-entry`, `test-before-configure`,
  `test-before-setup`, `entity-event-setup`, `entity-unique-id`, `entity-unavailable`,
  `log-when-unavailable`, `exception-translations`, `inject-websession`, `devices`, `diagnostics`,
  `reconfiguration-flow`, `entity-category`, `entity-device-class`,
  `entity-disabled-by-default`, `appropriate-polling`: all adopted, all evidenced by §9.2's tests or
  by a named module.

### 9.2 What enforces it

`custom_components/heatit_wifi_panel/quality_scale.yaml` is written in hassfest's own schema — all 54
hyphen-slugged keys, values `done` / `todo` / `exempt` — and checked by
**`scripts/check_quality_scale.py`**, run from `test.yml` so it also gates releases. It fails when:

1. any of the 54 rule keys is missing, or an unknown key is present (the rule list is vendored in the
   script with the core commit it came from; when core adds a rule, the script is updated and the yaml
   gains a `todo`);
2. a `done` or `exempt` entry has no comment;
3. a **`done` comment does not start with a repo-relative path that exists** — a test file, a module,
   or a directory that is the evidence. Free text may follow the path. Deleting the test that proved a
   rule breaks the build until the yaml is updated;
4. `manifest.json` carries a `quality_scale` key — **the key is deliberately omitted**: the yaml says
   what we hold ourselves to, and the manifest makes no claim a reviewer never graded;
5. **any rule is `todo` and the version under check is `v1.0.0` or later.** On PRs and 0.x tags the
   script reports the `todo` count and passes.

The escape hatch is the format itself: `exempt` with a comment.

**Rule tests** — the mechanically checkable rules get a real test, and the yaml's `done` path points
at it:

| Rule | The test asserts |
|---|---|
| `entity-unique-id` | every entity has a unique id of the form `{id}-{key}`, stable across a reload |
| `has-entity-name` | `_attr_has_entity_name` is true on every entity |
| `entity-translations`, `icon-translations` | every `translation_key` resolves in `translations/en.json` and `icons.json`; no `_attr_name` literal |
| `parallel-updates` | every platform module declares `PARALLEL_UPDATES`: `0` on `sensor` and `binary_sensor`, `1` on the five write platforms |
| `config-entry-unloading` | unload returns true and the client/session hold nothing afterwards |
| `unique-config-entry` | a second entry for the same status `id` aborts |
| `diagnostics` | no unscrubbed `id`, MAC, SSID or IP in **either** the parsed or the raw section, and the raw section byte-equals the scrubbed fixture |
| `common-modules` | the `done` path is the module itself; existence is the check |

### 9.3 Linters

- **ruff**: `select = ["ALL"]` with a **named ignore list** in `pyproject.toml`, one reason per entry;
  `ruff format --check` alongside. Per-file ignores only under `tests/`. `RUF100` (unused `noqa`) and
  `PGH004` (bare `noqa`) on, so a stale or code-less suppression fails. Runs **once**, in its own
  `test.yml` job — it needs no Home Assistant.
- **mypy**: `strict = true` over `custom_components/` and `scripts/`, run **inside each pytest row**
  against that row's Home Assistant. The **floor row blocks**; the latest row is a signal, not a
  blocker. `warn_unused_ignores` is part of strict, so a dead `# type: ignore[code]` fails; a bare
  `# type: ignore` is rejected by ruff `PGH003`.
- Both **block a merge**, and both are **pinned exactly** in the floor row's `requirements_test.txt` —
  a gate must not go red on its own.
- Suppressions are always **specific-code**: `# noqa: CODE`, `# type: ignore[code]`.

`scripts/probe.py`, `scripts/check_conformance.py` and `scripts/capture_fixtures.py` are under the
same ruff and mypy rules as everything else in `scripts/`.

### 9.4 One shared entry point

`scripts/check.sh` holds the exact commands — ruff, ruff format, mypy, both pytest invocations,
`check_quality_scale.py`, `check_conformance.py` — and **`test.yml` calls it** rather than listing
commands, so local and CI cannot drift. **No git hooks, no pre-commit framework**: a fresh worktree
without hooks installed is exactly the drift we are designing against. `AGENTS.md` names the entry
point as the step before a push.

---

## 10. Packaging

### 10.1 Fixed values

`hacs.json`, and **nothing else** (the schema rejects unknown keys):

```json
{
  "name": "Heatit WiFi Panel",
  "homeassistant": "2026.3.1",
  "hide_default_branch": true
}
```

`hide_default_branch: true` is present **from the first commit of the file**. `zip_release`,
`content_in_root`, `country`, `persistent_directory` and `render_readme` are all unset.

`manifest.json` — keys sorted `domain`, `name`, then alphabetical:

```json
{
  "domain": "heatit_wifi_panel",
  "name": "Heatit WiFi Panel",
  "codeowners": ["@Normio"],
  "config_flow": true,
  "dhcp": [{ "registered_devices": true }],
  "documentation": "https://github.com/Normio/HeatIt-Wifi-Home-Assistant",
  "import_executor": true,
  "integration_type": "device",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

No `quality_scale` key (§9.2). No `single_config_entry` — several panels per instance is supported.
`version` is `vol.Optional` in the schema but the **loader refuses to load the integration without
it**, and it must parse as SemVer here.

> **Assembly note.** `import_executor: true` was recommended by the conventions research (the loader
> warns on every start without it) and was never explicitly ruled on. It is included here on that
> basis; striking it costs one line and one warning.

**The floor is `2026.3.1`, and it is honest.** The only 2026-era mechanism we use is the in-tree
`brand/` icon, which renders on ≥ 2026.3; nothing on this map uses a newer API (the 2026.8
device-registry rewrite is not used, and `runtime_data`, the typed alias, the explicit
`TURN_ON`/`TURN_OFF` flags and `translations/en.json` all predate it). The **patch** number is there
because the floor CI row pins exactly, and no `pytest-homeassistant-custom-component` release pins
2026.3.0 — declaring `2026.3.1` makes the declaration and the enforced row coincide byte for byte
rather than leaving a one-patch gap nothing tests. Reach at the time of the decision: 82.4 % of
reporting installs. A 2026.8 floor would have halved that to 57.8 % for nothing.

**The floor moves only when a PR needs a newer HA API** — never for age, never on a schedule, never
frozen for a line. The pin moves in the same PR, the bump is a `CHANGELOG.md` entry, and it is at
least a minor version. **The floor CI row is the enforcement**: code using an API newer than the floor
goes red there. That is the same check the HACS reviewer performs by reading source, kept running
after submission when no reviewer is watching.

**Brand assets.** `custom_components/heatit_wifi_panel/brand/icon.png` (256×256) and `icon@2x.png`
(512×512), copied from `home-assistant/brands` `core_brands/heatit/` — identifying use of the vendor
mark, the same precedent the core Z-Wave brand relies on. **No `logo*`** (the icon is the logo
fallback and a byte-identical logo is rejected by the brands validator), no `dark_*`, and **nowhere
else in the repository** — a root `brand/` or a stray `icon.png` is a documented review comment.

**Licence.** Root `LICENSE`, MIT, already detected by GitHub as `spdx_id: MIT`, which satisfies the
undocumented HACS OSI-licence check. It ships in every release automatically because HACS downloads
the tag's source archive; the release gate's presence check is belt-and-braces.

**The domain string is permanent.** `heatit_wifi_panel` was verified free across core, the brands
repository and the HACS catalog. A duplicate domain is the most common substantive rejection.

**Explicitly not required**, so the implementation does not invent work: release assets /
`zip_release`, `info.md`, the `images` check, `country`, `content_in_root`, `persistent_directory`, a
`hacs` minimum-version key, a `home-assistant/brands` PR, any repository-age requirement.

### 10.2 Releases

Recorded as **[ADR-0002](../adr/0002-tag-push-release-with-gate.md)**.

**Pushing a `vX.Y.Z` tag is the only way a release is created.** The manifest bump and the changelog
section land on `main` through an ordinary reviewed PR first; `release.yml` runs on the tag and, if
its gate passes, creates the GitHub release.

- Tags are `v`-prefixed SemVer; `manifest.json` carries the bare number. `v0.1.0` ↔ `0.1.0`. The form
  is **permanent** — HACS compares tag strings. There is no `VERSION` constant anywhere in the code;
  `manifest.json` is the single source.
- **0.x are ordinary stable releases** through the hardware-validation window. **`v1.0.0` is cut when
  the `hacs/default` PR opens.** The GitHub pre-release flag is reserved for genuine betas after 1.0:
  an all-pre-release repository has no `last_version` and falls back to the default branch, which is
  exactly what `hide_default_branch` exists to prevent.
- **Only the owner may create `v*` tags** (a GitHub tag ruleset). A failed gate **leaves the bare
  tag** — HACS ignores tags without releases — and the owner deletes it, bumps, and retags. No
  workflow is ever granted tag deletion.

**The gate.** `release.yml`'s publish job `needs` all of the following, run against the tagged SHA:

1. **HACS Action** and **hassfest**, the same jobs as `validate.yml`, with no `ignore:`.
2. **Both pytest rows** from §8.7, exposed via `workflow_call`, plus the linters and the two check
   scripts. A Home Assistant release that breaks us blocks our own release until fixed — chosen
   deliberately.
3. A lockstep script asserting: tag minus `v` == manifest `version`; the tagged commit is an
   **ancestor of `main`** (agent sessions work on side branches in worktrees, and a tag pushed from
   one must never become a release); `LICENSE`, `hacs.json`, `manifest.json` and `brand/icon.png`
   exist in the checkout; `hacs.json` has `hide_default_branch: true` and a present,
   AwesomeVersion-parseable `homeassistant` key; and `CHANGELOG.md` contains a non-empty
   `## [X.Y.Z]` section for the tag — that section's body becomes the release notes.

**Changelog.** `CHANGELOG.md` at the root in **Keep a Changelog** format. **Every PR writes its entry
under `## [Unreleased]`**, enforced by a PR check that fails when `CHANGELOG.md` is untouched unless
the PR carries the **`skip-changelog`** label (docs-only, CI-only). The rule is also stated in
`AGENTS.md`. The release PR renames Unreleased to the version with its date and rewrites the entries
into final form; the gate reads the result.

**Validators.** One `validate.yml`, two jobs: `hacs/action@main` with `category: integration` (no
checkout needed) and `actions/checkout` + `home-assistant/actions/hassfest@master`. Triggers: `push`,
`pull_request`, nightly `schedule`, `workflow_dispatch`. `permissions: {}`. **No `ignore:` anywhere.**
They are **unpinned on purpose**: the nightly run exists to catch HACS and hassfest changing their
rules under us, and pinning is what would make it stop telling the truth. Five checks (`archived`,
`description`, `issues`, `license`, `topics`) carry `allow_fork = False` and skip on fork PRs while
`hacs/default` runs all ten — so **the nightly run is the only truthful signal**, and a green PR run
does not predict the submission.

### 10.3 Repository settings — a human must apply these

Nightly-only HACS checks that no workflow can satisfy:

```
gh repo edit Normio/HeatIt-Wifi-Home-Assistant \
  --description "Home Assistant integration for the Heatit WiFi Panel wall heater (local HTTP API)" \
  --add-topic home-assistant --add-topic hacs --add-topic custom-component \
  --add-topic heatit --add-topic heater --add-topic climate
```

plus the **`v*` tag ruleset** (owner-only create) in repository settings. Both are still unapplied —
the session token that agreed the values could not write them — and both are gate item 5 in §11.

---

## 11. Release and submission

### 11.1 Sequencing

- **`v0.1.0` when config flow + climate work against the real panel.** Remaining platforms arrive as
  further 0.x releases.
- **The custom-repository URL is never shared before the first release exists**, because
  `can_download`'s `if self.data.releases` guard means the `homeassistant` floor gate **does not
  exist** for a repository without releases — users on old installs would be offered an incompatible
  download.

### 11.2 The submission gate

HACS-default-**ready** is the quality bar; **submission is deferred**. "Not production ready pending
live-device validation" is a documented `hacs/default` rejection and describes 0.x exactly. Opening
that PR is also the moment `v1.0.0` is cut, so this gate *is* the 1.0.0 gate.

The `hacs/default` PR opens only when **all** of:

1. The conformance register (§12) has been **executed in full on at least one real panel**, every row
   recorded as verified at that firmware, its write echoes saved into
   `tests/fixtures/observed/fw-<version>/`.
2. **Every platform has shipped** in a 0.x release — the catalog entry describes the whole 21-entity
   surface, not a growing one.
3. **At least one HA monthly release has shipped and been installed on the dev's own instance while
   the complete integration was running there** — one cycle of daily use, so a poll-loop,
   availability or restart bug has had a release boundary to show itself across.
4. The nightly `validate.yml` run is green.
5. The repository settings in §10.3 are applied.

Rejected alternatives: submitting on the checklist alone (a catalog entry for a growing integration);
checklist plus platforms with no soak (a slow-burn bug is then found by listed users); waiting for a
second panel or firmware (it does not exist).

### 11.3 The README

- **Facts only, never disclaimers.** The README never says "beta", "alpha", "not production ready",
  "pending validation" or any equivalent, in 0.x or after. That prose is what sank a real
  `hacs/default` submission, and the 0.x version number already carries the message.
- A **`## Verified firmware`** section: one table row per firmware, version first, then the unit it was
  verified on (`1.21 | 600 W (maxLoad 6)`), updated in the same PR as each new `observed/fw-<version>/`
  directory. Asserted in CI against the fixture directories **and** `VERIFIED_FIRMWARES` — all three
  copies of the fact or none.
- A **static DHCP reservation** is recommended (§4.5).
- A **one-line signpost** for owners of the Heatit **WiFi6 thermostat**, stating that this integration
  is for the WiFi Panel wall heater and pointing them at their own device's integration. It is a
  routing aid so HACS users searching "heatit" pick the right one — **not** an acknowledgement, and no
  prior-art credit or licence notice accompanies it.
- **Install docs are written in the `v0.1.0` release PR**, not before: a My Home Assistant redirect
  link plus the manual add-repository steps (HACS → Custom repositories → URL, category *Integration*).
  **HACS custom repository only** — no manual-copy route, which would bypass the floor gate and never
  see a release. The **`v1.0.0` release PR rewrites** that section to plain default-store instructions,
  because HACS refuses a custom-repository entry for a repo already in the default store.

---

## 12. Hardware conformance

**The register is [`docs/conformance/checklist.md`](../conformance/checklist.md).** It is not
reproduced here and must not be: it is *living* — a list of open questions that shrinks and a
regression suite that grows — while this document is frozen. At the time of writing it holds **58
rows, 41 verified at firmware 1.21, 17 open**.

### 12.1 What a row is

Seven columns: `id | claim | vs spec | tier | status | evidence | dependents`.

- **Ids are the research document's Q-numbers verbatim**, extended past Q38 for rows raised by
  decision tickets. Those numbers are cited in prose across immutable issue comments, so renumbering
  would dangle every citation. The cost — a permanently arbitrary, unsorted numbering — is accepted.
- **The claim is always what the integration depends on**, phrased falsifiably, never what the vendor
  document says. So a status is genuinely binary, and nuance ("accepted but silently snapped") is
  written into the claim rather than fudged in a verdict.
- **`vs spec`** is `agrees` / `disagrees` / `silent` — the three-claims problem of §0 turned into a
  column. Ten rows are `disagrees`, and they are the most valuable rows in the file: each records a
  place a future firmware could quietly revert to the documented behaviour.
- **`contradicted` is not `disagrees`.** A `disagrees` row was never true; a `contradicted` row
  *stopped* being true, with shipped code resting on it. The register is born with zero contradicted
  rows, which is why that status is the one that triggers work.
- **`dependents` is the blast radius**, so triaging a flipped row is reading one cell rather than
  hunting through this document.

**Measurements are threshold claims naming the constant they justify** — Q31 → the post-write refresh
delay, Q43 → the poll budget, Q30 → the one-request-in-flight lock, Q45 → `RESET_VERIFY_DELAY`,
recorded as the upper bound it is rather than the measurement it is not. A second panel that misses a
bound flips the row and points straight at the constant to retune, which a bare measurements table
could never do: a number with no threshold can never fail.

### 12.2 `scripts/probe.py`

**Specified here, built by the implementing session.** Standalone — raw HTTP, no import of the
integration — and **stdlib only**: `http.client` gives the control over protocol version and headers
that the HTTP-hygiene rows need, `socket` covers the backlog and keep-alive rows, and a stranger with
a second panel can run it with nothing but Python.

A check registers its **id and tier only**:

```python
@check("Q13", tier=THERMAL)
def eco_regulates_to_eco_setpoint(panel): ...
```

**The claim text is not in the script.** `probe.py` parses the register at runtime and takes the label
it prints from the claim cell, so the sentence exists once and a check that tightens what it asserts
cannot leave the register describing the older, weaker claim.

**Four ascending flags**, matching the register's *probe tiers*:

```
probe.py                 → read tier only, unattended, no approval
probe.py --writes        → + benign writes, snapshotted and restore-verified
probe.py --destructive   → + kWh reset, settings reset          (y/N)
probe.py --thermal       → + heater-on sequences                (y/N, TTY required)
```

Selection is `--check Q13 Q29` or `--group write`; the default run is every `read`-tier check.

- `--thermal` additionally requires `sys.stdin.isatty()` and a typed confirmation naming the check, so
  **no CI job, cron or background run can ever turn a heater on in someone's bedroom**. A thermal
  check also refuses to raise a setpoint more than 2 °C above the current room temperature, and caps
  how long it may leave the relay closed.
- **`/api/reset/factory` is structurally absent**: the string appears nowhere in the source, and
  `tests/test_probe_safety.py` asserts that by reading the file. It is not a flag that could be passed
  by accident.

**The revert contract**, and it does not trust the echo — because this panel lies in its echo:

1. Before the first write of a run, snapshot the full status to `.local/probe-snapshot-<ts>.json`.
2. Every parameter a check touches is registered for restore.
3. An exit hook — normal return, exception, `SIGINT`, `SIGTERM` — restores them and then **re-reads
   the status to verify**.
4. A failed or unverified restore prints a banner naming the parameter, its original value and the
   exact `curl` to fix it by hand, and exits non-zero.
5. `--restore <file>` replays a snapshot as a standalone command — the backstop for a run that died
   too hard for any hook to fire (`kill -9`, a sleeping laptop, a crash inside the hook). Those are
   exactly the cases where a 600 W heater is left running.

**Output** is a Markdown result table to stdout that pastes into an issue, plus a fixtures block and a
measurements block. Results are `PASS` / `FAIL` / `INCONCLUSIVE` / `SKIPPED (tier not enabled)` —
`INCONCLUSIVE` is a first-class result. **A human transcribes results into the register, deliberately:
no machine marks a claim verified.**

**Fixtures.** Run with writes enabled, the probe saves each **write and reset** response as raw bytes
into `tests/fixtures/observed/fw-<version>/`, replacing the transcribed ones (§8.3). It saves **no
status captures**: it imports nothing from the integration, so it cannot use the shared redaction
function, and a second copy of a redaction function is a leak waiting to happen. It does not need one —
a write echo is `{"status":"Success","heatingSetpoint":19.0}` and carries none of the five scrubbed
fields — so instead it **asserts fail-closed** that no scrub key appears in the response bytes and
refuses to write the file if one does. Status captures stay `capture_fixtures.py`'s job, where the
real scrub lives.

**Exit codes**: `0` all selected checks passed · `1` a check failed, i.e. a contradiction · `2` a
revert failed, the loud one · `3` usage or connectivity.

### 12.3 Manual rows and their procedures

Twelve rows are `manual` tier: no script may run them, and most are rows a single 600 W unit at
firmware 1.21 can **never** close — a factory reset, a 1500 W unit, a paired external sensor, a
firmware carrying low temperature protection, a host on the panel's own VLAN. The people who close
them are strangers with other hardware, so the register's appendix carries **nine numbered procedures
(P-1…P-9)** with preconditions, steps, what to record and where to send it. That appendix is the
contributor-facing half of the document.

### 12.4 CI enforces the register

`scripts/check_conformance.py`, run from `test.yml` beside `check_quality_scale.py` and from §9.4's
shared entry point. It fails when:

1. an id is duplicated or malformed, a row has the wrong column count, or `vs spec` / `tier` /
   `status` is outside its vocabulary;
2. a `verified` or `contradicted` row names a firmware that is not in `VERIFIED_FIRMWARES`;
3. a non-`open` row has no evidence, or an evidence entry does not resolve — a repo path that exists,
   an issue or PR link, or a `P-n` defined in the appendix;
4. a dependents cell carries no resolvable reference of those same kinds. Prose may sit alongside it,
   and does: during the spec era that reference is an ADR or an issue, and after implementation it
   becomes a module path updated by the PR that renames it — the same discipline §9.2 puts on
   quality-scale `done` comments;
5. an `open` `manual` row cites no procedure, or an appendix procedure is cited by no row;
6. **the set of non-`manual` ids in the register is not exactly the set registered in `probe.py`** —
   the one place the two can silently diverge.

The escape hatch is the vocabulary itself: `manual` tier and `open` status ask for nothing.

### 12.5 When a claim is contradicted

Four contradictions have already happened, and each surfaced *inside a live decision ticket* — so no
process was needed. That mechanism dies with this document's assembly, and the next contradiction
lands against a frozen spec with shipped code on it.

1. The row flips to `contradicted fw <v>` citing the run.
2. An issue labelled `conformance` opens, naming the row. Its **dependents** cell is the triage.
3. **One PR** carries the spec amendment (§15), the code change, the new fixture and the row restored
   to `verified fw <v>`, and closes the issue.

**The spec gains an amendment rather than being rewritten**, so the v1 document still reads as what
v1 claimed with its corrections appended and dated.

---

## 13. Open questions carried forward

None of these blocks the build. Each is written down so an implementer meets it as a known unknown
rather than a surprise.

1. **Seventeen open register rows**, listed in the register with their tiers and procedures. The ones
   most likely to touch code: **Q17** (can `loadLimit` exceed `maxLoad`? — §5.2 makes the load limit's
   maximum `maxLoad × 100` on a design choice the vendor document does not license); **Q4**
   (multi-parameter atomicity — the reason for one parameter per request); **Q52** (does the *device
   id* survive a factory reset or a firmware update? — the one identity claim ADR-0003 rests on);
   **Q23** (does `sensorCalibration` shift `roomTemperature`, or only the display?); **Q47** (does
   `OWD.activeTime` count down?).
2. **On-segment discovery.** Register row Q28 / procedure P-2, tracked as its own issue. It is blocked
   on network access, not on a decision, and it explicitly does **not** gate v1: the manifest ships
   `dhcp: [{"registered_devices": true}]` either way. If it ever turns up an advertisement, it amends
   this spec and flips `discovery` from `exempt` to `done`.
3. **The runtime response to firmware drift.** The *detection* half is settled — every claim sits in
   the register with the firmware it was verified at, a second firmware that disagrees flips a row to
   `contradicted`, and the dependents cell names what breaks. The *posture* half is settled — observed
   parameters only, a new fixture directory per panel or firmware, a parse-only sweep, dropped-parameter
   tolerance tested per observed parameter, an info line at setup for an unverified firmware, a vanished
   parameter making its entity unavailable. What is **not** settled is what the integration should
   *do at runtime* when a second observed firmware behaves differently from the first — the 0.5/0.1
   split, the snap-versus-reject asymmetry, the echo. Gate by firmware, warn, or ignore cannot be
   answered with one firmware, and there is exactly one. This graduates the day a second panel appears.
4. **The `import_executor` assembly note** in §10.1.
5. **The two unobserved parameters.** `externalSensorFallback` and `lowTemperatureProtection` return to
   the registry and the entity table only with a captured fixture that contains them (register Q48,
   Q49; procedures P-6, P-7). Three entity rows come back with them — a number and an enum sensor for
   low temperature protection, and an external-sensor-fallback switch — and the *low temperature
   protection* glossary entry's warning applies: its wire name means both a threshold and a live
   state, and the two must never share a name.

---

## 14. Decision records

| ADR | Decision |
|---|---|
| [0001](../adr/0001-no-fork-of-heatit-wifi6.md) | The prior-art integration for the related Heatit WiFi6 thermostat is **ignored** — not forked, not copied, not credited. The integration is written from the vendor document and the observed panel. |
| [0002](../adr/0002-tag-push-release-with-gate.md) | A `vX.Y.Z` **tag push is the only release trigger**, behind a gate that fails closed (§10.2). |
| [0003](../adr/0003-device-id-as-unique-id.md) | The panel's **device id, not its MAC, is the Home Assistant unique id** (§4.1). |
| [0004](../adr/0004-eco-as-a-climate-preset.md) | **Eco is a climate preset**, with both *setpoint banks* also exposed as config numbers — not a second target temperature (§5.3). |

---

## 15. Amendments

Corrections to this document after v1 was frozen. Each entry names the register row or issue that
forced it, and the PR that carried it.

**2026-09-09 — `scripts/check_layout.py` joins §3.1 and §9.4** ([#36](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/36), PR #49).
Three of #36's acceptance criteria — no `strings.json` anywhere, brand assets nowhere else in the
repository, `hacs.json` holding exactly three keys — have no upstream enforcer: hassfest validates
`strings.json` only when the file exists, and the HACS Action never looks past `hacs.json` and the
manifest. §3.1's `scripts/` listing gains `check_layout.py` and §9.4's command list gains one line.
It also asserts §10.1's fixed manifest keys and their order, and that no `quality_scale` key is
present — **§9.2's failure condition 4 moves to `check_quality_scale.py` when that script lands
([#47](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/47)), rather than living in
both.**

**2026-09-09 — `config_flow.py` ships with the scaffold** ([#36](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/36), PR #49).
§3.1 lists it, but #36 named only `manifest.json` and `__init__.py`. hassfest *errors* — not warns —
when a manifest declares `config_flow: true` and the file is absent, and this holds for custom
integrations. The scaffold therefore ships a `ConfigFlow` subclass with no steps;
[#40](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/40) fills it in. `const.py` is
present for the same reason, holding `DOMAIN` alone.

**2026-09-09 — §9.3's "ruff runs once, in its own `test.yml` job" is deferred, not dropped** ([#36](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/36), PR #49).
§9.4's "`test.yml` calls `scripts/check.sh`" was taken as the binding half. Until §8.7's rows exist
there is nothing to matrix over, so one job runs the whole script.
[#38](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/38) adds the two rows and splits
ruff back out, so it does not run once per row.

**2026-09-09 — required status checks join §10.3's human-applied list** ([#36](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/36), PR #49).
§9.3 says both linters "block a merge" and §10.3 lists what a workflow cannot apply, but branch
protection was named in neither. `Checks`, `HACS Action`, `hassfest` and `Changelog entry` must be
marked required on `main` by the owner; nothing in the repository can assert that they are.

**2026-09-09 — the client ticket refines §3.2, §8.5 and §8.7** ([#38](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/38)).
Three refinements met under fire. (1) §2.4's "quantise" and §8.5's "an off-step value raises
locally" are reconciled as: a value within float noise of a grid point *is* that grid point
(``0.1 * 3`` is ``0.3``), and anything further off the grid raises a local ``ValueError`` with
no request emitted — the client never rounds a user's value into a different one. (2) §3.2's
taxonomy gains ``HeatitMissingFieldError``, a subclass of ``HeatitProtocolError`` carrying the
dotted path of the absent *required core* field, because §6.3's ``missing_field`` translation
key needs the path and the coordinator must not re-parse. ``HeatitParameterRejected`` is raised
for a ``400`` **and** for a ``200`` whose envelope is not success: a refusal is a refusal, and
both carry ``reason`` verbatim; the same ``failed`` envelope on a reset is a
``HeatitResponseError`` with ``status_code`` 200 and the ``reason``. (3) §8.7's matrix lands with the client rather than with the
integration tests, so `test.yml`'s single `Checks` job becomes `Lint`, `Tests (floor)` and
`Tests (latest)`; the required status checks named in the amendment of PR #49 are now `Lint`,
`Tests (floor)`, `HACS Action`, `hassfest` and `Changelog entry`. `scripts/check.sh` takes a
`lint` or `test` stage so CI still runs the one shared file; the monthly cron runs both rows
rather than the latest row alone, since the floor row is free and confirms the pin still
installs; and §8.7's `config_flow.py` coverage gate joins `check.sh` with the config flow
([#40](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/40)), there being no
`config_flow.py` to cover yet. The shared redaction of §7.1 lives
in `api.py` beside the parser it scrubs for, and the fixture-only fifth placeholder for `name`
(§8.3) is applied by `scripts/capture_fixtures.py` alone — logging and diagnostics keep `name`.
