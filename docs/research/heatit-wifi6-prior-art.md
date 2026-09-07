# Prior art audit: `mattik-gh/heatit_wifi6`

Research output for [issue #4](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/4) — *Research: audit mattik-gh/heatit_wifi6 against current standards*.
Parent map: [issue #1](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/1).

**Scope note.** This document deliberately issues **no fork / read-and-rewrite / ignore verdict**. Per the scope change from the map owner, that decision moved to [issue #16](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/16), which is blocked on this ticket plus [#2](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/2) (current HA conventions) and [#3](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/3) (HACS default requirements). What follows is fact-finding, structured so someone else can score it.

**Method.** The repository was cloned and read in full — all 1,548 lines of Python across both shipped integration directories, plus the vendored OpenAPI document, `manifest.json`, `hacs.json` and the complete git history. Requirements were taken from primary sources (developers.home-assistant.io rule pages and the `home-assistant/core` source itself), cited inline. The README was read but is not the basis of any judgement here.

**Audited revision.** `569fc32`, 2026-06-09 (repository HEAD at time of audit, 2026-09-07).

---

## 1. Licence — the hard facts

### What it is

`LICENSE.md` is the **MIT License**, verbatim and unmodified, with the copyright line:

```
Copyright (c) 2025 mattik-gh
```

GitHub's own licence detection agrees (`repos/mattik-gh/heatit_wifi6` → `license.spdx_id == "MIT"`). `README.md` restates it. There is no second licence, no `NOTICE`, no CLA, and no DCO sign-off requirement configured on the repository.

### Obligations a fork or copy-with-modification creates

MIT imposes exactly one affirmative obligation. The operative sentence is:

> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

Concretely, for a repository we intend to publish on HACS:

| Situation | Obligation |
| --- | --- |
| Fork the repo wholesale | Retain `LICENSE.md` with the `Copyright (c) 2025 mattik-gh` line intact. We may add our own copyright line; we may not remove or replace theirs. |
| Copy a *substantial portion* (e.g. lift `api.py`, or the climate mode-mapping logic, into our tree) | Ship the MIT notice and the copyright line alongside — conventionally as a `LICENSE-THIRD-PARTY` / `NOTICE` file, or as a header comment on the derived file naming the origin. |
| Copy a trivial fragment (a one-line idiom, a constant, an endpoint path string) | No obligation attaches. Endpoint paths and parameter names come from Heatit's own OpenAPI document, not from this repo, and are facts about the device rather than expressive work. |
| Read it, learn from it, write our own | **No obligation at all.** MIT constrains distribution of the code, not knowledge gained from reading it. |

MIT is permissive and imposes no copyleft, no share-alike, and no restriction on relicensing the combined work. It does not conflict with HACS in any way — HACS requires only that a repository *have* a licence.

### The two licence facts that actually constrain the map

**(a) HA core is Apache-2.0, and MIT-derived code creates a provenance question there.**
The map's stated quality bar is "built so Home Assistant **core** inclusion stays viable". Home Assistant core is licensed Apache-2.0 and contributions are accepted under those terms. MIT → Apache-2.0 relicensing is legally permitted (MIT is one-way compatible with Apache-2.0), *provided the MIT notice is preserved*. But the practical consequence is that a core PR containing MIT-derived third-party code arrives carrying a foreign copyright header and a second licence file, which a core reviewer must reason about rather than wave through. A clean-room implementation carries none of that. **This is the licence consideration that bears on the map's quality bar, and it is a friction/provenance argument, not a legal prohibition.** Recording it here; the trade-off is #16's to weigh.

**(b) The copyright line is incomplete, so a fork inherits an unclear chain.**
`LICENSE.md` names only `mattik-gh`, but the git history shows substantial authorship by others:

- `atlehogberg` — commits `fc82835`, `6a7cfcd`, `07482d2`, `3907d8c`, `c867d6d`, `1eb1b01` (2026-02 → 2026-03). This is *most of the current `api.py`* (retry logic), the staggered-startup code in `__init__.py`, and the eco-preset handling in `climate.py`.
- `Vladislav` / `vlad-323` — commits `94e1b71`, `8af4b9d`, `5d330f5` (2025-09).

These arrived as pull requests (#2, #7) against a repo with no CLA and no DCO. Under the standard inbound=outbound position (GitHub ToS §D.6, and the repo's own MIT licence as the stated project licence) those contributions are offered under MIT, so a fork is safe. But the `LICENSE.md` copyright line is factually incomplete, and a scrupulous attribution of forked code names at least three people — one of whom (`atlehogberg`) maintains a competing downstream fork. HACS default listing does not care about this. HA core review plausibly would.

**Bottom line on licence: MIT is permissive and creates no blocking obligation. The only real cost of copying is a preserved third-party notice plus an incomplete-authorship chain, and the only real risk is added friction on a future core PR. Reading the code freely costs nothing.**

---

## 2. Maintenance signals

All figures from the GitHub API on 2026-09-07.

| Signal | Value |
| --- | --- |
| Created | 2025-03-31 |
| Last push | 2026-06-09 (~3 months before audit) |
| Total commits | 14, on a single `main` branch |
| **Releases** | **0** |
| **Tags** | **0** |
| Stars | 15 |
| Forks | 4 |
| Watchers | 4 |
| Open issues/PRs | 4 open (issues #3, #5, #6, #9) |
| Archived | No |
| Repo description | **empty** |
| Repo topics | **none** |
| In HACS default list | **No** — `hacs/default`'s `integration` file (3,264 entries) contains no `heatit` entry. Installation is via "Custom repositories" only, as the README itself instructs. As of HEAD it also could not be accepted: it ships two integration directories, violating HACS's one-integration-per-repository rule (§3.4 #29). |
| Tests | None. No `tests/` directory, no test framework, no fixtures. |
| CI | None. No `.github/` directory at all — no hassfest action, no HACS action, no linting. |
| `quality_scale` | Not declared in `manifest.json`; no `quality_scale.yaml`. |

### Apparent user base and project health

15 stars and 4 forks put this at "a handful of households". Named individuals visible in the issue tracker running it: `mattik-gh`, `atlehogberg` (reports 5–6 thermostats), `nacree`, `chrispylizard`, `lvlie`, `t-liski-navi`, `santa-krauja`, `vlad-323`. That is roughly the whole observable population.

Three signals matter more than the counts:

1. **The maintainer has declared limited availability.** In issue #5 (2026-02-13) the owner writes: *"I have limited time to continue development and debug of this Heatit Wifi6 project. It works well for me as is."* PR #7 — the substantial stability rewrite — sat from 2026-03-04 to 2026-06-09 before merge, with contributors pinging for attention (issue #6).

2. **Modernisation attempts have not landed.** Two independent contributors tried to convert the integration from the single-climate-entity-with-attributes model to a proper multi-entity model:
   - PR #8 (`santa-krauja`, "Update to use entities") — **closed unmerged, 2026-03-15, with no comment**.
   - Issue #9 (`lvlie`, 2026-03-23) — offers a branch adding real power/energy sensors plus a CI pipeline. **Open and unanswered.**

   The attributes-not-entities design is not an accident awaiting a patch; it is defended by the maintainer (issue #3: users should build template sensors from attributes in `configuration.yaml`). Anyone building on this repo inherits an architecture whose owner has declined to change it.

3. **The merge that landed left the repo structurally broken** — see §3, `hacs.json`/structure rows. `custom_components/` now contains **two** integration directories, `heatit_wifi6` and `heatit_wifi6_custom`, byte-identical except for the `DOMAIN` constant and a UTF-8 BOM/line-ending difference in the vendored YAML. `atlehogberg` flagged this himself in issue #5 (*"the `heatit_wifi6_custom/` files at the bottom should be ignored and not included in the pull"*); they were merged anyway.

---

## 3. Conformance audit against current standards

Requirements are cited to the Home Assistant Integration Quality Scale rule pages and to `home-assistant/core` source. The Bronze tier is the baseline HA states is required of all new integrations; Silver/Gold rows are included where the map's "core inclusion stays viable" bar makes them relevant.

Legend: ✅ conforms · ⚠️ partial / fragile · ❌ does not conform · n/a not applicable.

### 3.1 Config entry lifecycle and runtime data

| # | Requirement | Source | What `heatit_wifi6` does | Conforms | Remediation cost |
| --- | --- | --- | --- | --- | --- |
| 1 | `ConfigEntry.runtime_data` must be used to store runtime data; use a typed `ConfigEntry` alias, e.g. `type MyIntegrationConfigEntry = ConfigEntry[MyClient]` | QS Bronze `runtime-data` | Uses `hass.data.setdefault(DOMAIN, {})` in `async_setup`, and `hass.data[DOMAIN].pop(entry.entry_id, None)` on unload. Nothing is ever actually *stored* there — the dict is created and popped but never written. The API client is constructed inside `climate.py`'s `async_setup_entry` and held only by the entity. | ❌ | Low mechanically, but only after a coordinator exists to *be* the runtime data. Currently there is no object to store. |
| 2 | Setup must check whether setup is possible, raising `ConfigEntryNotReady` for transient failure so HA retries | QS Bronze `test-before-setup` | `climate.py:async_setup_entry` calls `api.get_device_id(retries=0, timeout=8)`; on failure it **logs a warning, fabricates a fake id** (`f"unknown_{host.replace('.', '_')}"`) and adds the entity anyway. `__init__.py:async_setup_entry` unconditionally returns `True`. `ConfigEntryNotReady` is never raised anywhere in the codebase. | ❌ | Moderate. This is the root cause of open issue #4 ("Reload required after HA restart") — HA's own retry machinery is bypassed, so a device that is slow at boot is permanently degraded until manual reload. |
| 3 | Do not block setup; use HA's retry rather than sleeping | QS Bronze `test-before-setup`; core setup contract | `__init__.py` computes a per-entry index and does `await asyncio.sleep(index * 2 + 2)` **inside `async_setup_entry`**, before forwarding platforms. Every entry sleeps at least 2 s; the sixth panel sleeps 12 s. | ❌ | Low to delete, moderate to replace. The *problem* it addresses is real (see §5). The fix is wrong: it serialises setup rather than handling failure. |
| 4 | Support config entry unloading | QS Silver `config-entry-unloading` | Implements `async_unload_entry`, but via `async_forward_entry_unload(entry, "climate")`. | ⚠️ | Trivial. Core's own docstring on `ConfigEntries.async_forward_entry_unload` says: *"Its is preferred to call `async_unload_platforms` instead of directly calling this method."* (`homeassistant/config_entries.py` L2888-2894). Not deprecated, but not the preferred call. |
| 5 | `async_setup` should not exist purely to seed `hass.data` | — | Defines `async_setup` solely to `hass.data.setdefault(DOMAIN, {})`. With `runtime_data` this function has no reason to exist. | ⚠️ | Trivial (delete). |
| 6 | `PARALLEL_UPDATES` must be specified per platform | QS Silver `parallel-updates` | Not defined in `climate.py`. | ❌ | Trivial (one line). |

### 3.2 Data fetching, coordinator, and failure handling

| # | Requirement | Source | What `heatit_wifi6` does | Conforms | Remediation cost |
| --- | --- | --- | --- | --- | --- |
| 7 | Use `DataUpdateCoordinator` when a single poll serves many entities; signal failure with `UpdateFailed`; use `async_config_entry_first_refresh` so a failed first fetch raises `ConfigEntryNotReady` | HA docs, *Fetching data*; QS `test-before-setup` | **No coordinator anywhere.** The single `ClimateEntity` polls itself in `async_update()`. `DataUpdateCoordinator`, `CoordinatorEntity` and `UpdateFailed` are not imported in any file. | ❌ | High — this is the structural rewrite. With one entity the absence is survivable; the Panel's ~25-entity, 7-platform surface makes a coordinator mandatory (otherwise 25 entities poll the device independently). |
| 8 | Recommended to pass a shared web session into the client — `async_get_clientsession(hass)` for aiohttp; create your own only in special cases such as cookie isolation | QS Platinum `inject-websession` | `api.py` constructs **a brand-new `aiohttp.TCPConnector` and `aiohttp.ClientSession` for every single HTTP call** — `_get`, `_post` and `_delete` each open and tear down a session inside their own `async with`. It also forces `resolver=aiohttp.resolver.ThreadedResolver()` and `trust_env=False`. `hass` is never passed to the API class. | ❌ | Low to fix (inject the session), but it invalidates the whole `HeatitWiFi6API` constructor signature. At 1 request/min/device the waste is tolerable; at the Panel's target entity count with several panels it is not. |
| 9 | Errors must propagate so the coordinator can mark entities unavailable | QS Silver `entity-unavailable`, `log-when-unavailable` | Every error path in `api.py` **swallows the exception and returns `{}`** — `_get` (both `TimeoutError` and bare `except Exception`), `_post`, `_delete`. Nothing ever raises. The entity then infers unavailability from a falsy dict. `exceptions.py` defines `CannotConnect`, which is imported by `climate.py` and **never raised or caught anywhere**. | ❌ | Moderate. This is the defect with the widest blast radius: the caller cannot distinguish "device offline", "malformed JSON", "HTTP 400 out of range" and "HTTP 422 no parameters changed". For the Panel that matters directly — the API's documented 400/422 responses become indistinguishable from a network drop. |
| 10 | Set an appropriate polling interval, declared where HA reads it | QS Bronze `appropriate-polling` | `climate.py` sets `SCAN_INTERVAL = timedelta(minutes=POLL_INTERVAL)` **as a class attribute on the entity**. Core reads it from the *platform module*: `homeassistant/helpers/entity_component.py` L191 — `scan_interval=getattr(platform, "SCAN_INTERVAL", None)`. A class attribute is therefore never consulted; the platform falls back to the `climate` component's own `SCAN_INTERVAL`, which is `timedelta(seconds=60)` (`homeassistant/components/climate/__init__.py` L101). | ❌ (latent) | Trivial (move to module scope). **The bug is currently invisible only by coincidence**: climate's 60 s default happens to equal the intended `POLL_INTERVAL = 1` minute. Change the constant and nothing happens — which is exactly the trap a derived integration would fall into, since the Panel handoff proposes a 30 s default. |
| 11 | `should_poll` handling | core `entity_platform.py` | Sets `should_poll = False` as a plain class attribute (not `_attr_should_poll`), then **mutates `self.should_poll = True` at runtime inside `async_added_to_hass`**, after `async_add_entities([entity], False)`. | ⚠️ | Trivial under a coordinator (`CoordinatorEntity` handles it). As written the polling registration depends on the ordering of core's add-entity sequence rather than on a declared value. |
| 12 | Service/entity actions should raise exceptions on failure | QS Silver `action-exceptions` | `async_set_temperature`, `async_set_preset_mode` and `async_set_hvac_mode` all fail silently — `set_parameter` returns `{}` and the `if` simply does not fire. The user sees no error; the UI reverts on the next poll. | ❌ | Moderate. |

### 3.3 Entities, naming and identity

| # | Requirement | Source | What `heatit_wifi6` does | Conforms | Remediation cost |
| --- | --- | --- | --- | --- | --- |
| 13 | Entities set `_attr_has_entity_name = True` (*"required for new integrations"*) | QS Bronze `has-entity-name`; HA docs, *Entity* | `climate.py` L61 declares **`attr_has_entity_name = True`** — the leading underscore is missing. This is not a recognised attribute name; it sets an inert instance attribute and `has_entity_name` remains `False`. | ❌ | Trivial to fix (one character), but fixing it *changes every entity's `friendly_name`* for existing users, so upstream is now somewhat trapped by it. |
| 14 | Entity names come from `EntityDescription` / translation keys, not hand-rolled `name` properties | QS Gold `entity-translations`; HA docs, *Entity* | No `EntityDescription` of any kind is used — the string "EntityDescription" does not appear in the repository. `climate.py` defines a `name` **property with a setter** returning the raw user-typed name. | ❌ | High for the Panel's surface. An entity-description-driven table is the natural shape for ~25 parameter-backed entities; this repo offers no such table to borrow. |
| 15 | Entities have a unique ID, not user-configurable | QS Bronze `entity-unique-id`; HA docs, *Entity* | `unique_id` returns `f"heatit_wifi6_{self._device_id}"`. The device id comes from `/api/status`. **But** when the device is unreachable at setup, `_device_id` becomes `f"unknown_{host.replace('.', '_')}"` — i.e. the unique ID is **derived from the IP address**, which is user-configurable and can change via DHCP. A device set up while offline gets a permanently wrong, IP-derived unique ID. | ⚠️ | Low to fix given #2 is fixed — raising `ConfigEntryNotReady` removes the fallback path entirely. |
| 16 | Prevent duplicate setup of the same device | QS Bronze `unique-config-entry` | `config_flow.py` never calls `async_set_unique_id` or `_abort_if_unique_id_configured`. Adding the same panel twice creates two entries and two colliding entities. | ❌ | Low. |
| 17 | Test the connection in the config flow before creating the entry | QS Bronze `test-before-configure` | The config flow performs **no I/O at all**. It prepends `http://` if missing and immediately `async_create_entry`. A typo'd IP creates a broken entry with no feedback. | ❌ | Low. |
| 18 | Integration creates devices with complete `DeviceInfo` | QS Gold `devices`; HA device registry docs | **No `DeviceInfo` anywhere** — the string does not appear in the repository. The integration creates a bare `climate` entity with no device, so no `manufacturer`, `model`, `sw_version`, `connections`, or `suggested_area`. All of it is dumped into `extra_state_attributes` instead (`hw_firmware`, `net_mac`, `net_ipAddress`, …). | ❌ | Moderate. Confirmed as a live user complaint — issue #9 asks for "a proper device with sensors". |
| 19 | Entities assigned `EntityCategory` where appropriate | QS Gold `entity-category` | Not used; there is only one entity. | ❌ (n/a in practice) | — |
| 20 | Entities use device classes | QS Gold `entity-device-class` | Not used — power, energy, temperature and signal strength are all untyped attribute strings, so none reach the Energy dashboard or long-term statistics. | ❌ | Moderate. This is the single most-requested missing feature upstream (issues #3 and #9). |
| 21 | Icon translations rather than hardcoded icons | QS Gold `icon-translations` | `climate.py` hardcodes an `icon` property returning `"mdi:radiator"` / `"mdi:radiator-off"`. | ❌ | Trivial. |

### 3.4 Manifest, translations, and repository structure

| # | Requirement | Source | What `heatit_wifi6` does | Conforms | Remediation cost |
| --- | --- | --- | --- | --- | --- |
| 22 | `manifest.json` `requirements` lists third-party PyPI deps, pinned | HA docs, *Integration manifest* / *Building a Python library* | Declares `"requirements": ["aiohttp"]`. `aiohttp` is a Home Assistant **core** dependency, already present; listing it is both unnecessary and unpinned. | ❌ | Trivial (delete the key). |
| 23 | `dependencies` lists HA integrations genuinely required | HA docs, *Integration manifest* | Declares `"dependencies": ["network"]`. Nothing in the code uses the `network` integration. | ⚠️ | Trivial (delete). |
| 24 | `version` key required for custom integrations; HACS states releases are *"preferred but not required"* — a repo without releases installs from the default branch | HA docs, *Integration manifest*; HACS *Publish → Integration* | `version` present: `"1.1.2"`. But there are **no git tags and no GitHub releases**, so every HACS install pulls whatever `main` happens to be, and the manifest version corresponds to nothing pinned. Users cannot roll back. | ⚠️ | Not a HACS violation, but it forfeits versioning entirely — directly relevant to the map's open "release & CI hygiene" item. |
| 25 | HACS requires `manifest.json` to contain `domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version` | HACS *Publish → Integration* | All six present and well-formed. `iot_class: local_polling` is also correct. | ✅ | — |
| 26 | `strings.json` is the source of translatable strings; `translations/en.json` is generated from it | HA docs, *Internationalization* | **No `strings.json`.** Ships hand-maintained `translations/en.json` and `translations/fi.json` only. | ❌ | Low. |
| 27 | Exception messages translatable | QS Gold `exception-translations` | No `HomeAssistantError`/`ServiceValidationError` raised at all — see #12. | ❌ | Moderate. |
| 28 | HA core: brand assets live in the `home-assistant/brands` repo (QS Bronze `brands`). HACS additionally states you *"must provide brand assets for your integration"* by *"adding a `brand` directory in your repository with at least an `icon.png` file"* | QS Bronze `brands`; `home-assistant/brands`; HACS *Publish → Integration* | Ships `brands/icon.png` and `brands/logo.png` — plural, and nested **inside `custom_components/heatit_wifi6/`** rather than at the repo root. Commit `07482d2` states the rationale: *"as this is a custom integration and will not pick up from central repository by default"*. Verified: **no `heatit` folder exists in `home-assistant/brands`**, in either `core_integrations/` or `custom_integrations/`. | ❌ | Low, but it satisfies neither requirement as placed, and the `home-assistant/brands` route needs an external PR. Useful side-fact: **the `heatit` brand slug is currently unclaimed.** |
| 29 | *"There must only be one integration per repository, i.e. there can only be one subdirectory to `ROOT_OF_THE_REPO/custom_components/`."* | HACS *Publish → Integration* (verbatim) | Contains **two**: `heatit_wifi6/` and `heatit_wifi6_custom/`, byte-identical but for the `DOMAIN` constant. Both declare `config_flow: true`. | ❌ | **The one unambiguous, quotable HACS violation in the repo.** Trivial to fix upstream (delete one directory) but it is the state of `main` today, and it means the repo could not be accepted into the HACS default list as it stands. |
| 30 | `hacs.json` | HACS publishing docs | Present: `{"name": "HeatIT WiFi6 Thermostat", "render_readme": true}`. Minimal but valid. | ✅ | — |
| 31 | Repository description and topics set | HACS Action checks | Both **empty**. | ❌ | Trivial. |
| 32 | CI: hassfest action + HACS Action on PR and schedule | HACS publishing docs; HA docs | **No `.github/` directory at all.** Neither action has ever run against this repository. | ❌ | Low to add; likely to surface a batch of the failures listed above. |
| 33 | Test coverage — Bronze requires full config-flow coverage; Silver requires >95% overall | QS Bronze `config-flow-test-coverage`; QS Silver `test-coverage` | **Zero tests.** No `tests/`, no `conftest.py`, no `pytest-homeassistant-custom-component`. | ❌ | High. Nothing here to reuse for the map's testing-strategy ticket (#12). |
| 34 | Strict typing; `py.typed` | QS Platinum `strict-typing` | Essentially untyped. `api.py` annotates three return types (`-> str`, `-> dict`); `climate.py`'s ~30 methods carry **one** annotation (`available -> bool`). No `py.typed`, no mypy config. | ❌ | High. |
| 35 | Common patterns in common modules (`coordinator.py`, `entity.py`) | QS Bronze `common-modules` | No `coordinator.py`, no `entity.py`. All entity logic lives in a single 502-line `climate.py`. | ❌ | High. |

### 3.5 Defects found while reading — independent of convention

These are not style points; they are bugs on code paths we would otherwise be tempted to copy.

| # | Location | Defect |
| --- | --- | --- |
| D1 | `climate.py` `async_set_temperature` | Calls `self.hass.components.persistent_notification.create(...)`. The `hass.components` accessor **no longer exists on `HomeAssistant`** in current core (verified: no `components` property on the class in `homeassistant/core.py`). On any current HA this line raises `AttributeError` at runtime. It is reached whenever a user sets a temperature while the device is OFF. |
| D2 | `api.py` `set_parameter` / `reset_device` | Both test `response.get("status", "Failed") == "Success"` — **capitalised**. The device's own OpenAPI document (vendored in this repo) defines the response enum as lowercase `success` / `failed`, and the Panel's spec agrees. Against a spec-conformant device this comparison **never matches**, so every successful write is logged as an error and returns `{}`, and every caller's `if` fails. |
| D3 | `api.py` `_post` | Sends parameters as a **JSON body** (`session.post(url, json=data)`). The vendored WiFi6 OpenAPI document declares all 25 parameters as `in: query` (verified: 25 × `in: query`, zero `requestBody`). The code therefore contradicts the spec it ships. It evidently works on real firmware, but that is undocumented, unverified leniency. |
| D4 | `climate.py` `async_set_temperature` | `setattr(self, param, temperature)` writes `self.heatingSetpoint`, an attribute nothing ever reads. The intended target is `self._param_heatingSetpoint`. Dead write; the optimistic update never happens. |
| D5 | `climate.py` `hvac_modes` | Returns a **dynamic** list computed from the *current* mode (`[OFF, COOL]` while cooling, `[OFF, HEAT]` otherwise). HA expects a stable capability list; a mutating `hvac_modes` misleads the UI and voice assistants and makes `HVACMode.COOL` unreachable once the device is in heat. |
| D6 | `climate.py` | No `min_temp` / `max_temp` / `target_temperature_step` properties, despite the device reporting its own limits. HA's defaults apply. Confirmed against real user data posted in upstream issue #5: `min_temp: 7, max_temp: 35` — HA's built-in defaults, not the device's documented 5.0–40.0. |
| D7 | `api.py` `_LOGGER` calls | `_LOGGER.error("set_parameter({parameter, value}): %s", str(response))` — literal braces, not an f-string. Several sibling lines mix an f-string with trailing `%s` lazy-logging args, producing malformed log output. |
| D8 | `climate.py` `_hvac_mode_to_heatit_operatingmode` | Returns `-1` on an unrecognised mode, and the caller POSTs that `-1` to the device without checking. |
| D9 | `climate.py` module scope | `errors = {}` — an unused module-level mutable global. `import homeassistant.helpers.config_validation as cv` — unused. |
| D10 | Vendored spec, `Heatit_WiFi6_OpenAPI_v70.yaml` | Heatit's own document is internally inconsistent: the parameter keyed `internalMinimumTemperatureLimit` declares `name: internalMinTemperature` — i.e. the documented wire name differs from the key used everywhere else. Also `state` is typed `boolean` while its `enum` is the strings `Idle`/`Heating`/`Cooling`. **Relevant beyond this repo: it is direct evidence that Heatit's OpenAPI documents contain errors, which supports the map's decision to treat "the spec says X" and "the device does X" as separate claims.** |

---

## 4. API surface diff — WiFi6 thermostat vs Panel

Sources: the WiFi6 OpenAPI **v7.0.0** document vendored at `custom_components/heatit_wifi6/docs/Heatit_WiFi6_OpenAPI_v70.yaml`, against the Panel API **v12.0.0** as transcribed in `.orca/drops/heatit-wifi-panel-ha-integration.md`.

The handoff's claim is that the API surface is *"almost identical"*. The endpoint **shapes** are indeed the same — `GET /api/status`, `POST /api/parameters` with query-string parameters, `DELETE /api/reset/{factory,settings,kwh}`. The **contents** are not.

### 4.1 Headline numbers

- WiFi6 exposes **25** writable parameters. The Panel exposes **15** (plus read-only `maxLoad`).
- **5** parameters are shared with identical name, type, range and semantics: `heatingSetpoint`, `ecoSetpoint`, `temperatureDisplay`, `activeDisplayBrightness`, `openWindowDetection`.
- That is **20% of the WiFi6 surface** and **33% of the Panel surface**.
- **12** WiFi6 parameters have no Panel counterpart. **3** Panel parameters have no WiFi6 counterpart.

### 4.2 Same name, different meaning — the dangerous class

These are the entries where a copied implementation compiles, runs, and is wrong.

| Parameter | WiFi6 (v7.0.0) | Panel (v12.0.0) | Consequence of copying |
| --- | --- | --- | --- |
| `sensorMode` | **integer 0–5**: Floor / Internal / Internal+floor-limit / External / External+floor-limit / Power-regulator | **boolean**: `false` = internal sensor, `true` = external wireless sensor | Entirely different domain. The WiFi6 integration's single most-advertised feature — v0.9.4's "current temperature is dynamically based on `sensorMode`", with its `SENSORMODES` lookup table and the `match … case 0 / case 3\|4` dispatch in `async_update` — **is inapplicable to the Panel**, which has exactly one temperature reading (`roomTemperature`). Copying it would map boolean `True` to no case and silently fall through to the default branch. |
| `disableButtons` | **boolean** (`false`/`true`/`0`/`1`) | **integer 0/1/2**: enabled / disabled / lock menu | WiFi6 models this as a switch; the Panel needs a 3-state `select`. A copied boolean mapping silently loses "lock menu" and may write `true` where `2` was meant. |
| `standbyDisplayBrightness` | 1–10 | **0**–10 | A copied `number` entity's `min` is off by one; the Panel's "display off in standby" value becomes unreachable. |

### 4.3 The mode parameter — renamed *and* re-valued

This is the sharpest divergence, and it sits on the write path.

| | WiFi6 `operatingMode` | Panel `panelMode` |
| --- | --- | --- |
| 0 | OFF | Off |
| 1 | Heating (default) | Heating |
| 2 | **Cooling** | **Eco** |
| 3 | **ECO** | *(does not exist)* |

The parameter is renamed, so a literal copy fails loudly (`operatingMode` → HTTP 400/422 on a Panel — the safe failure). The hazard is the *plausible adaptation*: rename the key to `panelMode` and keep the value map, and `async_set_preset_mode(PRESET_ECO)` writes `panelMode=3`, which is out of range, while `HVACMode.COOL` writes `panelMode=2` and silently puts the heater into **Eco** instead of cooling. The Panel has no cooling function at all; `coolingSetpoint` does not exist on it.

The WiFi6 climate code also entangles mode and preset in a way the Panel cannot inherit: `operatingMode=3` (eco) is reported as `HVACMode.HEAT` + `PRESET_ECO`, but `async_set_hvac_mode(HEAT)` writes `operatingMode=1`, silently clearing eco; and `async_set_preset_mode` writes the mode directly, so selecting a preset while the device is OFF turns it on. **These are precisely the semantics [issue #8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) must decide, and this prior art gets them wrong.**

### 4.4 Renamed, analogous concept

| Concept | WiFi6 | Panel | Note |
| --- | --- | --- | --- |
| Sensor calibration | `internalCalibration`, `floorCalibration`, `externalCalibration` (3 × −6.0…6.0) | `sensorCalibration` (1 × −6.0…6.0) | Three collapse to one, under a different name. |
| Temperature limits | `internal{Min,Max}`, `floor{Min,Max}`, `external{Min,Max}TemperatureLimit` (6) | `minimumTemperatureLimit`, `maximumTemperatureLimit` (2) | Six collapse to two, under different names. |
| Load sizing | `sizeOfLoad` 0–99 (×100 W; **0 = use power metering**) | `loadLimit` 1–15 (×100 W), bounded by read-only `maxLoad` 4–15 | Same idea, different name, different range, different sentinel, and the Panel's upper bound is **device-reported at runtime** — a `number` entity whose `max` is dynamic. No WiFi6 equivalent of that pattern exists to copy. |

### 4.5 WiFi6-only — 12 parameters with no Panel counterpart

`sensorValue` (NTC resistance 0–7), `floorMinimumTemperatureLimit`, `floorMaximumTemperatureLimit`, `externalMinimumTemperatureLimit`, `externalMaximumTemperatureLimit`, `floorCalibration`, `externalCalibration`, `regulationMode` (PWM vs hysteresis), `temperatureControlHysteresis` (0.3–3.0), `actionAfterError` (0 or 10–65535 s), `coolingSetpoint`, `powerRegulatorActiveTime` (PWER duty cycle).

Every one of these is a *floor-thermostat driving an external relay/load* concept. A panel heater has no floor sensor, no user-selectable NTC, no cooling mode, and no relay duty cycle. Roughly half the WiFi6 integration's surface area is modelling a device the Panel is not.

### 4.6 Panel-only — 3 parameters with no WiFi6 counterpart

| Parameter | Shape | Note |
| --- | --- | --- |
| `externalSensorFallback` | boolean | No analogue. |
| `lowTemperatureProtection` | **nested object**: `{ lowTemperatureProtection: 0\|1–10, activeNow: "disabled"\|"Idle"\|"Heating" }` | A frost-protection feature with both a writable threshold and a read-only tri-state status, sharing the outer key name. Awkward to model, and there is **no prior art for it at all**. |
| `maxLoad` | integer 4–15, read-only | Bounds `loadLimit`. |

### 4.7 Status-payload divergences

| Field | WiFi6 | Panel | Consequence |
| --- | --- | --- | --- |
| Network block key | **`network`** (lowercase) | **`Network`** (capital N) | A copied `data.get("network", {})` returns `{}` on the Panel — **silent, total loss of SSID, MAC, IP, signal strength and status**. The MAC loss also breaks `CONNECTION_NETWORK_MAC` in `DeviceInfo`. A pure copy-paste landmine with no error. |
| Temperature | `internalTemperature`, `floorTemperature`, `externalTemperature` | `roomTemperature` | Three fields become one, renamed. |
| `state` enum | `Idle` \| `Heating` \| `Cooling` | `Idle` \| `Heating` | The `Cooling` → `HVACAction.COOLING` branch is dead code on a Panel. |
| `parameters.OWD` | `{openWindowDetection, activeNow, activeTime}` | same | ✅ One of the few structures that transfers cleanly. |
| `parameters.lowTemperatureProtection` | absent | nested object | New. |
| `totalConsumption`, `currentPower`, `id`, `name`, `room`, `firmware` | present | present | ✅ Transfer cleanly. |

### 4.8 Verdict on the handoff's premise

**The endpoint grammar is shared; the vocabulary is not.** "Almost identical" holds for *how you talk to the device* (URL shapes, query-string writes, echo-back responses, `DELETE` resets) and fails for *what you can say* (5 of 25 parameters identical; the mode parameter renamed and re-valued; the network key re-cased; roughly half the WiFi6 surface modelling floor-heating hardware the Panel does not have).

The divergences are concentrated **on the write path** — `panelMode` values, `disableButtons` arity, `sensorMode` type — which is the failure mode the ticket warned about. Two of them (`Network` casing, `panelMode`=2) fail *silently* rather than loudly. This finding is direct input to [#7 the parameter-write contract](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/7) and [#8 climate modes and presets](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8).

---

## 5. Concretely reusable candidates

Listed without judgement on whether we should take them — that is #16's call. Each is tagged with whether taking it would trigger the §1 attribution obligation.

### 5.1 Knowledge — free, no attribution obligation

| # | What | Why it is worth having |
| --- | --- | --- |
| K1 | **Content-Type workaround.** `api.py` deliberately parses JSON from `response.text()` rather than `response.json()`, with the comment: *"aiohttp `response.json()` require a correct content-type header on the http response. parse json from `response.text()` is immune of content-type header."* | Hard-won device behaviour: Heatit firmware apparently returns JSON with a wrong or missing `Content-Type`. If true of the Panel, `await response.json()` fails outright. **This belongs in the hardware conformance checklist (#13) as an assumption to verify**, and it is not derivable from the OpenAPI spec. |
| K2 | **Startup congestion with multiple devices.** Upstream issues #4 and #5 document, from several users independently, that polling 5–6 Heatit WiFi devices simultaneously on 2.4 GHz at HA restart causes most of them to time out and land permanently "unavailable". `atlehogberg` reports 4 of 5 failing consistently. | Real operational evidence bearing directly on the map's open "multi-panel topology" question. Note the *problem* is credible and the *fix* in this repo (`asyncio.sleep` in setup) is wrong; the correct answers are `ConfigEntryNotReady` + HA's own retry, a shared session with a connector limit, and generous timeouts. |
| K3 | **`coolingSetpoint` / mode-value collision.** §4.3. | Prevents a specific, silent, plausible bug in our climate implementation. |
| K4 | **Heatit's own specs contain errors.** D10. | Independent corroboration for the map's insistence on a conformance checklist. |
| K5 | **The maintainer's argument against eco-as-preset.** Upstream issue #5: eco is *"a preset rather than a distinct operating mode"*, and HA can manage setpoints centrally without it — countered by `atlehogberg`, who wants a device-local fallback setpoint that survives HA or WiFi going down. | A real, articulated design debate on exactly the question [#8](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/8) must settle. Worth reading both sides. |
| K6 | **Users want energy/power as first-class entities, not attributes.** Upstream issues #3, #9 and PR #8 are all the same request. | Validates the map's "full v1 entity surface" decision against real user demand. |

### 5.2 Code and artefacts — would trigger attribution if copied

| # | What | Assessment as a candidate |
| --- | --- | --- |
| C1 | **The vendored WiFi6 OpenAPI v7.0.0 YAML** (`custom_components/heatit_wifi6/docs/Heatit_WiFi6_OpenAPI_v70.yaml`, 992 lines) | Not the maintainer's work — it is Heatit's document, and the authoritative Panel equivalent is v12.0.0 from Heatit directly. Its value here is **comparative**: it lets us see how Heatit's spec conventions changed between v7 and v12, and it is the source of the D10 error evidence. Reference material, not a reuse candidate. |
| C2 | **HTTP client shape** (`api.py`, 165 lines) | Method surface — `get_status()`, `set_parameter()`, `reset_device(type)` — is a reasonable shape and close to what the handoff already proposes. But the *implementation* is disqualified on four counts: per-request session creation (§3.2 #8), universal error swallowing (#9), JSON body instead of query string (D3), and the `"Success"` casing bug (D2). The idea is worth ~10 minutes of thought; the code is a liability. |
| C3 | **Config flow** (`config_flow.py`, 41 lines) | 41 lines with no connection test, no `unique_id`, no error handling, and a user-typed `CONF_NAME` that should not exist. There is essentially nothing here. [#10](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/10) starts from a blank page regardless. |
| C4 | **Parameter-to-entity mapping table** | **Does not exist.** There is no `EntityDescription` table anywhere in the repository — parameters are hand-copied one line at a time into a 38-key `extra_state_attributes` dict. The single most valuable artefact for our purposes is the one thing this prior art does not contain. |
| C5 | **Test setup** | **Does not exist.** Zero tests, no CI. Nothing for [#12](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/12) to build on. |
| C6 | **`lvlie`'s Prism-mock CI pipeline** — described in upstream issue #9, living in the `lvlie/heatit_wifi6` fork, *not* in `mattik-gh/main`. It mocks the device from the OpenAPI spec using Stoplight Prism, boots Home Assistant, installs the custom integration, drives it via an injected automation, and asserts the HA log is clean. | **The most interesting single artefact in this repository's orbit**, and it is not in the repository. It attacks the map's hardest constraint — "no hardware" — by generating a device simulator directly from the spec we already have. Same MIT licence via the fork. Flagged as a candidate for [#12](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/12); the author self-describes it as vibe-coded and unreviewed, so it is a *technique* worth evaluating more than a codebase worth importing. Not yet independently verified by this audit. |

### 5.3 Naming and collision

| Question | Finding |
| --- | --- |
| Domain collision | None. `heatit_wifi_panel` vs `heatit_wifi6` are distinct, and the map's choice already anticipated this. |
| Third domain in the wild | `heatit_wifi6_custom` is also shipped and installable from the same repo (§3.4 #29). Any future `heatit_*` naming should assume both exist. |
| HACS default-list name clash | `heatit_wifi6` is **not in the HACS default list**, so it holds no reserved name there. "Heatit WiFi Panel" and "HeatIT WiFi6 Thermostat" are distinguishable in any case. |
| `home-assistant/brands` | **The `heatit` brand slug is unclaimed** — no folder in `core_integrations/` or `custom_integrations/`. Whoever files first shapes the brand grouping for every future Heatit integration. Worth deciding deliberately rather than by accident. |
| Heatit's official presence | Heatit's own "Works with Home Assistant" support is Z-Wave only (per the handoff) and does not occupy the WiFi/local-HTTP space. |

---

## 6. Decision deferred

**The fork / read-and-rewrite / ignore decision is explicitly NOT made in this document.** It is deferred to [issue #16](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/16), which is blocked on this ticket, on [#2](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/2) (current HA integration conventions) and on [#3](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/3) (HACS default repository requirements).

### Open questions #16 will need answered

1. **What tier is the target?** Nearly every ❌ in §3 is a Bronze or Silver rule. Whether they read as "modernisation debt" or "irrelevant" depends entirely on the tier the map commits to — currently unfixed. (#2, #3)
2. **Does the map's "HA core stays viable" bar make §1(a) binding?** If a core PR is a genuine future intent, the MIT-provenance friction plus the incomplete copyright chain (§1(b)) has weight. If core is aspirational, it is noise.
3. **How much of §3 is *this repo* versus *the era*?** #2 should establish when `runtime_data`, `EntityDescription` and `_attr_has_entity_name` became expected. Some of these findings may be a 2025-vintage integration that was never updated rather than one written badly.
4. **Is a 20%/33% parameter overlap enough to call it a base?** §4 quantifies it; someone must decide what threshold matters. Note the shared 20% is the *easy* part (setpoints, brightness), and the divergent part is the *hard* part (mode semantics, the write contract).
5. **Does the K2 startup-congestion evidence change the multi-panel design?** It is the map's only real-world data point on concurrent Heatit polling. (#10, #14)
6. **Is C6 (Prism-mock CI) worth an independent evaluation?** It is out-of-tree, unreviewed, and attacks the map's hardest constraint. It may deserve its own ticket regardless of what #16 decides about the parent repo. (#12)
7. **Should we claim the `heatit` brand slug in `home-assistant/brands`?** It is unclaimed and first-mover shapes it. Not currently ticketed.

---

## Appendix: sources

**Primary — code and repository data.** `mattik-gh/heatit_wifi6` @ `569fc32`, cloned and read in full on 2026-09-07: all Python in `custom_components/heatit_wifi6/` and `custom_components/heatit_wifi6_custom/`, `manifest.json`, `hacs.json`, `LICENSE.md`, `translations/*.json`, `docs/Heatit_WiFi6_OpenAPI_v70.yaml`, and the complete `git log`. Repository metadata, issues #3–#9 with full comment threads, PRs #1/#2/#7/#8, and the fork list via the GitHub API.

**Primary — Home Assistant.**
- Integration Quality Scale and its rule pages: <https://developers.home-assistant.io/docs/core/integration-quality-scale/>, `.../rules/runtime-data`, `.../rules/test-before-setup`, `.../rules/inject-websession`, and the full rule checklist at `.../integration-quality-scale/checklist`
- Entity documentation (`_attr_has_entity_name`, `unique_id`, `should_poll`): <https://developers.home-assistant.io/docs/core/entity/>
- Config entries: <https://developers.home-assistant.io/docs/config_entries_index/>
- Fetching data / `DataUpdateCoordinator`: <https://developers.home-assistant.io/docs/integration_fetching_data/>
- Building a Python library: <https://developers.home-assistant.io/docs/api_lib_index/>
- `home-assistant/core` source, read directly via the GitHub API: `homeassistant/config_entries.py` (the `async_forward_entry_unload` docstring, L2888-2894), `homeassistant/helpers/entity_component.py` (`SCAN_INTERVAL` lookup, L191), `homeassistant/helpers/entity_platform.py`, `homeassistant/core.py` (absence of a `components` accessor)
- `home-assistant/brands` repository contents (`core_integrations/`, `custom_integrations/`)

**Primary — HACS.** Publishing requirements: <https://hacs.xyz/docs/publish/integration/>. `hacs/default` repository, `integration` file (3,264 entries, checked for `heatit`).

**Project.** `.orca/drops/heatit-wifi-panel-ha-integration.md` (the Panel API v12.0.0 transcription used for §4); issues [#1](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/1) and [#4](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/4).
