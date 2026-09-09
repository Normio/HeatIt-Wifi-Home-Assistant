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
    ],
)
def test_required_files_must_exist(repo: Path, name: str) -> None:
    """Each file the release depends on is asserted present, by name."""
    (repo / name).unlink()
    assert f"{name}: missing" in problems(repo)


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


def test_changelog_section_must_not_be_empty(repo: Path) -> None:
    """A heading alone, or a heading over link definitions, is not release notes."""
    write(
        repo,
        "CHANGELOG.md",
        "# Changelog\n\n## [0.1.0] - 2026-09-09\n\n[0.1.0]: https://example.invalid\n",
    )
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
