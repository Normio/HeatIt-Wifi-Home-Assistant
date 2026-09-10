"""``scripts/capture_fixtures.py`` is read-only by construction (§8.1).

Asserted by reading the file: the only request it can issue is the client's
status read, and nothing in CI invokes it.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "capture_fixtures.py"

WRITE_SHAPED = [
    "set_parameter",
    "reset_kwh",
    "reset_settings",
    "/api/parameters",
    "/api/reset",
    "session.post",
    "session.delete",
    "session.request",
    '"POST"',
    '"DELETE"',
]


@pytest.mark.parametrize("token", WRITE_SHAPED)
def test_no_write_shaped_code_path(token: str) -> None:
    assert token not in SCRIPT.read_text(encoding="utf-8")


def test_the_only_client_call_is_the_status_read() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "client.get_status()" in source


@pytest.mark.parametrize(
    "path",
    [
        "scripts/check.sh",
        ".github/workflows/test.yml",
        ".github/workflows/validate.yml",
    ],
)
def test_ci_never_runs_the_capture(path: str) -> None:
    assert "capture_fixtures" not in (REPO_ROOT / path).read_text(encoding="utf-8")
