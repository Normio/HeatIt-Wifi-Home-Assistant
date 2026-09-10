"""Capture an observed status fixture from a real panel, read-only (§8.1).

Reads ``.local/device.json``, imports the client **directly** — no Home
Assistant boot — performs one ``GET /api/status`` through the real read path,
scrubs the bytes on the way, and writes them under
``tests/fixtures/observed/fw-<firmware>/`` beside the raw response headers and
a manifest. Then it prints a diff against what is committed.

The diff keeps the four fields that move on their own — ``roomTemperature``,
``currentPower``, ``totalConsumption`` and ``Network.wifiSignalStrength`` — in a
separate **live values** block, reported for information and never counted as
drift. A difference outside them is the drift signal.

Read-only by construction: the only request this file can issue is the
client's status read, and ``tests/test_capture_safety.py`` asserts that by
reading this source. It never runs in CI.

Exit codes: ``0`` no drift · ``1`` drift outside the live values · ``2`` the
scrub did not hold, nothing written · ``3`` usage or connectivity.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from custom_components.heatit_wifi_panel.api import (  # noqa: E402
    REDACTED_FIELDS,
    HeatitClient,
    HeatitError,
    redact_status_bytes,
    resolve,
    substitute_string_field,
)

CAPTURE_SCRIPT_VERSION = 1

DEVICE_FILE = REPO_ROOT / ".local" / "device.json"
DEFAULT_PORT = 80
OBSERVED_DIR = REPO_ROOT / "tests" / "fixtures" / "observed"

#: The fixture-only fifth placeholder (§8.3). ``name`` is kept by the shared
#: redaction — it is a label, not an identifier — but a committed fixture
#: should not carry someone's room name. It stays non-ASCII on purpose: this
#: field is the evidence that the charset-less UTF-8 decode is required.
NAME_PLACEHOLDER = "Näytehuone 1"
SCRUBBED_FIELDS: tuple[str, ...] = (*REDACTED_FIELDS, "name")
PLACEHOLDERS: dict[str, str] = {**REDACTED_FIELDS, "name": NAME_PLACEHOLDER}

#: Computed per request and moving on their own (Q54); shown, never drift.
LIVE_VALUES: tuple[str, ...] = (
    "roomTemperature",
    "currentPower",
    "totalConsumption",
    "Network.wifiSignalStrength",
)

#: Follows the body, and the body was scrubbed.
VOLATILE_HEADERS = frozenset({"content-length"})

EXIT_DRIFT = 1
EXIT_SCRUB_FAILED = 2
EXIT_USAGE = 3


def say(line: str) -> None:
    """Print one line of the report."""
    sys.stdout.write(line + "\n")


def device_host() -> str:
    """Read the panel's address from the gitignored device pointer."""
    if not DEVICE_FILE.is_file():
        sys.exit(f"{DEVICE_FILE} is missing; copy .local/device.example.json")
    device = json.loads(DEVICE_FILE.read_text(encoding="utf-8"))
    host = str(device["host"])
    port = int(device.get("port", 80))
    return host if port == DEFAULT_PORT else f"{host}:{port}"


async def read_status(host: str) -> tuple[bytes, dict[str, str], str | None]:
    """One status read through the real client; the raw bytes and headers."""
    async with aiohttp.ClientSession() as session:
        client = HeatitClient(host, session=session)
        status = await client.get_status()
    if client.last_raw_body is None or client.last_raw_headers is None:
        msg = "the client retained no raw status"
        raise AssertionError(msg)
    return client.last_raw_body, dict(client.last_raw_headers), status.firmware


def scrub(raw: bytes) -> bytes:
    """Apply the shared four-field scrub, then the fixture-only ``name``."""
    return substitute_string_field(redact_status_bytes(raw), "name", NAME_PLACEHOLDER)


def scrub_problems(scrubbed: bytes) -> list[str]:
    """Every scrubbed field must read exactly its placeholder; else the problems."""
    document = json.loads(scrubbed.decode("utf-8"))
    return [
        f"{path} is {resolve(document, path)!r}, not {placeholder!r}"
        for path, placeholder in PLACEHOLDERS.items()
        if resolve(document, path) != placeholder
    ]


def flatten(node: object, prefix: str = "") -> dict[str, object]:
    """Flatten a JSON document to ``{dotted path: leaf value}``."""
    if not isinstance(node, dict):
        return {prefix: node}
    flat: dict[str, object] = {}
    for key, value in node.items():
        flat.update(flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    return flat


def report_drift(
    committed: bytes | None,
    committed_headers: str | None,
    scrubbed: bytes,
    headers: dict[str, str],
) -> bool:
    """Print the live values and any drift; return whether there was drift."""
    new = flatten(json.loads(scrubbed.decode("utf-8")))
    old = flatten(json.loads(committed.decode("utf-8"))) if committed else {}

    say("## Live values (never drift)")
    for path in LIVE_VALUES:
        was = f"{old[path]!r} -> " if path in old else ""
        say(f"  {path}: {was}{new.get(path)!r}")

    if committed is None:
        say("## No committed fixture to compare against; this capture is new")
        return False

    drift = [
        f"  {path}: {old.get(path, '<absent>')!r} -> {new.get(path, '<absent>')!r}"
        for path in sorted(set(old) | set(new))
        if path not in LIVE_VALUES and old.get(path, ...) != new.get(path, ...)
    ]
    old_headers = {
        line.split(":", 1)[0].strip().lower(): line.split(":", 1)[1].strip()
        for line in (committed_headers or "").splitlines()
        if ":" in line
    }
    new_headers = {k.lower(): v for k, v in headers.items()}
    drift += [
        f"  header {name}: {old_headers.get(name, '<absent>')!r} -> "
        f"{new_headers.get(name, '<absent>')!r}"
        for name in sorted(set(old_headers) | set(new_headers))
        if name not in VOLATILE_HEADERS
        and old_headers.get(name) != new_headers.get(name)
    ]
    if drift:
        say("## Drift outside the live values")
        say("\n".join(drift))
        return True
    say("## No drift outside the live values")
    return False


def manifest(scrubbed: bytes, firmware: str) -> dict[str, Any]:
    """Describe what the fixture is and where it came from."""
    document = json.loads(scrubbed.decode("utf-8"))
    return {
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "firmware": firmware,
        "model": resolve(document, "model"),
        "maxLoad": resolve(document, "parameters.maxLoad"),
        "scrubbed_fields": list(SCRUBBED_FIELDS),
        "capture_script_version": CAPTURE_SCRIPT_VERSION,
    }


def write_fixture(
    directory: Path, scrubbed: bytes, headers: dict[str, str], firmware: str
) -> None:
    """Write the three files: raw scrubbed bytes, raw headers, manifest."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "status.json").write_bytes(scrubbed)
    (directory / "status.headers").write_text(
        "".join(f"{name}: {value}\n" for name, value in headers.items()),
        encoding="utf-8",
    )
    (directory / "manifest.json").write_text(
        json.dumps(manifest(scrubbed, firmware), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Capture, scrub, diff, write."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="diff only; write nothing"
    )
    args = parser.parse_args()

    host = device_host()
    try:
        raw, headers, firmware = asyncio.run(read_status(host))
    except HeatitError as err:
        sys.stderr.write(f"status read failed: {err}\n")
        return EXIT_USAGE
    if firmware is None:
        say("the status carries no firmware; cannot name the directory")
        return EXIT_USAGE

    scrubbed = scrub(raw)
    problems = scrub_problems(scrubbed)
    if problems:
        say("scrub did not hold; nothing written:\n  " + "\n  ".join(problems))
        return EXIT_SCRUB_FAILED

    directory = OBSERVED_DIR / f"fw-{firmware}"
    status_file = directory / "status.json"
    headers_file = directory / "status.headers"
    committed = status_file.read_bytes() if status_file.is_file() else None
    committed_headers = (
        headers_file.read_text(encoding="utf-8") if headers_file.is_file() else None
    )
    room = resolve(json.loads(scrubbed), "room")
    say(f"firmware {firmware}, {len(raw)} bytes, room {room!r}")
    drift = report_drift(committed, committed_headers, scrubbed, headers)

    if args.dry_run:
        say("dry run; nothing written")
    else:
        write_fixture(directory, scrubbed, headers, firmware)
        say(f"wrote {directory.relative_to(REPO_ROOT)}/")
    return EXIT_DRIFT if drift else 0


if __name__ == "__main__":
    sys.exit(main())
