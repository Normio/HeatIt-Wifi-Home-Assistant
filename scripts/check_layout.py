"""Assert the repository-layout invariants that nothing upstream enforces.

hassfest validates ``strings.json`` only when the file is present, and the HACS
Action never looks past ``hacs.json`` and the manifest. The parts of the spec
that say what must *not* be in the tree — no ``strings.json``, brand icons in
one place, ``hacs.json`` holding exactly three keys, no ``quality_scale`` in the
manifest — are therefore checked here or nowhere.

Run from ``scripts/check.sh``. Silent when the tree is clean; otherwise prints
one line per problem and exits non-zero.
"""

import json
import struct
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "heatit_wifi_panel"
BRAND_DIR = INTEGRATION_DIR / "brand"

#: ``hacs.json`` holds these and nothing else — the schema rejects unknown keys.
HACS_JSON_KEYS = frozenset({"name", "homeassistant", "hide_default_branch"})

#: The brand assets, and the square edge each must have.
BRAND_ICONS = {"icon.png": 256, "icon@2x.png": 512}

#: A logo is rejected by the brands validator when it is byte-identical to the
#: icon, and no dark variant is shipped; neither may appear under the package.
FORBIDDEN_BRAND_PREFIXES = ("logo", "dark_")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_HEADER_LENGTH = 24


def repository_files() -> Iterator[Path]:
    """Yield every file in the repository, ignoring dot-directories."""
    for path in REPO_ROOT.rglob("*"):
        if any(part.startswith(".") for part in path.relative_to(REPO_ROOT).parts):
            continue
        if path.is_file():
            yield path


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """Return a PNG's pixel dimensions, or ``None`` when it is not a PNG."""
    header = path.read_bytes()[:PNG_HEADER_LENGTH]
    if len(header) < PNG_HEADER_LENGTH or not header.startswith(PNG_SIGNATURE):
        return None
    width, height = struct.unpack(">II", header[16:PNG_HEADER_LENGTH])
    return width, height


def check_no_strings_json(files: list[Path]) -> list[str]:
    """Assert no ``strings.json`` exists anywhere in the repository."""
    return [
        f"{path.relative_to(REPO_ROOT)}: strings.json is never shipped — its "
        f"[%key:...%] syntax is a build-time feature nothing resolves at "
        f"runtime, so a custom integration shipping one shows raw keys. The "
        f"authored artifact is a fully-expanded translations/en.json."
        for path in files
        if path.name == "strings.json"
    ]


def check_brand_assets(files: list[Path]) -> list[str]:
    """Assert the brand assets exist, are the right size, and stand alone."""
    problems = [
        f"{path.relative_to(REPO_ROOT)}: brand assets live in "
        f"{BRAND_DIR.relative_to(REPO_ROOT)} and nowhere else"
        for path in files
        if path.name in BRAND_ICONS and path.parent != BRAND_DIR
    ]
    problems += [
        f"{path.relative_to(REPO_ROOT)}: no logo* and no dark_* — the icon is "
        f"the logo fallback, and a byte-identical logo is rejected"
        for path in files
        if path.is_relative_to(INTEGRATION_DIR)
        and path.name.startswith(FORBIDDEN_BRAND_PREFIXES)
    ]

    for name, edge in BRAND_ICONS.items():
        icon = BRAND_DIR / name
        if not icon.is_file():
            problems.append(f"{icon.relative_to(REPO_ROOT)}: missing")
            continue
        dimensions = png_dimensions(icon)
        if dimensions is None:
            problems.append(f"{icon.relative_to(REPO_ROOT)}: not a PNG")
        elif dimensions != (edge, edge):
            problems.append(
                f"{icon.relative_to(REPO_ROOT)}: is {dimensions[0]}x"
                f"{dimensions[1]}, must be {edge}x{edge}"
            )

    return problems


def check_hacs_json() -> list[str]:
    """Assert ``hacs.json`` holds exactly its three keys, with the gate on."""
    path = REPO_ROOT / "hacs.json"
    if not path.is_file():
        return [f"{path.relative_to(REPO_ROOT)}: missing"]

    hacs = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    if set(hacs) != HACS_JSON_KEYS:
        problems.append(
            f"hacs.json: keys are {sorted(hacs)}, must be exactly "
            f"{sorted(HACS_JSON_KEYS)}"
        )
    if hacs.get("hide_default_branch") is not True:
        problems.append(
            "hacs.json: hide_default_branch must be true — without it an "
            "install falls back to the default branch, past the floor gate"
        )
    return problems


def check_manifest() -> list[str]:
    """Assert the manifest's key order and the absence of ``quality_scale``."""
    path = INTEGRATION_DIR / "manifest.json"
    if not path.is_file():
        return [f"{path.relative_to(REPO_ROOT)}: missing"]

    manifest = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    if "quality_scale" in manifest:
        problems.append(
            "manifest.json: no quality_scale key — quality_scale.yaml says what "
            "we hold ourselves to, and the manifest makes no claim a reviewer "
            "never graded"
        )

    keys = list(manifest)
    expected = ["domain", "name", *sorted(set(keys) - {"domain", "name"})]
    if keys != expected:
        problems.append(
            f"manifest.json: keys are {keys}, must be domain, name, then "
            f"alphabetical: {expected}"
        )
    return problems


def main() -> None:
    """Run every layout check and exit non-zero on the first problems found."""
    files = list(repository_files())
    problems = [
        *check_no_strings_json(files),
        *check_brand_assets(files),
        *check_hacs_json(),
        *check_manifest(),
    ]
    if problems:
        sys.exit("\n".join(f"check_layout: {problem}" for problem in problems))


if __name__ == "__main__":
    main()
