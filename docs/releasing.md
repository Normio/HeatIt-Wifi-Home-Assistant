# Releasing

How a version of the integration becomes a GitHub release, what stops it, and
the repository settings the release depends on that no workflow can apply.
Spec §10.2 and §10.3; [ADR-0002](adr/0002-tag-push-release-with-gate.md).

## Cutting a release

Pushing a `vX.Y.Z` tag is the only way a release is created. Nothing else —
no `workflow_dispatch`, no bot, no hand-made release — and the tag form is
permanent because HACS compares tag strings.

1. **The release PR**, reviewed and merged like any other:
   - bump `version` in `custom_components/heatit_wifi_panel/manifest.json` to
     the bare number, `0.1.0`;
   - in `CHANGELOG.md`, rename `## [Unreleased]` to `## [0.1.0] - YYYY-MM-DD`
     and rewrite its entries into final form, then open a fresh, empty
     `## [Unreleased]` above it. That section's body becomes the release notes,
     verbatim.
2. **The tag**, pushed by the owner from the merged commit on `main`:

   ```sh
   git switch main && git pull --ff-only
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. `.github/workflows/release.yml` runs on the tag. When every gate job is
   green, the publish job creates the release with the changelog section as
   its body. When any of them is red, no release exists and the tag stays.

## The gate

Every job runs against the tagged commit, and the publish job `needs` all of:

| Job | What it is |
|---|---|
| Validate | `validate.yml` called whole: HACS Action and hassfest, no `ignore:` |
| Test | `test.yml` called whole: the `Lint` job and both pytest rows, so ruff, mypy, the check scripts and the tests. A job that is `continue-on-error` on pull requests must be off on a tag, or the gate would pass over its failure — `Tests (latest)` guards its own with `&& !startsWith(github.ref, 'refs/tags/')`, and `tests/scripts/test_release_gate.py` fails on any value that is not so guarded |
| Lockstep | `scripts/check_release.py`: the tag names the manifest's version; the tagged commit is an ancestor of `main`; `LICENSE`, `hacs.json`, the manifest and `brand/icon.png` exist; `hacs.json` has `hide_default_branch: true` and an AwesomeVersion-parseable `homeassistant`; `CHANGELOG.md` has a non-empty `## [X.Y.Z]` section |

To rehearse the lockstep half before pushing, from the checkout holding the tag:

```sh
python3 scripts/check_release.py v0.1.0 --main origin/main
```

It is silent when the tag would pass, and prints one line per problem when not.

## When the gate fails

A failed gate **leaves the bare tag** and deletes nothing. HACS ignores tags
without a release, so the bare tag is harmless. Fix the cause on `main`
through a PR, then delete the tag, and retag the new commit:

```sh
git push origin --delete v0.1.0
git tag --delete v0.1.0
git switch main && git pull --ff-only
git tag v0.1.0 && git push origin v0.1.0
```

Only the owner can do this: the `v*` tag ruleset denies creation, update and
deletion to everyone else, the workflows' tokens included. No workflow is ever
given tag deletion.

## Repository settings the release depends on

These live in GitHub's settings, not in the repository, and need an
administrator's token — which the agent sessions do not have (`gh repo edit`
answers 403). They are gate item 5 of the submission gate (spec §11.2).
**All of them were applied and verified through the API on 2026-09-09**; the
commands and the ruleset shapes are here so they can be checked or restored.

**Description and topics** — the nightly HACS checks `description` and
`topics` read them:

```sh
gh repo edit Normio/HeatIt-Wifi-Home-Assistant \
  --description "Home Assistant integration for the Heatit WiFi Panel wall heater (local HTTP API)" \
  --add-topic home-assistant --add-topic hacs --add-topic custom-component \
  --add-topic heatit --add-topic heater --add-topic climate
```

Check with `gh repo view --json description,repositoryTopics`.

**The `v*` tag ruleset** ("Release tags", target `tag`, enforcement `active`):
`refs/tags/v*` restricted for creation, update and deletion, with the
repository's administrators as the only bypass actors. This is what makes
"only the owner may create `v*` tags" true, and what denies every workflow
token tag deletion whatever `permissions:` it declares.

**The `main` ruleset** ("Main", target `branch`): no deletion, no
force-push, changes only through a pull request, and the blocking jobs of
`test.yml`, `validate.yml` and `changelog.yml` required as status checks.
This is the "blocks a merge" half of the linters and validators.

They must now be `Lint`, `Tests (floor)`, `HACS Action`, `hassfest` and
`Changelog entry`. **This is an outstanding manual step.** The ruleset was
written on 2026-09-09 naming `Checks`, the single job #38 has since split into
`Lint`, `Tests (floor)` and `Tests (latest)`; until the owner renames it, every
pull request stays blocked on a job that no longer runs, with every check
green. `Tests (latest)` is deliberately *not* required — it is
`continue-on-error` off a tag, a signal rather than a blocker (§8.7) — and no
workflow token can edit a ruleset, so only the owner can do this.

Check both with:

```sh
gh api repos/Normio/HeatIt-Wifi-Home-Assistant/rulesets --jq '.[] | "\(.name) \(.target) \(.enforcement)"'
```
