# Hardware conformance register

What we believe the Heatit WiFi Panel does, why we believe it, and on which panel.

This is a **living register**, not part of the frozen v1 spec. `docs/spec/heatit-wifi-panel-v1.md`
links here rather than restating it, so a row can flip without editing a versioned design document.
It supersedes §9 of `docs/research/panel-api-contract.md`, whose Q-numbers it keeps: a citation to
"Q13" anywhere in this repo's history still resolves to the row below.

Every claim is verified **at a firmware, on a panel** — never verified outright. One 600 W unit at
firmware 1.21 is not the fleet, and this register exists so that a second panel can find out where
we were wrong.

## How to read a row

| column | meaning |
|---|---|
| **id** | Stable forever. `Q1`–`Q38` come from the research document; `Q39`+ were raised by decision tickets. |
| **claim** | Phrased as *what the integration depends on*, falsifiably, so the status is genuinely binary. Never phrased as what the spec says. |
| **vs spec** | `agrees` / `disagrees` / `silent` — how the vendor's OpenAPI document relates to the claim. A `disagrees` row is the most valuable kind: it records a place a future firmware could quietly revert to the documented behaviour. |
| **tier** | The hazard class, matching the probe script's flags: `read`, `write`, `destructive`, `thermal`, `manual`. `manual` means no script can run it. |
| **status** | `open`, `verified fw <v>`, or `contradicted fw <v>`. |
| **evidence** | Where the claim came from: an issue, a committed fixture, or a `P-n` procedure for an open manual row. Checked by CI. |
| **dependents** | The blast radius if the row flips. Contains at least one resolvable reference (a repo path, an ADR, an issue) and may carry prose. Checked by CI. |

**`contradicted` is not the same as `disagrees`.** A row is born `open` or `verified`; `disagrees`
simply records that the vendor document was wrong from the start. `contradicted` appears only when a
run **disproves a claim we already shipped against** — which is why it starts empty and why it is the
status that triggers work.

## How a row is checked

Automated rows are run by `scripts/probe.py`, which selects checks by the ids in this file:

```
probe.py                 → read tier only, unattended, no approval
probe.py --writes        → + benign writes, snapshotted and restore-verified
probe.py --destructive   → + kWh reset, settings reset          (y/N)
probe.py --thermal       → + heater-on sequences                (y/N, TTY required)
```

`/api/reset/factory` is **structurally absent** from the probe: the path string appears nowhere in
its source, and a test asserts that. A factory reset unpairs the panel from the MyHeatit app and
strands it off WiFi; it is `manual` tier (Q52) and always will be.

`manual` rows have no script. Each carries a numbered procedure in the appendix — these are the rows
our single 600 W panel at fw 1.21 can never close, so they are written for whoever has different
hardware.

This file is the **single source of the claim wording**: `probe.py` parses it at runtime for the
labels it prints, so a check and its claim cannot drift apart. `scripts/check_conformance.py` asserts
in CI that ids are unique, statuses are legal, every `verified` row cites a firmware in
`VERIFIED_FIRMWARES` with evidence that resolves, every dependents cell carries a resolvable
reference, and the register and `probe.py` register exactly the same set of automated ids.

## When a claim is contradicted

A run that disproves a `verified` row:

1. flips the row to `contradicted fw <v>` and cites the run;
2. opens an issue labelled `conformance` naming the row — the **dependents** cell is the triage, so
   nobody has to hunt for what breaks;
3. is fixed in **one PR** carrying the spec amendment, the code change, the new fixture and the row
   restored to `verified fw <v>`, closing the issue.

The spec gains an **Amendments** section rather than being rewritten, so the v1 document still reads
as what v1 claimed, with its corrections appended and dated.

## The register

| id | claim | vs spec | tier | status | evidence | dependents |
|----|-------|---------|------|--------|----------|------------|
| Q1 | Temperature writes accept bare integers and off-step values; the setpoint banks silently snap to the 0.5 grid, the limits reject off-step | disagrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) number step and bounds |
| Q2 | Integer parameters given a decimal (`panelMode=1.0`) are rejected rather than truncated | silent | write | open | — | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) registry serialisation |
| Q3 | Booleans accept `true`/`True`/`TRUE`/`1` and the false equivalents; none is silently misread | silent | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) switch entities |
| Q4 | A multi-parameter write is atomic — one valid plus one out-of-range applies neither | silent | write | open | — | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) one parameter per request |
| Q5 | The 200 echo uses the names sent and reports the value **applied**, type-normalised | agrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) optimistic update |
| Q6 | Writing a parameter to its current value returns 200, not 422 | disagrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) no diff-before-write |
| Q7 | `DELETE /api/reset/kwh` zeroes the counter without its documented query parameter | disagrees | destructive | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#18](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/18) reset button |
| Q8 | A query-string write applies correctly (a JSON body also does; the query string is what we ship) | disagrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) client write path |
| Q9 | A body-less POST (`Content-Length: 0`) with a query string is accepted — aiohttp's default shape | silent | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) client posture |
| Q10 | `wifiSignalStrength` is signed, of the form `"-NNdBm"` | silent | read | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) signal sensor |
| Q11 | `Network.status` reads `"ok"` on a connected panel | agrees | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#21](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/21) diagnostics only |
| Q12 | `Network.mac` is **uppercase** hex with colons | disagrees | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | `docs/adr/0003-device-id-as-unique-id.md` — the `connections` migration hatch |
| Q13 | Eco mode regulates to `ecoSetpoint` | silent | thermal | verified fw 1.21 | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) climate presets — the founding assumption |
| Q14 | Either setpoint bank is writable in any panel mode; only the live one regulates | silent | write | verified fw 1.21 | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) setpoint numbers |
| Q15 | The temperature limits bound **both** banks, `min < max` is enforced, and narrowing a limit clamps a stored setpoint | silent | write | verified fw 1.21 | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) dynamic bounds |
| Q16 | The temperature limits also constrain low temperature protection | silent | manual | open | [P-7](#p-7) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) entity table |
| Q17 | `loadLimit` above the reported `maxLoad` is rejected, not accepted-and-misbehaving | silent | write | open | — | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) load limit bounds |
| Q18 | `state` reads `Idle` when the panel mode is Off | agrees | read | verified fw 1.21 | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) `hvac_action` mapping |
| Q19 | `state` reads `Heating` whenever the relay is closed, including while open window detection or low temperature protection is overriding | silent | manual | open | [P-4](#p-4), [P-7](#p-7) | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) `hvac_action` mapping |
| Q20 | `currentPower` trails the relay by ~15 s and must never drive `hvac_action` | silent | thermal | verified fw 1.21 | [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) power sensor |
| Q21 | A kWh reset lands the counter at exactly `0.00`, never a partial value | silent | destructive | verified fw 1.21 | [#18](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/18) | [#18](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/18) `total_increasing` and the 10 % dip rule |
| Q22 | `totalConsumption` carries two decimals on the wire | agrees | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) energy sensor |
| Q23 | `sensorCalibration` shifts `roomTemperature` in `/api/status`, not only the display | silent | write | open | — | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) temperature sensor |
| Q24 | No status field is ever `null`; a missing field means that parameter does not exist on this firmware | silent | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#14](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/14) required core and absent-field rules |
| Q25 | `OWD.activeTime` is `0` while `activeNow` is false | agrees | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) open-window duration sensor |
| Q26 | The device `id` survives a settings reset | silent | destructive | verified fw 1.21 | [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) | `docs/adr/0003-device-id-as-unique-id.md` |
| Q27 | `name` and `room` are free text; `room` is `""` before the panel is assigned in the app | silent | read | verified fw 1.21 | [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) | [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) title and `suggested_area` |
| Q28 | The panel advertises nothing discoverable on its own L2 segment | silent | manual | open | [P-2](#p-2) | [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) discovery, [#21](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/21) `quality_scale.yaml` |
| Q29 | An unknown path returns `404` with `Content-Type: text/html` and the body `Nothing matches the given URI`; `GET /` is the same, so there is no web UI | silent | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) config-flow fingerprint, no `configuration_url` |
| Q30 | The panel accepts at least 2 concurrent connections; its accept backlog fails at roughly 4–5 | silent | read | verified fw 1.21 | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) one-request-in-flight lock |
| Q31 | A write is reflected in `/api/status` within 1.5 s (observed 305–632 ms) | silent | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) post-write refresh delay |
| Q32 | The HTTP server refuses fast rather than hanging while the panel is rebooting or off WiFi | silent | manual | open | [P-3](#p-3) | [#14](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/14) `ConfigEntryNotReady`, [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) timeouts |
| Q33 | The panel answers only on tcp/80, plain HTTP — no HTTPS, no alternate port, no redirect | silent | read | verified fw 1.21 | [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) | [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) config flow |
| Q34 | A settings reset leaves `id`, `name`, `room` and the network block untouched, does not reboot, and settles within ~5 s | silent | destructive | verified fw 1.21 | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) settings-reset button |
| Q35 | The firmware version and the OpenAPI document's version are independent numbering schemes, and no endpoint or header exposes an API version | disagrees | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#14](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/14) `VERIFIED_FIRMWARES` |
| Q36 | The success sentinel is `"Success"` (capital S) and the failure sentinel `"failed"` (lowercase) | disagrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) client response parser |
| Q37 | The 200 write body is `{status, <echoed parameter names>}` — not the WiFi6 client's `{status, value}` | agrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) client response parser |
| Q38 | Re-sending an identical parameter write is harmless and returns 200 | silent | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) writes are never retried |
| Q39 | The panel speaks HTTP/1.1 only; an HTTP/1.0 request is refused with 505 | silent | read | verified fw 1.21 | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) client posture |
| Q40 | Responses carry `Content-Length`; the panel never uses chunked transfer | silent | read | verified fw 1.21 | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) client posture |
| Q41 | Success responses carry `Content-Type: application/json`, so `response.json()` works without a content-type override | silent | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) client parser — the WiFi6 device fails this |
| Q42 | Keep-alive is honoured and an idle socket survives at least 65 s | silent | read | verified fw 1.21 | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) shared HA session |
| Q43 | A status read completes in under 5 s (observed 30–210 ms) | silent | read | verified fw 1.21 | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) | [#17](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/17) poll budget and per-attempt timeout |
| Q44 | The energy counter survives a power cycle | silent | manual | open | [P-3](#p-3) | [#18](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/18) `total_increasing` |
| Q45 | The counter reads `0.00` within 5 s of a reset acknowledgement | silent | destructive | verified fw 1.21 | [#18](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/18) | [#18](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/18) reset-verification delay — an upper bound, not a measurement |
| Q46 | The energy counter advances in steps of no more than 0.05 kWh at any wattage | silent | manual | open | [P-5](#p-5) | [#18](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/18) one lost step per reset |
| Q47 | `OWD.activeTime` counts down in seconds while `activeNow` is true | agrees | manual | open | [P-4](#p-4) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) open-window duration sensor |
| Q48 | `externalSensorFallback` appears in status once an external sensor is paired | silent | manual | open | [P-6](#p-6) | [#12](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/12) observed parameters only |
| Q49 | `lowTemperatureProtection` appears in status on some firmware | silent | manual | open | [P-7](#p-7) | [#12](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/12) observed parameters only |
| Q50 | A settings reset on a 1500 W unit lands `loadLimit` at its `maxLoad` | agrees | manual | open | [P-8](#p-8) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) load limit bounds |
| Q51 | The 0.5 °C setpoint grid and the 0.1 °C calibration grid hold on firmwares other than 1.21 | silent | manual | open | [P-9](#p-9) | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) number steps |
| Q52 | The device `id` survives a factory reset and a firmware update | silent | manual | open | [P-1](#p-1) | `docs/adr/0003-device-id-as-unique-id.md` — every entity orphans if it churns |
| Q53 | Parameter values after a settings reset match the vendor document's stated defaults | silent | destructive | open | — | `docs/api/heatit-wifi-panel-openapi.yaml` — the only claim we have about post-reset state |
| Q54 | `/api/status` is computed per request, not served from a cache | silent | read | verified fw 1.21 | [#13](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/13) | [#12](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/12) fixture diff carries live-value noise |
| Q55 | A parameter-less POST gets no response at all — the firmware closes the connection; the documented 422 does not exist | disagrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#14](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/14) write error handling |
| Q56 | A 400 body is freeform text naming the offending parameter, not the document's fixed `invalid data.` | disagrees | write | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#14](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/14) device `reason` surfaced verbatim |
| Q57 | A reset returns `{"status":"Success"}` — the `status` key, uniform with parameter writes, not the documented `reset` key | disagrees | destructive | verified fw 1.21 | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) | [#7](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) client response parser |
| Q58 | `sensorMode=true` on a panel with no external sensor paired returns a success echo but does not apply — the echo lies | silent | write | verified fw 1.21 | [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) | [#14](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/14) silent-undo warning, [#11](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/11) switch entity |

**41 verified at firmware 1.21, 17 open.** Nothing is `contradicted` — the ten places the vendor
document is simply wrong are recorded as `disagrees`, which is a different thing: they were never
true, rather than having stopped being true.

## Appendix: manual procedures

These are the rows no script may run. Most need hardware this project does not have. If you run one,
open an issue labelled `conformance` on this repository with the results and the raw response bytes;
that is how a row goes green for a firmware or a model we have never seen.

Record with every result: the **firmware** string, the **model** string, and `maxLoad`, all from
`GET /api/status`. A result without them cannot be entered in the register.

<a id="p-1"></a>
### P-1 — the device `id` across a factory reset and a firmware update (Q52)

The one identity claim ADR-0003 rests on. Destructive and disruptive: a factory reset unpairs the
panel from the MyHeatit app and drops it off WiFi.

1. `GET /api/status`; record `id` verbatim, and `Network.mac`.
2. Factory reset the panel from the device itself (see the vendor manual — **not** via this API).
3. Re-pair in the MyHeatit app; note the new IP address.
4. `GET /api/status`; record `id` verbatim.
5. Separately, if a firmware update becomes available: record `id` and `firmware` before, apply the
   update, record both after.

Report: both `id` values, both `firmware` values, and whether `Network.mac` changed.

<a id="p-2"></a>
### P-2 — on-segment discovery (Q28)

Needs a host on the panel's **own L2 segment**. Link-local mDNS (224.0.0.251, TTL 1) cannot cross a
routed boundary, so a sweep from another VLAN is no evidence at all.

The full checklist, including what has already been ruled out from off-segment, is in
[#32](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/32). In short: a ~30 s
`avahi-browse -art`, the targeted ESP-family service types, an SSDP `M-SEARCH`, and the router's DHCP
lease hostname for the panel's MAC.

Report: every record that resolves to the panel, with service type, instance name, port and all TXT
keys — a matcher is only as good as the fields it can key on. A clean negative is a useful result and
becomes the `discovery` exemption comment.

<a id="p-3"></a>
### P-3 — power cycle and WiFi loss (Q32, Q44)

1. `GET /api/status`; record `totalConsumption`.
2. Cut mains power to the panel for 30 s, then restore it.
3. Poll `GET /api/status` every second from restore. Record how long until the first successful
   response, and whether earlier attempts **refuse fast** or hang until timeout — that distinction
   decides the client's connect timeout.
4. Record `totalConsumption` on the first successful response.
5. For the WiFi half: take the panel's SSID down instead of its power, and record the same.

Report: time to first response, the failure mode before it (connection refused / no route / timeout),
and the counter value either side.

<a id="p-4"></a>
### P-4 — an open window detection event (Q19, Q47)

Needs a real temperature drop, so it needs an actual open window and a cold day.

1. Enable open window detection (`openWindowDetection=true`) and set the panel heating with the
   comfort setpoint above room temperature, so the relay is closed.
2. Open a window near the panel.
3. Poll `GET /api/status` every 5 s until `OWD.activeNow` becomes true, then for a further 5 minutes.
4. Record every distinct `OWD.activeTime`, with its timestamp, and `state` throughout.

Report: whether `activeTime` decreases monotonically in seconds, what it starts at, and whether
`state` reads `Idle` or `Heating` while the override is active.

<a id="p-5"></a>
### P-5 — energy publication step size at another wattage (Q46)

Needs a panel that is not 600 W.

1. Record `maxLoad`. Set the panel heating so the relay stays closed continuously.
2. Poll `GET /api/status` every 5 s for at least 20 minutes.
3. Record every distinct `totalConsumption` value with its timestamp and the `currentPower` alongside.

Report: the step size between consecutive distinct values and the interval between them — this tells
us whether publication is energy-based or time-based, which one 600 W unit cannot distinguish.

<a id="p-6"></a>
### P-6 — a paired external temperature sensor (Q48)

Needs an external sensor, which nobody on this project has.

1. `GET /api/status`; confirm `externalSensorFallback` is absent from `parameters`.
2. Pair the external sensor and set `sensorMode=true`.
3. `GET /api/status`; record the whole `parameters` object.
4. Disconnect or obstruct the sensor and record `roomTemperature` — does it fall back, hold the last
   value, return `0.0`, or drop the field?

Report: the full status body at each step, raw. On this firmware `sensorMode=true` on an **unpaired**
unit is silently ignored behind a success echo, so step 3 is the only thing that can distinguish
"absent" from "conditional".

<a id="p-7"></a>
### P-7 — a firmware carrying low temperature protection (Q16, Q19, Q49)

Needs a firmware other than 1.21, where the parameter actually exists.

1. `GET /api/status`; confirm `lowTemperatureProtection` is present, and record its shape — the
   vendor document uses one wire name for both the threshold and the live state.
2. Set a threshold above current room temperature and record `state` and `currentPower` once the
   relay closes.
3. Set `minimumTemperatureLimit` above the threshold, then below it, recording the threshold after
   each — do the limits clamp it?

Report: the raw status at each step, and the firmware string.

<a id="p-8"></a>
### P-8 — settings reset on a non-600 W unit (Q50)

Needs a 1500 W (or any non-600 W) panel. Destroys that panel's settings.

1. `GET /api/status`; record `maxLoad` and the full `parameters` object.
2. `DELETE /api/reset/settings`.
3. Wait 10 s, then `GET /api/status` and record `parameters` again.

Report: `maxLoad`, and `loadLimit` before and after. This also fills Q53 for that model.

<a id="p-9"></a>
### P-9 — quantisation on another firmware (Q51)

Needs any panel whose `firmware` is not `1.21`. Benign, self-reverting, no thermal effect if you stay
below room temperature.

1. Record `heatingSetpoint` and `sensorCalibration`.
2. Write `heatingSetpoint` to an off-grid value below room temperature (e.g. `18.3`). Record the echo
   and the value in `/api/status` afterwards — snapped, rejected, or accepted as sent?
3. Write `minimumTemperatureLimit` to an off-grid value. Record the same.
4. Write `sensorCalibration=0.1`. Record the same.
5. Restore all three to their original values and verify by a status read.

Report: firmware, and for each write the echo body and the subsequent status value.
