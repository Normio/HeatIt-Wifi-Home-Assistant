---
status: accepted
---

# Tag push is the release trigger, behind a gate that fails closed

HACS reads the GitHub release tag as the version of record. It never reads `manifest.json`. Home Assistant reads the `version` in `manifest.json` and never reads the tag. Nothing binds the two, so they can drift without anyone noticing. And once the first release exists, the tag form is fixed for the life of the repository, because HACS compares tag strings.

We decided that **pushing a `vX.Y.Z` tag is the only way a release is created**. `release.yml` runs on the tag. It re-runs every validator and the test suite on that exact commit. It checks that the tag equals the manifest version and that the tagged commit is on `main`. Only then does it create the GitHub release. A failed gate leaves a bare tag, which HACS ignores. It never deletes anything. Tags are SemVer with a `v` prefix (`v0.1.0`). Manifests carry the bare number (`0.1.0`). That form never changes.

## Considered Options

- **`workflow_dispatch` that bumps, commits, tags and releases.** This guarantees lockstep, because CI writes both values. But it needs write access to `main` and a branch-protection bypass, and it lands bot commits outside review.
- **release-please.** This generates the release PR from conventional commits. It is the strongest automation. But it forces a commit-message discipline on every agent session, and it adds a third-party action to trust for the one operation that cannot be undone.

## Consequences

- The manifest bump and the changelog section land on `main` through an ordinary reviewed PR. The tag is pushed afterwards, by the owner only. A tag ruleset on `v*` enforces this.
- A mismatch is fixed by deleting the tag, bumping, and retagging. No workflow is ever allowed to delete a tag.
- A release cannot exist without `LICENSE`, `brand/icon.png`, a `hacs.json` that carries `hide_default_branch: true` and a `homeassistant` floor, and a non-empty `CHANGELOG.md` section for its version. The gate checks for each.
