"""Suite-wide fixtures: the observed directories and the reference capture.

The reference fixture is the observed directory with the newest version. It
is named here by hand. Tests that check state values use it. The parse-only
sweep runs over every observed directory, so a capture from a second panel
extends the suite with no test edits.
"""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
OBSERVED_DIR = FIXTURES_DIR / "observed"
SYNTHESISED_DIR = FIXTURES_DIR / "synthesised"

REFERENCE_FIRMWARE = "1.21"
REFERENCE_DIR = OBSERVED_DIR / f"fw-{REFERENCE_FIRMWARE}"


def observed_directories() -> list[Path]:
    """Return every ``fw-<version>/`` directory a real panel produced."""
    return sorted(path for path in OBSERVED_DIR.glob("fw-*") if path.is_dir())


@pytest.fixture(scope="session")
def reference_status_bytes() -> bytes:
    """Read the reference capture's raw wire bytes: scrubbed, never re-encoded."""
    return (REFERENCE_DIR / "status.json").read_bytes()


@pytest.fixture(scope="session")
def reference_headers() -> dict[str, str]:
    """Read the reference capture's response headers, as received."""
    lines = (REFERENCE_DIR / "status.headers").read_text(encoding="utf-8")
    return {
        name.strip(): value.strip()
        for name, value in (line.split(":", 1) for line in lines.splitlines() if line)
    }
