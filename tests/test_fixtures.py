"""Fixture hygiene and the three-way firmware consistency (§8.3, §8.5).

Every observed fixture carries exactly the five placeholders, so an unscrubbed
capture cannot merge; and ``VERIFIED_FIRMWARES`` equals the set of observed
directories. The README table joins the assertion with the README ticket.
"""

import json
from typing import TYPE_CHECKING

import pytest

from custom_components.heatit_wifi_panel.api import REDACTED_FIELDS, resolve
from custom_components.heatit_wifi_panel.const import VERIFIED_FIRMWARES
from tests.conftest import REFERENCE_DIR, observed_directories

if TYPE_CHECKING:
    from pathlib import Path

PLACEHOLDERS = {
    "id": "FIXTUREFIXTUREFIXTUREX",
    "Network.mac": "02:00:00:00:00:01",
    "Network.SSID": "SSID-REDACTED",
    "Network.ipAddress": "10.0.0.2",
    "name": "Näytehuone 1",
}

OBSERVED = observed_directories()
OBSERVED_IDS = [path.name for path in OBSERVED]


def test_at_least_one_observed_fixture_exists() -> None:
    assert REFERENCE_DIR in OBSERVED


def test_verified_firmwares_equals_the_observed_directories() -> None:
    directories = {path.name.removeprefix("fw-") for path in OBSERVED}
    assert directories == set(VERIFIED_FIRMWARES)


def test_the_shared_redaction_scrubs_exactly_four_fields() -> None:
    assert set(REDACTED_FIELDS) == set(PLACEHOLDERS) - {"name"}
    assert all(REDACTED_FIELDS[path] == PLACEHOLDERS[path] for path in REDACTED_FIELDS)


@pytest.mark.parametrize("directory", OBSERVED, ids=OBSERVED_IDS)
def test_fixtures_are_scrubbed(directory: Path) -> None:
    document = json.loads((directory / "status.json").read_bytes().decode("utf-8"))
    assert {path: resolve(document, path) for path in PLACEHOLDERS} == PLACEHOLDERS
    assert resolve(document, "id") != resolve(document, "id").lower()  # type: ignore[union-attr]
    assert len(resolve(document, "id")) == 22  # type: ignore[arg-type]


@pytest.mark.parametrize("directory", OBSERVED, ids=OBSERVED_IDS)
def test_manifest_matches_its_directory_and_status(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    document = json.loads((directory / "status.json").read_bytes().decode("utf-8"))
    assert manifest["firmware"] == directory.name.removeprefix("fw-")
    assert manifest["firmware"] == document["firmware"]
    assert manifest["model"] == document["model"]
    assert manifest["maxLoad"] == document["parameters"]["maxLoad"]
    assert manifest["scrubbed_fields"] == list(PLACEHOLDERS)
    assert manifest["captured_at"]
    assert manifest["capture_script_version"] >= 1


@pytest.mark.parametrize("directory", OBSERVED, ids=OBSERVED_IDS)
def test_headers_are_the_charset_less_content_type(directory: Path) -> None:
    headers = (directory / "status.headers").read_text("utf-8")
    assert "Content-Type: application/json\n" in headers
    assert "charset" not in headers


def test_the_reference_capture_has_a_room_and_two_decimal_energy() -> None:
    raw = (REFERENCE_DIR / "status.json").read_bytes()
    assert json.loads(raw)["room"] != ""
    # The wire says 0.00; a round trip through json.dumps would write 0.0.
    assert b'"totalConsumption":0.00' in raw
