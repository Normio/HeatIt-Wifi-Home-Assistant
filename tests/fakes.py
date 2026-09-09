"""Builders for synthesised fixtures, derived from observed bytes (§8.3).

Off mode, a dropped parameter, an unknown key, a ``null`` — nobody is turning
on a bedroom heater to capture these. They are produced here by mutating an
observed fixture: parse the reference bytes, change the named paths, re-encode.
Every unobserved part of a synthesised status is therefore real, and no
synthesised fixture may introduce a field no observed fixture contains.

The fake client itself joins this module with the coordinator ticket.
"""

import json
from typing import TYPE_CHECKING, Any

from tests.conftest import SYNTHESISED_DIR

if TYPE_CHECKING:
    from collections.abc import Mapping

ABSENT = object()
"""Set a path to this to drop it from the synthesised status."""


def mutated(raw: bytes, changes: Mapping[str, object]) -> bytes:
    """Derive a status from observed bytes by setting or dropping dotted paths.

    An intermediate object that does not exist is created, so a nested key can
    be introduced — only ever for a test of *unknown keys are ignored*.
    """
    document: dict[str, Any] = json.loads(raw.decode("utf-8"))
    for path, value in changes.items():
        *parents, key = path.split(".")
        node = document
        for parent in parents:
            node = node.setdefault(parent, {})
        if value is ABSENT:
            node.pop(key, None)
        else:
            node[key] = value
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def synthesised(name: str) -> bytes:
    """Load a transcribed write-path response from ``fixtures/synthesised/``."""
    return (SYNTHESISED_DIR / name).read_bytes()


def synthesised_manifest() -> dict[str, dict[str, Any]]:
    """Load what each synthesised file is, and what it was transcribed from."""
    manifest = json.loads((SYNTHESISED_DIR / "manifest.json").read_text("utf-8"))
    files: dict[str, dict[str, Any]] = manifest["files"]
    return files
