"""The release gate's lockstep script: every failure mode red, the clean case green.

Each test builds a throwaway repository with ``main`` and a tag, breaks one
invariant, and asserts the script names exactly that problem.
"""

import json
import subprocess
from typing import TYPE_CHECKING

import check_release
import pytest

if TYPE_CHECKING:
    from pathlib import Path

TAG = "v0.1.0"
VERSION = "0.1.0"
CHANGELOG = """\
# Changelog

## [Unreleased]

## [0.1.0] - 2026-09-09

### Added

- The first release.

[Unreleased]: https://example.invalid/compare/v0.1.0...HEAD
[0.1.0]: https://example.invalid/releases/tag/v0.1.0
"""

#: A 0.x README: the custom-repository route, and nothing else.
README = """\
# x

## Installation

Open HACS, then **Custom repositories**, and add this repository's URL with
the category *Integration*.

## Verified firmware
"""

#: What v1.0.0 rewrites it to, once the repository is in the default store.
DEFAULT_STORE_README = """\
# x

## Installation

Open HACS, search for *Heatit WiFi Panel*, and download it.

## Verified firmware
"""


def git(root: Path, *args: str) -> str:
    """Run git in the throwaway repository with a fixed identity."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *args],  # noqa: S607
        capture_output=True,
        check=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "HOME": str(root),
            "PATH": "/usr/bin:/bin",
        },
    ).stdout


def write(root: Path, name: str, content: str | bytes) -> None:
    """Write one file under the repository root, creating parents."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build a repository whose ``main`` tip is tagged and passes the gate."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main")
    write(root, "LICENSE", "MIT\n")
    write(
        root,
        "hacs.json",
        json.dumps(
            {
                "name": "x",
                "homeassistant": "2026.3.1",
                "hide_default_branch": True,
            }
        ),
    )
    write(
        root,
        "custom_components/heatit_wifi_panel/manifest.json",
        json.dumps({"domain": "heatit_wifi_panel", "version": VERSION}),
    )
    write(root, "custom_components/heatit_wifi_panel/brand/icon.png", b"png")
    write(root, "CHANGELOG.md", CHANGELOG)
    write(root, "README.md", README)
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--message", "release")
    git(root, "tag", TAG)
    return root


def problems(root: Path, tag: str = TAG, main_ref: str = "main") -> list[str]:
    """Run the gate and return only its problem lines."""
    return check_release.check_release(root, tag, main_ref).problems


def test_clean_tree_passes_and_yields_the_section(repo: Path) -> None:
    """The fixture repository is exactly a releasable one; the notes are the section."""
    result = check_release.check_release(repo, TAG, "main")
    assert result.problems == []
    assert result.notes == "### Added\n\n- The first release.\n"


@pytest.mark.parametrize("tag", ["0.1.0", "v0.1", "v0.1.0-rc1", "release-1"])
def test_tag_must_be_v_prefixed_semver(repo: Path, tag: str) -> None:
    """Anything but ``vX.Y.Z`` is refused before any other check runs."""
    git(repo, "tag", tag)
    found = problems(repo, tag)
    assert len(found) == 1
    assert "vX.Y.Z" in found[0]


def test_tag_must_equal_manifest_version(repo: Path) -> None:
    """The manifest is the single source of the version; the tag must repeat it."""
    git(repo, "tag", "v0.2.0")
    found = problems(repo, "v0.2.0")
    assert any("manifest.json" in p and "0.1.0" in p and "0.2.0" in p for p in found)


def test_tag_must_exist(repo: Path) -> None:
    """A tag the checkout does not hold cannot be verified, so it fails."""
    found = problems(repo, "v0.1.1")
    assert any("not a tag in this checkout" in p for p in found)


def test_tagged_commit_must_be_an_ancestor_of_main(repo: Path) -> None:
    """A tag on a side branch, even a releasable one, never becomes a release."""
    git(repo, "checkout", "--quiet", "-b", "side")
    write(repo, "note.txt", "side branch\n")
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--message", "side")
    git(repo, "tag", "--force", TAG)
    found = problems(repo)
    assert found == [f"{TAG}: the tagged commit is not an ancestor of main"]


def test_main_ref_must_resolve(repo: Path) -> None:
    """A gate that cannot see main cannot answer, and says so rather than passing."""
    found = problems(repo, main_ref="origin/main")
    assert found == ["origin/main: does not resolve to a commit"]


@pytest.mark.parametrize(
    "name",
    [
        "LICENSE",
        "hacs.json",
        "custom_components/heatit_wifi_panel/manifest.json",
        "custom_components/heatit_wifi_panel/brand/icon.png",
        "README.md",
    ],
)
def test_required_files_must_exist(repo: Path, name: str) -> None:
    """Each file the release depends on is asserted present, by name."""
    (repo / name).unlink()
    assert f"{name}: missing" in problems(repo)


def retag(root: Path, version: str) -> str:
    """Bump the manifest and the changelog to ``version`` and tag the result."""
    write(
        root,
        "custom_components/heatit_wifi_panel/manifest.json",
        json.dumps({"domain": "heatit_wifi_panel", "version": version}),
    )
    write(root, "CHANGELOG.md", CHANGELOG.replace(VERSION, version))
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--message", version)
    tag = f"v{version}"
    git(root, "tag", tag)
    return tag


def test_a_release_readme_must_carry_an_install_section(repo: Path) -> None:
    """§11.3 defers the install docs to v0.1.0; the gate stops them slipping past."""
    write(repo, "README.md", "# x\n")
    found = problems(repo)
    assert any("no '## Installation' section" in p for p in found)


def test_a_0_x_release_installs_from_a_custom_repository(repo: Path) -> None:
    """Before the default-store listing that dialog is the only route there is."""
    write(repo, "README.md", DEFAULT_STORE_README)
    found = problems(repo)
    assert any("Custom repositories" in p and "only route" in p for p in found)


def test_the_install_heading_is_installation_and_nothing_else(repo: Path) -> None:
    """Every problem line and the runbook name one heading; so does the regex."""
    write(repo, "README.md", README.replace("## Installation", "## Installing"))
    found = problems(repo)
    assert any("no '## Installation' section" in p for p in found)


def test_the_install_section_offers_no_manual_copy_route(repo: Path) -> None:
    """A copy into custom_components/ bypasses the floor gate, at every version."""
    write(
        repo,
        "README.md",
        README.replace(
            "the category *Integration*.",
            "the category *Integration*. Or copy custom_components/x into config.",
        ),
    )
    found = problems(repo)
    assert any("manual copy" in p for p in found)


def test_v1_0_0_drops_the_custom_repository_route(repo: Path) -> None:
    """HACS refuses a custom-repository entry for a repository already in the store."""
    tag = retag(repo, "1.0.0")
    found = problems(repo, tag)
    assert any("default store" in p for p in found)


def test_v1_0_0_passes_on_default_store_instructions(repo: Path) -> None:
    """The rewrite §11.3 requires is the one the gate accepts."""
    write(repo, "README.md", DEFAULT_STORE_README)
    tag = retag(repo, "1.0.0")
    assert problems(repo, tag) == []


def test_hacs_json_must_hide_the_default_branch(repo: Path) -> None:
    """Without the flag an install falls back to the default branch."""
    write(repo, "hacs.json", json.dumps({"name": "x", "homeassistant": "2026.3.1"}))
    assert any("hide_default_branch" in p for p in problems(repo))


@pytest.mark.parametrize(
    "floor",
    [None, "", "banana"],
    ids=["absent", "empty", "unparseable"],
)
def test_hacs_json_floor_must_parse(repo: Path, floor: str | None) -> None:
    """The floor gate exists only if HACS can parse the key with AwesomeVersion."""
    document: dict[str, object] = {"name": "x", "hide_default_branch": True}
    if floor is not None:
        document["homeassistant"] = floor
    write(repo, "hacs.json", json.dumps(document))
    assert any("homeassistant" in p for p in problems(repo))


def test_changelog_section_must_exist(repo: Path) -> None:
    """A version with no changelog section has no release notes, so no release."""
    write(repo, "CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n\n- Not yet.\n")
    assert any("## [0.1.0]" in p for p in problems(repo))


@pytest.mark.parametrize(
    "body",
    ["", "[0.1.0]: https://example.invalid\n", "### Added\n\n### Changed\n"],
    ids=["nothing", "link definitions", "sub-headings only"],
)
def test_changelog_section_must_not_be_empty(repo: Path, body: str) -> None:
    """A heading over nothing, link definitions or bare sub-headings is not notes."""
    write(repo, "CHANGELOG.md", f"# Changelog\n\n## [0.1.0] - 2026-09-09\n\n{body}")
    assert any("## [0.1.0]" in p and "empty" in p for p in problems(repo))


def test_changelog_section_ends_at_the_next_heading() -> None:
    """The section runs to the next ``##`` heading, link definitions dropped."""
    text = (
        "## [0.2.0] - 2026-10-01\n\n- Newer.\n\n"
        "## [0.1.0] - 2026-09-09\n\n- Older.\n\n"
        "[0.2.0]: https://example.invalid\n"
    )
    assert check_release.changelog_section(text, "0.2.0") == "- Newer.\n"
    assert check_release.changelog_section(text, "0.1.0") == "- Older.\n"
    assert check_release.changelog_section(text, "0.0.1") is None


def test_main_writes_the_notes_and_exits_zero(repo: Path, tmp_path: Path) -> None:
    """The command-line entry point writes the section where the workflow asked."""
    notes = tmp_path / "notes.md"
    check_release.main(
        [TAG, "--main", "main", "--notes", str(notes), "--root", str(repo)]
    )
    assert notes.read_text(encoding="utf-8") == "### Added\n\n- The first release.\n"


def test_main_exits_non_zero_and_writes_nothing_on_a_problem(
    repo: Path, tmp_path: Path
) -> None:
    """A failed gate leaves no notes behind to be published by mistake."""
    notes = tmp_path / "notes.md"
    (repo / "LICENSE").unlink()
    with pytest.raises(SystemExit) as raised:
        check_release.main(
            [TAG, "--main", "main", "--notes", str(notes), "--root", str(repo)]
        )
    assert raised.value.code != 0
    assert not notes.exists()
