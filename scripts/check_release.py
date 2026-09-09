"""The release gate's lockstep check (spec §10.2, ADR-0002).

HACS reads the release tag as the version of record and never the manifest;
Home Assistant reads the manifest and never the tag. Nothing upstream binds the
two, so this script does, and it also asserts everything else a release must
not exist without: the tagged commit is on ``main`` (a tag pushed from a side
branch must never become a release), the files HACS and the licence check
depend on are present, ``hacs.json`` keeps the floor gate on, and
``CHANGELOG.md`` carries a non-empty section for the version — which becomes
the release notes.

Run by ``.github/workflows/release.yml`` against the tagged checkout::

    python3 scripts/check_release.py v0.1.0 --main origin/main --notes notes.md

Silent and exit 0 when the tag may become a release, writing the changelog
section to ``--notes``; otherwise one line per problem and exit non-zero,
writing nothing. It never creates, deletes or moves anything.
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from awesomeversion import AwesomeVersion

REPO_ROOT = Path(__file__).resolve().parents[1]

#: A release tag is ``v`` plus a bare SemVer triple, and that form is permanent:
#: HACS compares tag strings, so the first release fixes it for good.
TAG_PATTERN = re.compile(r"^v(\d+\.\d+\.\d+)$")

MANIFEST = Path("custom_components/heatit_wifi_panel/manifest.json")
HACS_JSON = Path("hacs.json")
CHANGELOG = Path("CHANGELOG.md")

#: The files a release cannot exist without: the OSI-licence check, both
#: documents HACS reads, and the icon the brand renders from.
REQUIRED_FILES = (
    Path("LICENSE"),
    HACS_JSON,
    MANIFEST,
    Path("custom_components/heatit_wifi_panel/brand/icon.png"),
)

#: A Keep a Changelog link definition, ``[0.1.0]: https://...``. These trail
#: the file and are not release notes.
LINK_DEFINITION = re.compile(r"^\[[^\]]+\]:\s")


@dataclass
class ReleaseCheck:
    """What the gate found: the problems, and the notes if there were none."""

    problems: list[str] = field(default_factory=list)
    notes: str | None = None


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command in the checkout, never raising on failure."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *args],  # noqa: S607
        capture_output=True,
        check=False,
        text=True,
    )


def json_document(path: Path) -> dict[str, Any] | None:
    """Return a parsed JSON object, or ``None`` when the file is missing."""
    if not path.is_file():
        return None
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


def version_from_tag(tag: str) -> str | None:
    """Return the bare version a ``vX.Y.Z`` tag names, or ``None`` otherwise."""
    match = TAG_PATTERN.match(tag)
    return match.group(1) if match else None


def changelog_section(text: str, version: str) -> str | None:
    """Return the body of ``## [version]``, or ``None`` when there is no such heading.

    The body runs to the next ``##`` heading or the end of the file, with the
    trailing link definitions dropped and surrounding blank lines trimmed. An
    empty string means the heading is there and nothing is under it.
    """
    heading = re.compile(rf"^## \[{re.escape(version)}\](\s|$)")
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if heading.match(line)]
    if not starts:
        return None
    start = starts[0] + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    body = [line for line in lines[start:end] if not LINK_DEFINITION.match(line)]
    section = "\n".join(body).strip()
    return f"{section}\n" if section else ""


def check_required_files(root: Path) -> list[str]:
    """Assert every file the release depends on is in the checkout."""
    return [
        f"{name}: missing" for name in REQUIRED_FILES if not (root / name).is_file()
    ]


def check_manifest_version(root: Path, version: str) -> list[str]:
    """Assert the manifest carries exactly the version the tag names."""
    manifest = json_document(root / MANIFEST)
    if manifest is None:
        return []  # reported by check_required_files
    declared = manifest.get("version")
    if declared != version:
        return [
            (
                f"{MANIFEST}: version is {declared!r}, but the tag names {version!r} — "
                f"the manifest bump lands on main before the tag is pushed"
            )
        ]
    return []


def check_hacs_json(root: Path) -> list[str]:
    """Assert ``hacs.json`` keeps the floor gate on and declares a parseable floor."""
    hacs = json_document(root / HACS_JSON)
    if hacs is None:
        return []  # reported by check_required_files

    problems = []
    if hacs.get("hide_default_branch") is not True:
        problems.append(
            f"{HACS_JSON}: hide_default_branch must be true — without it an "
            f"install falls back to the default branch, past the floor gate"
        )
    floor = hacs.get("homeassistant")
    if not isinstance(floor, str) or not AwesomeVersion(floor).valid:
        problems.append(
            f"{HACS_JSON}: homeassistant is {floor!r}, must be a version "
            f"AwesomeVersion parses — it is the floor HACS enforces"
        )
    return problems


def check_ancestry(root: Path, tag: str, main_ref: str) -> list[str]:
    """Assert the tag exists and its commit is reachable from ``main``."""
    tagged = git(
        root, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"
    )
    if tagged.returncode != 0:
        return [f"{tag}: not a tag in this checkout"]
    main = git(root, "rev-parse", "--verify", "--quiet", f"{main_ref}^{{commit}}")
    if main.returncode != 0:
        return [f"{main_ref}: does not resolve to a commit"]
    ancestry = git(
        root, "merge-base", "--is-ancestor", tagged.stdout.strip(), main.stdout.strip()
    )
    if ancestry.returncode != 0:
        return [f"{tag}: the tagged commit is not an ancestor of {main_ref}"]
    return []


def check_changelog(root: Path, version: str) -> tuple[list[str], str | None]:
    """Assert a non-empty ``## [version]`` section exists, and return its body."""
    path = root / CHANGELOG
    if not path.is_file():
        return [f"{CHANGELOG}: missing"], None
    section = changelog_section(path.read_text(encoding="utf-8"), version)
    if section is None:
        return [
            f"{CHANGELOG}: no '## [{version}]' section — it becomes the release notes"
        ], None
    if not section:
        return [f"{CHANGELOG}: the '## [{version}]' section is empty"], None
    return [], section


def check_release(root: Path, tag: str, main_ref: str) -> ReleaseCheck:
    """Run every gate check for ``tag`` against the checkout at ``root``."""
    version = version_from_tag(tag)
    if version is None:
        return ReleaseCheck(
            problems=[f"{tag}: a release tag is vX.Y.Z, a v-prefixed SemVer triple"]
        )

    problems, notes = check_changelog(root, version)
    result = ReleaseCheck(
        problems=[
            *check_ancestry(root, tag, main_ref),
            *check_manifest_version(root, version),
            *check_required_files(root),
            *check_hacs_json(root),
            *problems,
        ]
    )
    if not result.problems:
        result.notes = notes
    return result


def main(argv: list[str] | None = None) -> None:
    """Parse the command line, run the gate, and write the notes or the problems."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tag", help="the pushed tag, vX.Y.Z")
    parser.add_argument(
        "--main",
        default="origin/main",
        metavar="REF",
        help="the ref the tagged commit must be an ancestor of (default: origin/main)",
    )
    parser.add_argument(
        "--notes",
        type=Path,
        metavar="FILE",
        help="where to write the changelog section when the gate passes",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        metavar="DIR",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    result = check_release(args.root, args.tag, args.main)
    if result.problems:
        sys.exit("\n".join(f"check_release: {problem}" for problem in result.problems))
    if args.notes is not None and result.notes is not None:
        args.notes.write_text(result.notes, encoding="utf-8")


if __name__ == "__main__":
    main()
