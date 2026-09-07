# HACS default repository: requirements and release process

Research resolving [#3](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/3) (parent map [#1](https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues/1)).
Researched 2026-09-07 against live sources.

**Target:** `heatit_wifi_panel` accepted into the HACS default list, without foreclosing Home Assistant **core** inclusion later.

**Sources are primary only** — `hacs/documentation` (the source of hacs.xyz), `hacs/integration` (the code the HACS Action actually executes), `hacs/action`, `hacs/default` (workflows, scripts, PR template, and ~300 recent merged/closed PRs), `home-assistant/brands`, `home-assistant/actions`, `home-assistant/core` (`script/hassfest/`, `homeassistant/loader.py`), and developers.home-assistant.io. Where the published docs and the enforcing code disagree, the code is quoted and the disagreement is called out.

> **Read §5 and §8 before making any structural decision.** §5 documents a rule that changed in 2026 and invalidates most third-party write-ups of this process. §8 enumerates every place HACS and core pull in different directions.

---

## 1. TL;DR — the gate, in order

1. Public GitHub repo, not archived, issues enabled, non-empty description, ≥1 topic, repo name must **not contain "HACS"**.
2. OSI-approved licence detected by GitHub, at the repo root. *(New check, added July 2026; not in the published docs table.)*
3. `README.md` at root, with real documentation — not two lines.
4. `hacs.json` at root: `name` required, **no unknown keys** (strict schema).
5. Exactly one directory under `custom_components/`, named exactly `heatit_wifi_panel`.
6. `manifest.json` with `domain`, `name`, `version`, `documentation`, `issue_tracker`, `codeowners` (HACS) plus `iot_class` (hassfest), keys **sorted**.
7. **Brand assets in-tree** at `custom_components/heatit_wifi_panel/brand/icon.png`. The `home-assistant/brands` route is closed to new custom integrations (§5).
8. `HACS Action` + `hassfest` workflows green, **with no `ignore:`**.
9. A published GitHub **release** created *after* those runs went green, containing all of the above.
10. A `+1/-0` one-line PR to `hacs/default`'s `integration` file, from a personal fork, from a non-`master` branch, with "allow edits from maintainers" on, every template box `[x]`, and three links.

---

## 2. HACS general requirements (all categories)

Source: [`hacs/documentation` → `source/docs/publish/start.md`](https://github.com/hacs/documentation/blob/main/source/docs/publish/start.md)

| Requirement | Detail |
| --- | --- |
| Hosting | "Only public repositories on GitHub will work with HACS." |
| Description | The GitHub repo description is shown in the HACS UI; must be non-empty. |
| Topics | GitHub topics must be set. Not displayed in HACS, but used for search. |
| README | "a readme with information about how to use it". |
| `hacs.json` | Must exist **in the repo root**. |
| Versions | "If the repository uses GitHub releases, the tag name from the latest release is used to set the remote version. *Just publishing tags is not enough, you need to publish releases.*" Without releases, the first 7 chars of the last commit are used. |

### 2.1 `hacs.json` — the authoritative schema

The docs table is informative; the enforced schema is
[`custom_components/hacs/utils/validate.py`](https://github.com/hacs/integration/blob/main/custom_components/hacs/utils/validate.py):

```python
HACS_MANIFEST_JSON_SCHEMA = vol.Schema(
    {
        vol.Optional("content_in_root"): bool,
        vol.Optional("country"): _country_validator,
        vol.Optional("filename"): str,
        vol.Optional("hacs"): str,
        vol.Optional("hide_default_branch"): bool,
        vol.Optional("homeassistant"): str,
        vol.Optional("persistent_directory"): str,
        vol.Optional("render_readme"): bool,
        vol.Optional("zip_release"): bool,
        vol.Required("name"): str,
    },
    extra=vol.PREVENT_EXTRA,
)
```

Two things the prose docs do not make obvious:

1. **`extra=vol.PREVENT_EXTRA`** — any key not in that list is a hard validation failure. Do not copy `"domains"`, `"iot_class"`, `"homeassistant_min"` etc. from other people's files, and do not typo a key.
2. **`render_readme`** is accepted by the schema and exists on the `HacsManifest` dataclass, but has **no consumer anywhere in `hacs/integration`** — it is effectively dead. It is also absent from the documented table.

| Key | Type | Req. | Meaning / our value |
| --- | --- | :---: | --- |
| `name` | str | **yes** | Display name in the HACS UI, and it wins over `manifest.json`'s `name`. `"Heatit WiFi Panel"`. |
| `content_in_root` | bool | no | Content at repo root instead of `custom_components/<domain>/`. **Leave unset** — it would break the core-compatible layout, and it also moves where the `brands` check looks for `brand/icon.png`. |
| `zip_release` | bool | no | Download a named zip release asset instead of the source archive. Integrations only; requires `filename`. **Do not use** (§6.3). |
| `filename` | str | no | Asset/file name; for integrations only meaningful with `zip_release`. |
| `hide_default_branch` | bool | no | Hides "install from default branch" in the UI. Set **true** once we publish releases. |
| `country` | str \| list | no | ISO 3166-1 alpha-2, upper-cased, validated against HACS's `LOCALE`. Hides the repo from users configured to other countries. The panel works on any LAN — **leave unset**. |
| `homeassistant` | str | no | Minimum HA version. Enforced by `can_download` / `_ensure_download_capabilities`, but **only for repos that publish releases** (§6.5). Append `b0` to allow HA betas. |
| `hacs` | str | no | Minimum HACS version. Leave unset. |
| `persistent_directory` | str | no | Path inside the installed dir preserved across upgrades (backed up to a tempdir and restored). We keep no such state — leave unset. |
| `render_readme` | bool | no | Dead key (see above). Leave unset. |

Proposed `hacs.json`:

```json
{
  "name": "Heatit WiFi Panel",
  "homeassistant": "2026.3.0",
  "hide_default_branch": true
}
```

The `2026.3.0` floor is not arbitrary — see §5.3. It is the version from which in-tree brand images render, and it is currently the only brand route available to us.

---

## 3. Integration-specific requirements

Source: [`source/docs/publish/integration.md`](https://github.com/hacs/documentation/blob/main/source/docs/publish/integration.md)

### 3.1 Repository structure

- "There must only be one integration per repository, i.e. there can only be one subdirectory to `ROOT_OF_THE_REPO/custom_components/`. *If there are more than one, only the first one will be managed.*"
- "All files required for the integration to run must be located inside the directory `ROOT_OF_THE_REPO/custom_components/INTEGRATION_NAME/`."

This layout is a superset of core's, so it costs nothing:

```
custom_components/heatit_wifi_panel/__init__.py
custom_components/heatit_wifi_panel/manifest.json
custom_components/heatit_wifi_panel/brand/icon.png
...
hacs.json
README.md
LICENSE
```

This structural rule is **not ignorable**. If `custom_components/` has no subdirectory, [`repositories/integration.py`](https://github.com/hacs/integration/blob/main/custom_components/hacs/repositories/integration.py) raises before any check runs:

```python
raise HacsException(
    f"{self.string} Repository structure for {self.ref.replace('tags/', '')} is not compliant"
)
```

**Gotcha — the directory name must equal the domain.** HACS resolves the *remote* path as "the first directory under `custom_components/`" but computes the *local* install path from the manifest:

```python
@property
def localpath(self):
    return f"{self.hacs.core.config_path}/custom_components/{self.data.domain}"
```

If they disagree, HACS writes the files into a directory Home Assistant will not load.

### 3.2 `manifest.json`

Two validators run against it, and they want different things.

**HACS** — [`INTEGRATION_MANIFEST_JSON_SCHEMA`](https://github.com/hacs/integration/blob/main/custom_components/hacs/utils/validate.py):

```python
INTEGRATION_MANIFEST_JSON_SCHEMA = vol.Schema(
    {
        vol.Required("codeowners"): list,
        vol.Required("documentation"): url_validator,
        vol.Required("domain"): str,
        vol.Required("issue_tracker"): url_validator,
        vol.Required("name"): str,
        vol.Required("version"): vol.Coerce(AwesomeVersion),
    },
    extra=vol.ALLOW_EXTRA,
)
```

`extra=vol.ALLOW_EXTRA` — HACS does not object to the rest of a normal HA manifest. Only those six are *required*.

**hassfest** — [`script/hassfest/manifest.py`](https://github.com/home-assistant/core/blob/dev/script/hassfest/manifest.py):

```python
CUSTOM_INTEGRATION_MANIFEST_SCHEMA = INTEGRATION_MANIFEST_SCHEMA.extend(
    {
        vol.Required("documentation"): vol.All(vol.Url(), custom_documentation_url),
        vol.Optional("version"): vol.All(str, verify_version),
        vol.Optional("issue_tracker"): vol.Url(),
        vol.Optional("import_executor"): bool,
    }
)
```

Note the base schema has **no `extra=ALLOW_EXTRA`** — unknown keys are rejected by hassfest even though HACS allows them. And although `version` is `vol.Optional` in the schema, a separate hard check makes it mandatory for custom integrations:

```python
def validate_version(integration: Integration) -> None:
    if not integration.manifest.get("version"):
        integration.add_error("manifest", "No 'version' key in the manifest file.")
        return
...
    if not integration.core:
        validate_version(integration)
```

Combined requirements for our manifest:

| Key | Required by | Constraint |
| --- | --- | --- |
| `domain` | both | Must equal the directory name (`"Domain does not match dir name"`). |
| `name` | both | — |
| `version` | both | AwesomeVersion-parseable as CalVer / SemVer / SimpleVer / BuildVer / PEP 440. |
| `documentation` | both | HACS: any valid URL. hassfest: **https**, and **must not** start with `https://www.home-assistant.io/integrations` (`custom_documentation_url`). |
| `issue_tracker` | HACS only | Valid URL. hassfest treats it as optional. |
| `codeowners` | both | List; each entry must start with `@` ("Code owners need to be valid GitHub handles"). |
| `iot_class` | hassfest | Error `"Domain is missing an IoT Class"` if absent. One of `assumed_state, calculated, cloud_polling, cloud_push, local_polling, local_push`. |
| key **order** | hassfest | `"Manifest keys are not sorted correctly: domain, name, then alphabetical order"`. |

Proposed manifest — HACS-valid, hassfest-valid, and as close to core-shaped as HACS allows:

```json
{
  "domain": "heatit_wifi_panel",
  "name": "Heatit WiFi Panel",
  "codeowners": ["@Normio"],
  "config_flow": true,
  "documentation": "https://github.com/Normio/HeatIt-Wifi-Home-Assistant",
  "integration_type": "device",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/Normio/HeatIt-Wifi-Home-Assistant/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

### 3.3 `version` — also enforced by Home Assistant itself

`homeassistant/loader.py` **blocks a custom integration from loading** if `version` is missing or unparseable:

```python
if integration.version is None:
    _LOGGER.error(
        "The custom integration '%s' does not have a version key in the"
        " manifest file and was blocked from loading. ...", integration.domain)
    return None
try:
    AwesomeVersion(integration.version, ensure_strategy=[
        AwesomeVersionStrategy.CALVER, AwesomeVersionStrategy.SEMVER,
        AwesomeVersionStrategy.SIMPLEVER, AwesomeVersionStrategy.BUILDVER,
        AwesomeVersionStrategy.PEP440])
except AwesomeVersionException:
    ... return None
```

([`home-assistant/core` → `homeassistant/loader.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/loader.py); enforced since HA 2021.6 — [announcement](https://developers.home-assistant.io/blog/2021/01/29/custom-integration-changes/).) Plain SemVer is the safe choice.

### 3.4 Domain availability — verified 2026-09-07

`heatit_wifi_panel` is free everywhere it matters:

| Namespace | Result |
| --- | --- |
| `home-assistant/core` `homeassistant/components/heatit_wifi_panel` | 404 — free. |
| HACS default catalog (`https://data-v2.hacs.xyz/integration/data.json`, 3244 entries) | No entry with domain `heatit_wifi_panel`; in fact **no `heatit*` domain at all** — `mattik-gh/heatit_wifi6` is not in `hacs/default`. |
| `home-assistant/brands` `custom_integrations/heatit_wifi_panel` | 404 — free. (`custom_integrations/heatit_wifi6` exists.) |
| `home-assistant/core` `homeassistant/brands/heatit.json` | Exists: `{"domain": "heatit", "name": "Heatit", "iot_standards": ["zwave"]}`, images in `core_brands/heatit/`. |

This matters because **duplicate domain is the single most common substantive rejection** on `hacs/default` (§4.5). It also confirms the map's choice of `heatit_wifi_panel` over `heatit`: taking the bare `heatit` domain would collide with the existing core brand and would read as overriding a core integration, which `include.md` rules out for default listings.

Also note hassfest emits `"Domain collides with built-in core integration"` for a core-domain clash — but `add_warning`, not `add_error`, so it does **not** fail the job. Do not rely on CI to catch a squat.

---

## 4. The `hacs/default` submission

### 4.1 Who may submit

[`include.md`](https://github.com/hacs/documentation/blob/main/source/docs/publish/include.md):

- "Only the owner or a major contributor of a repository can submit a pull request (PR) to add it as a default." Enforced by [`scripts/check/owner.py`](https://github.com/hacs/default/blob/master/scripts/check/owner.py): the actor must be the owner (case-insensitive) or a contributor with `contributions >= top_contributor/3`.
- Integrations that alpha/beta-test or **override a core integration are not accepted** as defaults.
- There is a publisher blocklist (`REMOVED_PUBLISHERS`) → `"'{owner}' is not allowed to publish default repositories"`.

### 4.2 Preconditions (verbatim from `include.md`)

- Your repository can be added to HACS as a custom repository.
- Your repository is public and hosted on GitHub.
- Add and pass these GitHub Actions:
  - HACS Action — "**Before you submit your PR, this action must pass without any errors or ignores.**"
  - Hassfest (for integrations only)
- "Create a new GitHub release (not just a tag, a full release) **after the actions run successfully**."

The "no ignores" clause is not decorative: the PR template asks for a "Link to successful HACS action (**without the `ignore` key**)".

### 4.3 The PR itself

Add `"Normio/HeatIt-Wifi-Home-Assistant"` to [`integration`](https://github.com/hacs/default/blob/master/integration) — a plain JSON array of `"owner/repo"` strings, no file extension, 2-space indent, **no trailing newline**, matching `^[\w\.-]+\/[\w\.-]+$`.

**Sorting is case-INSENSITIVE.** [`scripts/sort.py`](https://github.com/hacs/default/blob/master/scripts/sort.py):

```python
cat_file.write(json.dumps(sorted(content, key=str.casefold), indent=2))
```

and [`scripts/is_sorted.py`](https://github.com/hacs/default/blob/master/scripts/is_sorted.py) asserts `content == sorted(content, key=str.casefold)` in CI. **Never run a naive `sort` or a JSON formatter over the file** — that produces a several-hundred-line diff and an instant rejection (real example: [#8989](https://github.com/hacs/default/pull/8989), "713 additions and 712 deletions because the whole `integration` catalog was re-sorted from case-insensitive to case-sensitive order").

**The diff must be exactly `+1 / -0` on exactly one file.** A `+1/-1` means you silently deleted somebody else's entry ([#8246](https://github.com/hacs/default/pull/8246): "`+1/-1` on this file is the tell; a store addition should always be `+1/-0`").

Casing must match GitHub's actual repo name exactly — `Normio/HeatIt-Wifi-Home-Assistant`, not lowercased. Eight recent PRs were auto-closed for `**Repository name case mismatch.**`

Rules from `include.md`:

- Insert **alphabetically** (case-insensitively), not at the end.
- Fork must branch from `master`; **do not PR from your fork's `master`** — 55 auto-closes in one month for this alone.
- The PR must be **editable** ("Allow edits from maintainers"). Org-owned forks cannot set this, which is why the docs say don't submit from an organization account.
- "If you did not fill out the pull request template correctly, your PR will be closed without further notice."
- Misrepresenting statements → closed without notice.
- Not owner/major contributor → closed without notice.
- Doesn't meet requirements → **drafted** for minor issues, **closed** for major issues.

### 4.4 The PR template (verbatim)

[`.github/PULL_REQUEST_TEMPLATE.md`](https://github.com/hacs/default/blob/master/.github/PULL_REQUEST_TEMPLATE.md):

```markdown
<!--
DO NOT REQUEST REVIEWS, THAT IS JUST RUDE, IF YOU DO THE PULL REQUEST WILL BE CLOSED!
Make sure to check out the guide here: https://hacs.xyz/docs/publish/start
-->
## Checklist

<!-- Do not open a pull request before you have completed all these, it will be closed. -->

- [ ] I've read the [publishing documentation](https://hacs.xyz/docs/publish/start).
- [ ] I've added the [HACS action](https://hacs.xyz/docs/publish/action) to my repository.
- [ ] (For integrations only) I've added the [hassfest action](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) to my repository.
- [ ] The actions are passing without any disabled checks in my repository.
- [ ] I've added a link to the action run on my repository below in the links section.
- [ ] I've created a new release of the repository after the validation actions were run successfully.

## Links

<!-- Do not open a pull request before you have provided all these, it will be closed. -->

Link to current release: <>
Link to successful HACS action (without the `ignore` key): <>
Link to successful hassfest action (if integration): <>
```

Every box must be `[x]` and, for an integration, **all three links** must be filled — a bot counts them.

### 4.5 What actually runs, and what actually rejects

**`hacs-bot` gates the PR before CI.** On open it validates the checklist, link count, branch, editability, single-file/single-repo diff, and casing. On failure it posts a `CHANGES_REQUESTED` review and **closes the PR immediately**. On pass it renames the PR to `Adds new integration [owner/repo]` and applies the `New default repository` label — which is what unlocks the real checks. **The bot does not re-evaluate after a force-push; a rejected PR must be replaced with a new one.**

**Auto-rejection reasons, by frequency** across ~287 bot reviews on 300 PRs closed 2026-08-09 → 2026-09-07:

| Count | Message (verbatim) |
| ---: | --- |
| 162 | `**Complete all checklist items before submitting.**` |
| 100 | `**Add required repository links to the PR description.** Found N link(s), but 3 are required for integration repositories.` |
| 55 | `**Do not submit PRs from your `master` branch.**` |
| 28 | `**Your branch seems out of date.**` |
| 12 | `**Remove "HACS" from your repository name.**` |
| 11 | `**Limit your PR to a single repository change.**` |
| 8 | `**Repository name case mismatch.**` |
| 6 | `**Allow maintainers to edit this PR.**` |
| 6 | `**Limit your PR to a single file change.**` |
| 1 | `**This author is blocked from publishing to HACS.**` |

Our repo name, `HeatIt-Wifi-Home-Assistant`, contains no "HACS" — fine.

**CI jobs** ([`checks.yml`](https://github.com/hacs/default/blob/master/.github/workflows/checks.yml), gated on the `New default repository` label):

| Job | Enforces |
| --- | --- |
| Preflight | Exactly one category file and exactly one new repo changed. |
| Owner | Owner, or contributor ≥ ⅓ of top contributor; not in `REMOVED_PUBLISHERS`. |
| Editable PR | `maintainer_can_modify` is true. |
| Releases | `GET /repos/{repo}/releases` non-empty → else `"'{repo}' has no releases"`. |
| Removed repository | Not in `https://data-v2.hacs.xyz/removed/repositories.json`. |
| Existing repository | Not already in any category at `https://data-v2.hacs.xyz/{category}/repositories.json`. |
| Hassfest | Integration only. Clones the repo and runs `ghcr.io/home-assistant/hassfest:latest` against `custom_components/<domain>`. |
| HACS action | `hacs/action@main` with `repository:` and `category:`, **no `ignore`**. |

Plus [`lint.yml`](https://github.com/hacs/default/blob/master/.github/workflows/lint.yml) on every PR: `jq --raw-output .` over every category file, JSON-schema validation, and `is_sorted.py`.

**Human review is real and deep.** `frenck` reads the integration source against a core checkout. Documented rejections include:

- **Duplicate domain** — [#9077](https://github.com/hacs/default/pull/9077): "both repositories declare the same `"domain"` … Because HACS installs by domain, both would write to `custom_components/…`, so anyone who ended up with both would have one silently overwrite the other." Also [#8920](https://github.com/hacs/default/pull/8920), [#9124](https://github.com/hacs/default/pull/9124), [#7804](https://github.com/hacs/default/pull/7804) (a rebrand-fork of a core integration).
- **Missing LICENSE** — [#9441](https://github.com/hacs/default/pull/9441), [#7959](https://github.com/hacs/default/pull/7959), [#7731](https://github.com/hacs/default/pull/7731): "Please pick a license …, commit the LICENSE file to the repo root, **cut a new release that includes it**, and re-request review."
- **No brand assets** — [#8962](https://github.com/hacs/default/pull/8962): "Since Home Assistant 2026.3 those must ship in-tree under `custom_components/<domain>/brand/` (`icon.png`, `logo.png`, and the `@2x` variants)."
- **Duplicated brand assets** — [#9632](https://github.com/hacs/default/pull/9632): "the brand assets are duplicated, once at the repo-root `brand/` and once under `custom_components/<domain>/brand/`. Only the in-component copy is needed." Also [#9630](https://github.com/hacs/default/pull/9630), a "stray 1.7 MB `icon.png` at the repo root".
- **Codeowners pointing at someone else** (fork submissions) — [#8962](https://github.com/hacs/default/pull/8962), [#8819](https://github.com/hacs/default/pull/8819).
- **Security** — leaking tokens/keys/PII into debug logs ([#9643](https://github.com/hacs/default/pull/9643), [#8989](https://github.com/hacs/default/pull/8989), [#7810](https://github.com/hacs/default/pull/7810)); unauthenticated endpoints ([#9377](https://github.com/hacs/default/pull/9377)); undisclosed telemetry / phone-home ([#8231](https://github.com/hacs/default/pull/8231), [#7809](https://github.com/hacs/default/pull/7809)). [#8968](https://github.com/hacs/default/pull/8968) states the standard: "the default catalog is browsed and installed by ordinary users on a name and a one-line description, and **listing there carries an implicit endorsement**".
- **Not production-ready / thin README** — [#8819](https://github.com/hacs/default/pull/8819): "The README currently describes the integration as an initial, not-production-ready slice pending live-device validation. It's best to submit to the default catalog once it's past that stage."
- **Aggressive polling defaults** — [#9638](https://github.com/hacs/default/pull/9638), a 5-second scan interval.
- **`hacs.json` `homeassistant` floor not matching the APIs actually used** — checked against core (e.g. `entry.runtime_data` → 2024.6).

> **Direct consequence for this map.** The "not production-ready pending live-device validation" rejection is precisely our situation: no hardware, everything derived from the OpenAPI spec. Submitting to `hacs/default` before the conformance checklist has been run against a real panel is a documented rejection pattern. The listing should be sequenced after hardware validation, not before.

### 4.6 Timeline and etiquette

`include.md`: "new additions still take months to be reviewed and included." Observed reality is bimodal — bursty batch merges (~18 h to 5 days when a batch runs) separated by ~month-long gaps, with outliers at 31 and 36 days. **Queue depth on 2026-09-07: 850 open non-draft PRs, 266 drafts.**

The bot's queue comment: "Pull requests are processed in the order they were created, oldest first." What to avoid: commenting on the PR, opening a second PR, asking others to comment, or merging in the default branch unless asked. The template header: "DO NOT REQUEST REVIEWS, THAT IS JUST RUDE, IF YOU DO THE PULL REQUEST WILL BE CLOSED!"

**Stale policy** ([`stale.yml`](https://github.com/hacs/default/blob/master/.github/workflows/stale.yml)): 21 days to stale, 7 more to auto-close — 28 days total. A drafted PR you leave alone dies.

After merge: "It might take up to **8 hours** before your repository appears in HACS for users."

### 4.7 Removal (for completeness)

[`remove.md`](https://github.com/hacs/documentation/blob/main/source/docs/publish/remove.md): archived repos are removed automatically. **Deleting** a repo that is a HACS default permanently bars the maintainer from adding more. Removal is requested via an issue on `hacs/integration`.

---

## 5. Brand assets — the rule that changed in 2026

> **This section overrides most third-party guides, and the ticket's own framing.** The `home-assistant/brands` PR is no longer the route for a new custom integration. It is not merely optional — it is **actively blocked**.

### 5.1 `home-assistant/brands` no longer accepts new custom integrations

[`.github/PULL_REQUEST_TEMPLATE.md`](https://github.com/home-assistant/brands/blob/master/.github/PULL_REQUEST_TEMPLATE.md):

> Pull requests for adding new custom components will no longer be accepted. Please refer to the Brands Proxy API announcement for more details.

There is an enforcement bot, [`.github/workflows/close-new-custom-integrations.yml`](https://github.com/home-assistant/brands/blob/master/.github/workflows/close-new-custom-integrations.yml), on `pull_request_target` for `custom_integrations/**`. It detects folders where every touched file is `added` and auto-comments + auto-closes:

> "we no longer accept brand icons for custom integrations in this repository. Starting with Home Assistant 2026.3.0, custom integrations can provide their own brand icons directly, so there's no longer a need to add them here."

The brands README now labels `custom_integrations` a **"Legacy folder"**. The PR template's "type of change" options are core-only.

**Opening a `custom_integrations/heatit_wifi_panel/` PR would be auto-closed.** Do not do it.

### 5.2 The replacement: ship `brand/` in the integration directory

[HA dev blog, 2026-02-24](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/). Detection in core is directory presence (`homeassistant/loader.py`):

```python
@cached_property
def has_branding(self) -> bool:
    """Return if the integration has brand assets."""
    return "brand" in self._top_level_files
```

Serving is `homeassistant/components/brands/`, `_serve_from_custom_integration()`, reading `Path(integration.file_path) / "brand"`. **Local images take priority over the CDN.**

Allowed filenames (`homeassistant/components/brands/const.py`, `ALLOWED_IMAGES`) — exactly eight:

```python
ALLOWED_IMAGES: Final = frozenset({
    "icon.png", "logo.png", "icon@2x.png", "logo@2x.png",
    "dark_icon.png", "dark_logo.png", "dark_icon@2x.png", "dark_logo@2x.png",
})
```

with fallbacks `logo.png → icon.png`, `icon@2x.png → icon.png`, `logo@2x.png → logo.png → icon.png`, `dark_* → light equivalent`.

The HACS check ([`validate/brands.py`](https://github.com/hacs/integration/blob/main/custom_components/hacs/validate/brands.py)) looks for `custom_components/<domain>/brand/icon.png` in the **git tree**; only if absent does it fall back to requiring the domain in the `custom` map of `https://brands.home-assistant.io/domains.json` — a map now effectively frozen for new entries. Only `icon.png` is required to pass.

### 5.3 The catch: an in-tree brand only renders on HA ≥ 2026.3

Because the brands repo is closed to us and the in-tree mechanism landed in 2026.3, our icon will simply not appear for users on older Home Assistant. `frenck` checks `hacs.json`'s `homeassistant` floor against the APIs actually used, so setting `"homeassistant": "2026.3.0"` is both honest and self-consistent. Anything lower means shipping an integration with no icon on part of its supported range — defensible, but a deliberate choice, not an oversight.

### 5.4 Image specification

hassfest performs **no validation whatsoever** of a custom integration's `brand/` directory — `brand.py` is core-only, gated behind `if config.specific_integrations: return`. Nothing in CI will catch a badly-sized icon. Match the brands repo's published spec anyway; it is what the HA frontend expects and what a reviewer will eyeball.

From [`home-assistant/brands` README](https://github.com/home-assistant/brands/blob/master/README.md) and its enforcing [`validate.sh`](https://github.com/home-assistant/brands/blob/master/.github/workflows/validate/validate.sh):

- PNG only. Properly compressed and optimised, lossless preferred, interlaced/progressive preferred.
- Transparency preferred; images optimised for a white background, with dark-optimised variants prefixed `dark_`.
- "The image should be trimmed, so it contains the minimum amount of empty space on the edges."
- **Icon: aspect ratio exactly 1:1. `icon.png` = 256×256. `icon@2x.png` = 512×512.** (Exact dimension checks in `validate.sh`.)
- **Logo:** landscape preferred, brand's own aspect ratio; shortest side ≥128 and ≤256 for `logo.png`, ≥256 and ≤512 for `logo@2x.png`.
- If the logo is the same square mark as the icon, **ship only the icon files** — the icon is the logo fallback. `validate.sh` errors if `logo.png` is byte-identical to `icon.png`, or a `dark_` variant identical to its light one, or an `@2x` identical to its 1x.
- Any `@2x` file requires its non-`@2x` sibling.
- **"Custom integrations must not use Home Assistant branded images"** — no HA logo, ever.

Practical instruction: put the four files under `custom_components/heatit_wifi_panel/brand/` and **nowhere else**. A repo-root `brand/` or a stray root `icon.png` is a documented review comment ([#9632](https://github.com/hacs/default/pull/9632), [#9630](https://github.com/hacs/default/pull/9630)).

### 5.5 Trademark

The Heatit mark is third-party. `core_brands/heatit/` and `custom_integrations/heatit_wifi6/` set the precedent inside `home-assistant/brands` for identifying-use of the vendor mark. Use the vendor's actual mark at the correct size, not a redraw, and never anything HA-branded.

### 5.6 If this integration ever goes to core

Dev docs: *"If a custom integration will be contributed to Home Assistant Core, be sure to remove the local brand images and open a PR to add them to the brands repository instead."* Core integrations go under `core_integrations/<domain>/`, and `homeassistant/brands/heatit.json` would gain `"integrations": ["heatit_wifi_panel"]`. That brands PR **is** accepted, because it is a core integration.

---

## 6. Release mechanics

### 6.1 The tag is HACS's version of record

[`repositories/base.py` → `version_to_download()`](https://github.com/hacs/integration/blob/main/custom_components/hacs/repositories/base.py):

```python
def version_to_download(self) -> str:
    if self.force_branch and self.ref is not None:
        return self.ref
    if self.data.last_version is not None:
        if self.data.selected_tag is not None:
            if self.data.selected_tag == self.data.last_version:
                self.data.selected_tag = None
                return self.data.last_version
            return self.data.selected_tag
        return self.data.last_version
    ...
    return self.data.default_branch or "main"
```

`data.last_version` is the tag name of the **first non-draft, non-prerelease release** found while walking up to 30 releases. `pending_update` compares release tags. `data.installed_version` is set to the tag installed.

So: **the git tag is what HACS shows and compares. `manifest.json`'s `version` is what Home Assistant displays and what the loader validates. HACS never reads the manifest version to decide anything.**

**Keep them in lockstep.** The release process must stamp `manifest.json`'s `version` from the tag, or CI must assert equality. A release tagged `v1.2.0` shipping a manifest that still says `1.1.0` produces a permanently wrong version in HA's UI and confusing bug reports. This is the classic HACS footgun.

Convention: tag `v1.2.0`, manifest `1.2.0`. AwesomeVersion tolerates the `v`; pick one form and never change it.

### 6.2 What HACS downloads — no release assets needed

Default path, `download_content` → `download_repository_zip` (`repositories/base.py`): HACS fetches GitHub's **auto-generated source archive** for the ref (`…/archive/refs/tags/<ref>.zip`, falling back to `refs/heads/`), then extracts only members under `custom_components/<dir>/`, stripping that prefix, into `<config>/custom_components/<domain>/`:

```python
filename = "/".join(path.filename.split("/")[1:])   # drop the "<repo>-<ref>/" root
if filename.startswith(self.content.path.remote) and filename != self.content.path.remote:
    ...
zip_file.extractall(self.content.path.local, extractable)
```

If that fails it falls back to per-file downloads. The FAQ describes the user-visible effect: delete the local target directory, recreate it, download all expected files ([`faq/download.md`](https://github.com/hacs/documentation/blob/main/source/docs/faq/download.md)).

Confirmed by the HACS Action's own test snapshots — `no_releases.log` and `releases_without_assets.log` both end in `All (9) checks passed` ([`tests/snapshots/action/test_hacs_action_integration/`](https://github.com/hacs/integration/tree/main/tests/snapshots/action/test_hacs_action_integration)).

### 6.3 `zip_release` — do not use it

With `zip_release: true` + `filename: x.zip`, HACS downloads that named **release asset** and `extractall`s it directly into `<config>/custom_components/<domain>/`, so the zip must contain the integration's files at *its* root (no `custom_components/<domain>/` prefix). `should_try_releases` additionally requires `filename.endswith(".zip")` and `ref != default_branch`.

It is real and HACS itself uses it, but for us it adds a build step that can silently produce a broken release (nothing validates the zip's internal layout), and a missing or misnamed asset installs nothing. **Decision: leave `zip_release` unset.**

### 6.4 Pre-releases

`common_update_data` calls `get_releases(prerelease=True, returnlimit=30)`; draft releases are skipped outright (`if release.draft or (release.prerelease and not prerelease): continue`). The newest prerelease tag lands in `data.prerelease` and is only *offered* to users who enable "show beta"; everyone else tracks `last_version`.

Two consequences: marking a GitHub release "pre-release" is a safe way to ship betas, and the lookback is **30 releases** — publishing more than 30 consecutive pre-releases without a stable pushes the last stable out of the window.

### 6.5 The `homeassistant` floor only works with releases

```python
@property
def can_download(self) -> bool:
    if self.repository_manifest.homeassistant is not None:
        if self.data.releases:
            if not version_left_higher_or_equal_then_right(
                self.hacs.core.ha_version.string,
                self.repository_manifest.homeassistant,
            ):
                return False
    return True
```

Note the `if self.data.releases` guard. A repo with no releases has no minimum-HA gate at all — another reason to publish releases from day one, and to set `hide_default_branch: true` so users cannot bypass the gate by installing `main`.

### 6.6 Per-release checklist

- [ ] `manifest.json` `version` bumped and equal to the tag (minus any `v`).
- [ ] `LICENSE` and `brand/` are present **in the tagged tree** (a release without them is a documented rejection).
- [ ] HACS Action and hassfest green on the exact commit being tagged.
- [ ] Publish a **GitHub release**, not just a tag.
- [ ] Pre-release flag for betas; unflagged for stable.
- [ ] No release assets required.

---

## 7. Required GitHub Actions

### 7.1 HACS Action

[`hacs/action`](https://github.com/hacs/action/blob/main/action.yml) is a thin Docker wrapper around `ghcr.io/hacs/action:main`, built from `action/Dockerfile` in `hacs/integration`. Inputs: `ignore`, `category` (required), `repository`, `comment`, `github_token`.

**`comment` is dead** — there is no `INPUT_COMMENT` consumer anywhere in `hacs/integration`. Results come out as `::error::` annotations and a `::group::data` JSON block.

The documented workflow, unchanged (no `actions/checkout` needed — everything is fetched over the API, and `permissions: {}` suffices):

```yaml
name: Validate

on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:

permissions: {}

jobs:
  validate-hacs:
    runs-on: "ubuntu-latest"
    steps:
      - name: HACS validation
        uses: "hacs/action@main"
        with:
          category: "integration"
```

The nightly `schedule` matters — it catches HACS changing its rules under us. Pinning (`hacs/action@xx.xx.x`) + Dependabot is the documented alternative to `@main`.

### 7.2 What the HACS Action actually checks

The checks are Python modules in [`custom_components/hacs/validate/`](https://github.com/hacs/integration/tree/main/custom_components/hacs/validate). The ignorable ID is exactly the module filename stem (`ActionValidationBase.slug`). `ValidationManager.async_run_repository_checks` loads them all, filters by category / `INPUT_IGNORE` / fork, runs them concurrently, and `exit(1)`s if any failed.

| Slug | Categories | Runs on fork PR? | Enforces |
| --- | --- | :---: | --- |
| `archived` | all | **no** | Repo is not archived. |
| `brands` | integration | yes | `custom_components/<domain>/brand/icon.png` in the tree, else `domain` in `custom` of `brands.home-assistant.io/domains.json`. |
| `description` | all | **no** | GitHub repo description non-empty. |
| `hacsjson` | all | yes | `hacs.json` exists, parses, matches `HACS_MANIFEST_JSON_SCHEMA`; integrations: `zip_release` without `filename` fails. |
| `images` | plugin, theme | yes | Info file contains a non-badge image. **N/A for us.** |
| `information` | all | yes | One of `readme`, `readme.md`, `info`, `info.md` (case-insensitive). |
| `integration_manifest` | integration | yes | `manifest.json` exists and matches `INTEGRATION_MANIFEST_JSON_SCHEMA` (§3.2). |
| `issues` | all | **no** | GitHub issues enabled. |
| `license` | all | **no** | See below. |
| `topics` | all | **no** | Repo topics non-empty. |

That is the complete list. **`wheels`, `repositorystructure`, `releases` and `dependabot` are not check slugs** — `releases` exists only as a `hacs/default` CI job, and repository-structure failure is an unignorable exception raised before checks run (§3.1).

**The `license` check is undocumented on hacs.xyz** (added 2026-07-04). [`validate/license.py`](https://github.com/hacs/integration/blob/main/custom_components/hacs/validate/license.py) requires GitHub to have detected a licence, with an SPDX id that is neither missing nor `NOASSERTION`, and that is OSI-approved — fast path against a hardcoded set (`Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `CDDL-1.0`, `EPL-2.0`, `GPL-2.0`, `GPL-3.0`, `LGPL-2.1`, `LGPL-3.0`, `MIT`, `MPL-2.0`), else it downloads a pinned SPDX list and checks `isOsiApproved`. Our root `LICENSE` is MIT — compliant. Keep it at the root, in a form GitHub's detector recognises, and make sure it is in every release.

**Fork PRs skip five checks.** `allow_fork = False` on `archived`, `description`, `issues`, `license`, `topics`. The fork-detection logic:

```python
is_pull_from_fork = (
    not os.getenv("INPUT_REPOSITORY")
    and os.getenv("GITHUB_REPOSITORY") != repository.data.full_name
)
```

`hacs/default` passes `repository:` explicitly, so `INPUT_REPOSITORY` is set and **every** check runs there. In our own repo, a PR from a fork skips those five. **A green fork-PR run does not predict the submission run.** The nightly scheduled run — which runs against our own repo — is the truthful signal. There is no other strictness difference; the check bodies are identical.

A successful integration run logs `All (9) checks passed` (all ten minus `images`).

### 7.3 hassfest

[`hassfest/action.yml`](https://github.com/home-assistant/actions/blob/master/hassfest/action.yml) is four lines of shell: add a problem matcher, then `docker run --rm -v ${{ github.workspace }}://github/workspace ghcr.io/home-assistant/hassfest`. **It has no `inputs:` at all** — you cannot pass flags through the composite action. The entrypoint discovers `custom_components/*/manifest.json` (exactly two levels) or a root `manifest.json` and runs:

```
python3 -m script.hassfest --action validate --integration-path /github/workspace/custom_components/<domain>
```

`--requirements` is **not** passed, so `requirements` entries are format-checked only, never resolved or installed.

```yaml
  validate-hassfest:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@v4"
      - uses: "home-assistant/actions/hassfest@master"
```

Unlike the HACS Action, hassfest **does** need a checkout.

What hassfest applies to a custom integration, beyond the manifest schema in §3.2:

- **Skipped entirely**: the `HASS_PLUGINS` set (`core_files`, `device_classes`, `docker`, `mdi_icons`, `mypy_config`, `metadata`, `sensor`) never runs with `--integration-path`. Within `INTEGRATION_PLUGINS`, these bail out via `if config.specific_integrations: return`: `bluetooth`, `application_credentials`, `dhcp`, `mqtt`, `ssdp`, `usb`, `zeroconf`, `labs`, `integration_info`, `brand`, `integration_type`, and the generation half of `config_flow`.
- **Custom-only**: `json` — every `*.json` in the integration must parse.
- **`config_flow: true` requires `config_flow.py`** to exist.
- **Translations**: for custom integrations hassfest validates **both** `strings.json` **and** `translations/en.json` against the full strings schema. Neither is required, but if present it must be schema-valid. A legacy `.translations/` directory is an error.
- **`services.yaml`**: if any `.py` matches `hass.services.(async_)?register` / `async_register_entity_service` / `async_register_admin_service` and there is no `services.yaml`, you get `"Registers services but has no services.yaml"`. Validated against the looser `CUSTOM_INTEGRATION_SERVICES_SCHEMA`; descriptions are looked up in `translations/en.json`, not `strings.json`.
- **`icons.json`**: optional; if present, every icon must be `mdi:*`.
- **Downgraded to warnings for custom**: missing `config_schema`, discovery steps without a unique ID, domain collision with a core integration.
- **`quality_scale.yaml` is never demanded** — `validate_iqs_file()` returns immediately for non-core.

`hacs/default` runs the same container with the same default plugin set, so a green hassfest here means a green hassfest there.

### 7.4 Recommended beyond the two required

Not required by HACS, required by core later, and cheap now: `ruff` (format + lint), `mypy`, and `pytest` with `pytest-homeassistant-custom-component`. See §8.4.

---

## 8. Where HACS and HA core diverge or conflict

### 8.1 Summary

| # | Topic | HACS requires | Core requires | Cost to reconcile |
| --- | --- | --- | --- | --- |
| 1 | `manifest.json` `version` | **Required** (and HA's loader blocks custom integrations without it) | **Must be absent** — core's schema is `PREVENT_EXTRA` and has no `version` field | Trivial: delete one line. |
| 2 | `manifest.json` `issue_tracker` | **Required** | Omitted for built-in integrations | Trivial. |
| 3 | `manifest.json` `documentation` | Any https URL, and hassfest **forbids** a `home-assistant.io/integrations/…` URL for custom | **Must be** `https://www.home-assistant.io/integrations/<domain>` | Trivial, but exactly inverted — see §8.2. |
| 4 | `hacs.json` | **Required** at repo root | Meaningless | Trivial — it just doesn't move. |
| 5 | Directory layout | `custom_components/<domain>/` | `homeassistant/components/<domain>/` | Mechanical move; import paths and test layout change. |
| 6 | Device/API communication | No constraint — the HTTP client may live in the integration | **Must be a third-party library published on PyPI**, pinned in `requirements` | **Expensive to retrofit.** §8.3. |
| 7 | Brand assets | In-tree `brand/icon.png` (the brands repo is closed to us) | `core_integrations/<domain>/` in `home-assistant/brands`, plus listing under `homeassistant/brands/heatit.json` | Delete the local `brand/`, open a brands PR. Cheap, but must not be forgotten. |
| 8 | Scope of first submission | Whole v1 surface is expected | "Limit to a single platform"; exclude diagnostics, custom services, reauth | **Structural.** §8.5. |
| 9 | Tests | None | Bronze: config-flow/setup tests | Retrofitting tests is the usual reason this never happens. |
| 10 | `quality_scale.yaml` | Never demanded | Required for a tiered integration | Cheap if Bronze was the bar all along. |
| 11 | Product eligibility | None | "available for purchase" and "widely available and has a user base" | Outside our control; a core reviewer's judgment. |
| 12 | Licence | OSI-approved, GitHub-detected | Core is Apache-2.0 | MIT here is fine; the core copy is relicensed on contribution. |
| 13 | Releases / tags | The distribution mechanism | Irrelevant — core ships on HA's train | Free. |
| 14 | Unknown manifest keys | Tolerated (`ALLOW_EXTRA`) | Rejected (`PREVENT_EXTRA`) — and hassfest already rejects them for custom too | Free if we never add junk keys. |

### 8.2 The manifest is genuinely two schemas

`documentation` is the sharpest case. hassfest enforces it in both directions:

```python
def custom_documentation_url(value: str) -> str:
    parsed_url = urlparse(value)
    if parsed_url.scheme != DOCUMENTATION_URL_SCHEMA:      # "https"
        raise vol.Invalid("Documentation url is not prefixed with https")
    if value.startswith(_CORE_DOCUMENTATION_BASE):          # https://www.home-assistant.io/integrations
        raise vol.Invalid("Documentation URL should point to the custom integration documentation")
    return value
```

A custom integration **must not** use the core docs URL; a core integration **must**. Combined with `version` (required custom, forbidden core) and `issue_tracker` (required by HACS, omitted for core), **there is no single `manifest.json` valid for both.** The core PR will always carry a small manifest diff. That is normal and cheap — the important thing is not to build tooling that assumes one canonical manifest.

### 8.3 The PyPI-library rule — the expensive one

Core's checklist: *"All API specific code has to be part of a third party library hosted on PyPi"* ([code review checklist](https://developers.home-assistant.io/docs/creating_component_code_review/)), repeated in [Contributing to core](https://developers.home-assistant.io/docs/core/integration/contributing_to_core/). The Bronze [dependency-transparency](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/dependency-transparency/) rule adds: source distributions must exist, the package must be built and published from a **public CI pipeline**, and the PyPI version must correspond to a **tagged release in a public repository**.

HACS imposes nothing here — and hassfest, run without `--requirements`, only format-checks the strings. Most HACS integrations put the device client right inside `custom_components/<domain>/api.py`.

If core is to stay viable, this must be settled **before the spec fixes the module layout**:

- **Option A — separate PyPI package from day one** (e.g. `pyheatit-wifi-panel`), listed in `requirements`. Core-ready immediately. Costs a second repo, a PyPI account, a publish pipeline, and two-artifact version coordination on every change.
- **Option B — vendor now, extract later.** Fastest to v1; the extraction is a real refactor that moves every consumer with it.
- **Option C — vendor now, behind a clean seam.** All device I/O in one package directory (`custom_components/heatit_wifi_panel/api/`) with **zero Home Assistant imports**, so extraction is a `git mv` plus a `pyproject.toml`. This is the cheap middle and the default recommendation.

**This deserves its own decision ticket / ADR.** It is not a HACS requirement; it is the largest single core-viability constraint and it shapes the spec's module layout.

### 8.4 Quality scale and tests

New core integrations must reach **Bronze** ([quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/)): UI-configurable via config entry, basic coding standards, automated tests for setup, end-user documentation. Tiered integrations carry a `quality_scale.yaml`.

HACS requires none of it, and hassfest explicitly skips `quality_scale.yaml` for custom integrations. But Bronze's rules — `_attr_has_entity_name`, unique IDs, `strings.json` coverage, config-flow test fixtures — are cheap while writing and painful afterwards. The spec should adopt Bronze as its own bar. `"quality_scale": "bronze"` is harmless in the HACS build (HACS `ALLOW_EXTRA`, hassfest accepts the key).

### 8.5 Submission scope

The map's decision is a **full v1 entity surface** across seven platforms. Core's guidance for a *new* integration PR is the opposite: single platform, no diagnostics, no custom services, no reauth, defer the harder quality-scale rules.

These do not conflict for the HACS deliverable — they mean a future core submission would be a deliberately *reduced* first PR with the rest following. Worth recording in the spec so "core viable" is never later misread as "core-submittable as-is".

### 8.6 What does *not* conflict

- `custom_components/<domain>/` is a superset of core's layout; nothing has to be undone.
- Extra manifest keys (`iot_class`, `integration_type`, `config_flow`, `single_config_entry`, `quality_scale`) are accepted by HACS and hassfest and expected by core. Fill them in now.
- `strings.json` / translations are unconstrained by HACS (though hassfest validates them if present) and required by core. Write them from the start.
- `services.yaml` is validated by hassfest for custom integrations too, on a *looser* schema than core's. Writing it core-style now costs nothing.
- Releases, tags and `hacs.json` simply become irrelevant on the core side; this repo continues as the HACS distribution.

---

## 9. Actionable checklists

### 9.1 Repo settings (GitHub UI — do early)

- [ ] Repository **public**.
- [ ] **Description** set, non-empty, one line (shown in HACS).
- [ ] **Topics** set — e.g. `home-assistant`, `homeassistant`, `hacs`, `custom-component`, `heatit`, `climate`, `thermostat`.
- [ ] **Issues enabled**.
- [ ] Not archived.
- [ ] Repo name contains no "HACS" — `HeatIt-Wifi-Home-Assistant` is fine.
- [ ] `LICENSE` at root, MIT, and GitHub's sidebar reads "MIT license".

### 9.2 Repo contents

- [ ] `README.md` at root with substantive docs: setup, entities, services, limitations — not two lines. Include a [My Home Assistant link](https://my.home-assistant.io/create-link/?redirect=hacs_repository).
- [ ] `hacs.json` at root — `name` required, no unknown keys (§2.1).
- [ ] Exactly one directory under `custom_components/`, named `heatit_wifi_panel`.
- [ ] `manifest.json` with the HACS six + `iot_class`, keys sorted `domain`, `name`, then alphabetical (§3.2).
- [ ] `domain` equals the directory name.
- [ ] `version` present and SemVer.
- [ ] `documentation` is https and **not** a `home-assistant.io/integrations/…` URL.
- [ ] `custom_components/heatit_wifi_panel/brand/icon.png` (256×256 PNG, trimmed, transparent) — plus `icon@2x.png` (512×512), and `logo*.png` only if the logo genuinely differs from the icon.
- [ ] **No** `brand/` or `icon.png` anywhere else in the repo.
- [ ] No Home Assistant branding in any asset.

### 9.3 CI

- [ ] `.github/workflows/validate.yml`: HACS Action with `category: integration`, on `push` + `pull_request` + nightly `schedule` + `workflow_dispatch`, `permissions: {}`.
- [ ] Second job: `actions/checkout` + `home-assistant/actions/hassfest@master`.
- [ ] **No `ignore:` input** anywhere.
- [ ] Confirm the **nightly (non-fork) run** is green — fork PR runs skip five checks (§7.2).
- [ ] A check asserting `manifest.json` `version` == release tag (§6.1).
- [ ] Recommended: ruff, mypy, pytest + `pytest-homeassistant-custom-component`.

### 9.4 First release

- [ ] 9.1–9.3 all done, both actions green on the commit to be tagged.
- [ ] `LICENSE` and `brand/` present in the tagged tree.
- [ ] Publish a **GitHub release** (e.g. `v1.0.0`) with manifest `version` = `1.0.0`.

### 9.5 `hacs/default` PR

- [ ] Verify the domain is still unique: `https://data-v2.hacs.xyz/integration/data.json`.
- [ ] Fork `hacs/default` **to a personal account** (not an org).
- [ ] Branch off `master`; do **not** PR from `master`.
- [ ] Enable "Allow edits from maintainers".
- [ ] Add `"Normio/HeatIt-Wifi-Home-Assistant"` — exact GitHub casing — to `integration`, in **case-insensitive** alphabetical position.
- [ ] Diff is exactly `+1 / -0` on exactly one file. No reformatting, no re-sorting, no trailing newline change, no leading space inside the quotes.
- [ ] Branch up to date with `master`.
- [ ] Every template checkbox `[x]`; all **three** links filled (release, HACS action run, hassfest run).
- [ ] Open it, then leave it alone. Do not request reviews. Do not open a second PR.
- [ ] Watch for a draft/changes-requested state — 28 days of silence auto-closes it.
- [ ] Note: a rejected PR cannot be fixed by force-push; the bot does not re-evaluate. Open a fresh one.

### 9.6 Do NOT

- [ ] Do **not** open a `home-assistant/brands` PR for `custom_integrations/heatit_wifi_panel` — an enforcement bot auto-closes it (§5.1).
- [ ] Do **not** set `zip_release`, `content_in_root`, `country`, or `persistent_directory`.
- [ ] Do **not** run a formatter or sorter over `hacs/default`'s `integration` file.

---

## 10. Must be decided or done *early*

Retrofitting any of these is disproportionately painful:

1. **The domain string is permanent.** `heatit_wifi_panel` becomes the install path, the entity-id prefix, the brand directory name and the `hacs/default` identity. It is verified free today (§3.4). Changing it post-listing means a new default entry and orphaned installs.
2. **The PyPI-library decision (§8.3).** It determines the spec's module layout. Decide before the spec fixes file structure.
3. **Version/tag lockstep (§6.1).** Add the CI assertion at the same time as the first release workflow, not after the first mismatch.
4. **Releases + `hide_default_branch` from day one.** The `homeassistant` minimum-version gate does not exist for repos without releases (§6.5), and users installing `main` bypass it.
5. **The `homeassistant` floor vs. brand rendering (§5.3).** In-tree brands only render on HA ≥ 2026.3. Decide whether to set the floor there or accept a missing icon on older installs — and know that a reviewer checks this claim against the APIs used.
6. **Tests and `strings.json`.** Not HACS requirements at all; the two Bronze items that are near-impossible to retrofit cheaply.
7. **Sequencing the submission after hardware validation.** "Not production-ready pending live-device validation" is a documented `hacs/default` rejection (§4.5), and it describes this project's current state exactly.

---

## 11. Out of scope / non-requirements

Things a naive reading of the ticket might have us build, that are genuinely not needed:

- **A `home-assistant/brands` PR.** Actively blocked for new custom integrations (§5.1). This was the ticket's assumption and it is no longer true.
- **Release assets / zips.** HACS downloads the source archive of the tag. `zip_release` is opt-in and we should not opt in (§6.3).
- **The `images` check.** Plugins and themes only.
- **`country`.** Only for region-locked repos; setting it would hide us from most users.
- **`content_in_root`.** Only for repos not using `custom_components/`; it would break the core-compatible layout.
- **`persistent_directory`.** We keep no user files inside the integration directory.
- **A `hacs` minimum-version key.** Nothing we use needs a recent HACS.
- **An `info.md`.** `README.md` satisfies the `information` check.
- **`quality_scale.yaml`.** Never demanded of a custom integration — worth adding only as core preparation.
- **Any repo-age requirement.** None exists in the docs or in `hacs/default`'s scripts.
- **`netdaemon`.** A category file exists in `hacs/default` but is irrelevant to us.

---

## 12. Open questions for follow-up tickets

1. **Separate PyPI client library, yes or no?** (§8.3) — the one decision that changes the spec's module layout. Recommend an ADR.
2. **What `homeassistant` floor do we commit to?** (§5.3, §6.5) — interacts with brand rendering, with the HA APIs the spec is allowed to use, and with reviewer scrutiny.
3. **When do we submit to `hacs/default`?** (§4.5) — before or after live-device conformance. The evidence says after.
4. **Release automation shape** — who bumps `manifest.json`, and how the tag/manifest assertion is wired. Small, but it belongs in the "release & CI hygiene" fog the map already names.
