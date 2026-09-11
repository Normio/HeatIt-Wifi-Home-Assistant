"""Assert the repository-layout invariants that nothing upstream enforces.

hassfest validates ``strings.json`` only when the file is present, and the HACS
Action never looks past ``hacs.json`` and the manifest. The parts of the spec
that say what must *not* be in the tree — no ``strings.json``, brand assets in
one place, ``hacs.json`` holding exactly three keys — are therefore checked
here or nowhere. The manifest's other absence, a ``quality_scale`` key, is
``scripts/check_quality_scale.py``'s to assert, beside the yaml it concerns.

Run from ``scripts/check.sh``. Silent when the tree is clean; otherwise prints
one line per problem and exits non-zero.
"""

import json
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "heatit_wifi_panel"
BRAND_DIR = INTEGRATION_DIR / "brand"

#: ``hacs.json`` holds these and nothing else — the schema rejects unknown keys.
HACS_JSON_KEYS = frozenset({"name", "homeassistant", "hide_default_branch"})

#: The manifest's fixed keys, in their fixed order: domain, name, then
#: alphabetical. A key added or dropped here is a deliberate edit, not a drift.
MANIFEST_KEYS = [
    "domain",
    "name",
    "codeowners",
    "config_flow",
    "dhcp",
    "documentation",
    "import_executor",
    "integration_type",
    "iot_class",
    "issue_tracker",
    "requirements",
    "version",
]

#: The brand assets, and the square edge each must have.
BRAND_ICONS = {"icon.png": 256, "icon@2x.png": 512}

#: A logo is rejected by the brands validator when it is byte-identical to the
#: icon, and no dark variant is shipped. Neither may appear anywhere.
FORBIDDEN_IMAGE_PREFIXES = ("logo", "dark_")
IMAGE_SUFFIXES = frozenset({".png", ".svg", ".jpg", ".jpeg", ".webp"})

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: Offset of the end of the IHDR width and height fields, which begin at 16.
IHDR_DIMENSIONS_END = 24


def rel(path: Path) -> str:
    """Render a path the way a problem line names it: relative to the root."""
    return str(path.relative_to(REPO_ROOT))


def tracked_files() -> list[Path]:
    """Return every file git tracks — the definition of "in the repository".

    Asking git rather than walking the tree keeps an untracked virtualenv, with
    a Home Assistant install and its hundreds of ``strings.json``, out of the
    answer, and keeps dot-directories like ``.github`` in it.
    """
    listing = subprocess.run(  # noqa: S603
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],  # noqa: S607
        capture_output=True,
        check=True,
        text=True,
    )
    return [REPO_ROOT / name for name in listing.stdout.split("\0") if name]


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """Return a PNG's pixel dimensions, or ``None`` when it is not a PNG."""
    header = path.read_bytes()[:IHDR_DIMENSIONS_END]
    if len(header) < IHDR_DIMENSIONS_END or not header.startswith(PNG_SIGNATURE):
        return None
    width, height = struct.unpack(">II", header[16:IHDR_DIMENSIONS_END])
    return width, height


def json_document(path: Path) -> dict[str, Any] | None:
    """Return a parsed JSON object, or ``None`` when the file is missing."""
    if not path.is_file():
        return None
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


def check_no_strings_json(files: list[Path]) -> list[str]:
    """Assert no ``strings.json`` exists anywhere in the repository."""
    return [
        f"{rel(path)}: strings.json is never shipped — its [%key:...%] syntax "
        f"is a build-time feature nothing resolves at runtime, so a custom "
        f"integration shipping one shows raw keys. The authored artifact is a "
        f"fully-expanded translations/en.json."
        for path in files
        if path.name == "strings.json"
    ]


def check_brand_assets(files: list[Path]) -> list[str]:
    """Assert the brand assets exist, are the right size, and stand alone."""
    problems = [
        f"{rel(path)}: brand assets live in {rel(BRAND_DIR)} and nowhere else"
        for path in files
        if path.name in BRAND_ICONS and path.parent != BRAND_DIR
    ]
    problems += [
        f"{rel(path)}: no logo* and no dark_* image anywhere — the icon is the "
        f"logo fallback, and a byte-identical logo is rejected"
        for path in files
        if path.name.startswith(FORBIDDEN_IMAGE_PREFIXES)
        and path.suffix.lower() in IMAGE_SUFFIXES
    ]

    for name, edge in BRAND_ICONS.items():
        icon = BRAND_DIR / name
        if not icon.is_file():
            problems.append(f"{rel(icon)}: missing")
            continue
        dimensions = png_dimensions(icon)
        if dimensions is None:
            problems.append(f"{rel(icon)}: not a PNG")
        elif dimensions != (edge, edge):
            problems.append(
                f"{rel(icon)}: is {dimensions[0]}x{dimensions[1]}, "
                f"must be {edge}x{edge}"
            )

    return problems


def check_hacs_json(path: Path) -> list[str]:
    """Assert ``hacs.json`` holds exactly its three keys, with the gate on."""
    hacs = json_document(path)
    if hacs is None:
        return [f"{rel(path)}: missing"]

    problems = []
    if set(hacs) != HACS_JSON_KEYS:
        problems.append(
            f"{rel(path)}: keys are {sorted(hacs)}, must be exactly "
            f"{sorted(HACS_JSON_KEYS)}"
        )
    if hacs.get("hide_default_branch") is not True:
        problems.append(
            f"{rel(path)}: hide_default_branch must be true — without it an "
            f"install falls back to the default branch, past the floor gate"
        )
    return problems


def check_manifest(path: Path) -> list[str]:
    """Assert the manifest's fixed keys and their order.

    A ``quality_scale`` key is skipped rather than named here: it is
    ``check_quality_scale.py``'s failure condition, and one problem should have
    one line.
    """
    manifest = json_document(path)
    if manifest is None:
        return [f"{rel(path)}: missing"]

    keys = [key for key in manifest if key != "quality_scale"]
    if keys != MANIFEST_KEYS:
        return [f"{rel(path)}: keys are {keys}, must be exactly {MANIFEST_KEYS}"]
    return []


def main() -> None:
    """Run every layout check and exit non-zero when any of them speaks."""
    files = tracked_files()
    problems = [
        *check_no_strings_json(files),
        *check_brand_assets(files),
        *check_hacs_json(REPO_ROOT / "hacs.json"),
        *check_manifest(INTEGRATION_DIR / "manifest.json"),
    ]
    if problems:
        sys.exit("\n".join(f"check_layout: {problem}" for problem in problems))


if __name__ == "__main__":
    main()
