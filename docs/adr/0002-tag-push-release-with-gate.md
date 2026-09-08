---
status: accepted
---

# Tag push is the release trigger, behind a gate that fails closed

HACS reads the GitHub release tag as the version of record and never reads `manifest.json`; Home Assistant reads `manifest.json`'s `version` and never reads the tag. Nothing binds the two, they drift silently, and once the first release exists the tag form is fixed for the life of the repository because HACS compares tag strings. We decided that **pushing a `vX.Y.Z` tag is the only way a release is created**: `release.yml` runs on the tag, re-runs every validator and the test suite on that exact commit, asserts the tag equals the manifest version and that the tagged commit is on `main`, and only then creates the GitHub release. A failed gate leaves a bare tag, which HACS ignores, and never deletes anything. Tags are SemVer with a `v` prefix (`v0.1.0`), manifests carry the bare number (`0.1.0`), and that form never changes.

## Considered Options

- **`workflow_dispatch` that bumps, commits, tags and releases.** Guarantees lockstep because CI writes both values, but needs write access to `main` and a branch-protection bypass, and lands bot commits outside review.
- **release-please.** Generates the release PR from conventional commits. Strongest automation, but imposes a commit-message discipline on every agent session and adds a third-party action to trust for the one operation that cannot be undone.

## Consequences

- The manifest bump and the changelog section land on `main` through an ordinary reviewed PR; the tag is pushed afterwards, by the owner only (a tag ruleset on `v*`).
- A mismatch is fixed by deleting the tag, bumping, and retagging. No workflow is ever granted permission to delete a tag.
- A release cannot exist without `LICENSE`, `brand/icon.png`, a `hacs.json` carrying `hide_default_branch: true` and a `homeassistant` floor, and a non-empty `CHANGELOG.md` section for its version, because the gate checks for each.
