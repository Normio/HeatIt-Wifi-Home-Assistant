"""Status reads and parsing at the HTTP seam, over the observed bytes.

The reference fixture's values are copied here by hand as literals, so the
test compares two independent encodings of what the panel sent.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

import aiohttp
import pytest
from yarl import URL

from custom_components.heatit_wifi_panel.api import (
    HeatitClient,
    HeatitConnectionError,
    HeatitMissingFieldError,
    HeatitProtocolError,
    HeatitResponseError,
    parse_signal_strength,
    parse_status,
    redact_status,
    redact_status_bytes,
)
from custom_components.heatit_wifi_panel.registry import PARAMETERS
from tests.conftest import observed_directories
from tests.fakes import ABSENT, UNSCRUBBED, mutated

if TYPE_CHECKING:
    from pathlib import Path

    from aioresponses import aioresponses

from tests.client.conftest import HOST, JSON

STATUS_URL = f"http://{HOST}/api/status"

OBSERVED = observed_directories()

#: Copied by hand from tests/fixtures/observed/fw-1.21/status.json.
REFERENCE_READINGS: dict[str, object] = {
    "panelMode": 1,
    "heatingSetpoint": 19.0,
    "ecoSetpoint": 18.0,
    "minimumTemperatureLimit": 5.0,
    "maximumTemperatureLimit": 40.0,
    "sensorCalibration": 0.0,
    "loadLimit": 600,
    "activeDisplayBrightness": 100,
    "standbyDisplayBrightness": 0,
    "disableButtons": 1,
    "temperatureDisplay": True,
    "sensorMode": False,
    "openWindowDetection": False,
}


# --- parsing the observed bytes ---------------------------------------------


def test_the_reference_fixture_parses_to_its_required_core(
    reference_status_bytes: bytes,
) -> None:
    status = parse_status(reference_status_bytes)
    assert status.device_id == "FIXTUREFIXTUREFIXTUREX"
    assert status.relay_state == "Idle"
    assert status.room_temperature == 23.0
    assert status.panel_mode == 1
    assert status.comfort_setpoint == 19.0
    assert status.eco_setpoint == 18.0


def test_the_optional_top_level_fields_read_as_typed(
    reference_status_bytes: bytes,
) -> None:
    status = parse_status(reference_status_bytes)
    assert status.name == "Näytehuone 1"
    assert status.room == "Bedroom"
    assert status.model == "Heatit WiFi Panel Heater"
    assert status.firmware == "1.21"
    assert status.mac == "02:00:00:00:00:01"
    assert status.signal_strength_dbm == -66
    assert status.get_int("currentPower") == 0
    assert status.get_float("totalConsumption") == 0.0
    assert status.get_int("parameters.maxLoad") == 6
    assert status.get_bool("parameters.OWD.activeNow") is False
    assert status.get_int("parameters.OWD.activeTime") == 0
    assert status.get_str("Network.status") == "ok"


def test_the_typed_getters_answer_none_for_the_wrong_type(
    reference_status_bytes: bytes,
) -> None:
    status = parse_status(reference_status_bytes)
    assert status.get_float("state") is None
    assert status.get_float("parameters.sensorMode") is None
    assert status.get_int("roomTemperature") is None
    assert status.get_int("parameters.sensorMode") is None
    assert status.get_bool("state") is None
    assert status.get_str("currentPower") is None
    assert status.get("Network.mac.octet") is None
    assert status.get("no.such.path") is None


@pytest.mark.parametrize("key", list(REFERENCE_READINGS), ids=list(REFERENCE_READINGS))
def test_every_registry_read_path_resolves_against_the_reference(
    reference_status_bytes: bytes, key: str
) -> None:
    status = parse_status(reference_status_bytes)
    descriptor = PARAMETERS[key]
    assert descriptor.present_in(status)
    reading = descriptor.read(status)
    assert reading == REFERENCE_READINGS[key]
    assert type(reading) is type(REFERENCE_READINGS[key])


@pytest.mark.parametrize("directory", OBSERVED, ids=[d.name for d in OBSERVED])
def test_parse_only_sweep_over_every_observed_directory(directory: Path) -> None:
    status = parse_status((directory / "status.json").read_bytes())
    assert status.firmware == directory.name.removeprefix("fw-")
    assert status.device_id


@pytest.mark.parametrize(
    "path",
    [
        "id",
        "state",
        "roomTemperature",
        "parameters.panelMode",
        "parameters.heatingSetpoint",
        "parameters.ecoSetpoint",
    ],
)
@pytest.mark.parametrize("value", [ABSENT, None], ids=["absent", "null"])
def test_a_missing_or_null_required_core_field_names_its_path(
    reference_status_bytes: bytes, path: str, value: object
) -> None:
    raw = mutated(reference_status_bytes, {path: value})
    with pytest.raises(HeatitMissingFieldError) as excinfo:
        parse_status(raw)
    assert excinfo.value.path == path
    assert isinstance(excinfo.value, HeatitProtocolError)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("id", 5),
        ("state", True),
        ("roomTemperature", "23.0"),
        ("parameters.panelMode", 1.5),
        ("parameters.panelMode", True),
        ("parameters.heatingSetpoint", "19"),
        ("parameters", []),
    ],
)
def test_a_required_core_field_of_the_wrong_type_is_a_protocol_error(
    reference_status_bytes: bytes, path: str, value: object
) -> None:
    with pytest.raises(HeatitProtocolError):
        parse_status(mutated(reference_status_bytes, {path: value}))


@pytest.mark.parametrize("raw", [b"", b"[]", b'"status"', b"<html>", b"\xff\xfe"])
def test_a_body_that_is_not_a_status_is_a_protocol_error(raw: bytes) -> None:
    with pytest.raises(HeatitProtocolError):
        parse_status(raw)


@pytest.mark.parametrize("key", [k for k, d in PARAMETERS.items() if not d.required])
@pytest.mark.parametrize("value", [ABSENT, None], ids=["absent", "null"])
def test_a_dropped_optional_parameter_leaves_only_its_reading_unknown(
    reference_status_bytes: bytes, key: str, value: object
) -> None:
    descriptor = PARAMETERS[key]
    status = parse_status(
        mutated(reference_status_bytes, {descriptor.read_path: value})
    )
    assert not descriptor.present_in(status)
    assert descriptor.read(status) is None
    others = {k for k, d in PARAMETERS.items() if k != key}
    assert all(PARAMETERS[k].present_in(status) for k in others)


def test_unknown_keys_are_ignored_at_top_level_and_under_parameters(
    reference_status_bytes: bytes,
) -> None:
    raw = mutated(
        reference_status_bytes,
        {"futureField": "x", "parameters.lowTemperatureProtection": 3},
    )
    status = parse_status(raw)
    assert status.comfort_setpoint == 19.0
    assert all(d.present_in(status) for d in PARAMETERS.values())


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-67dBm", -67),
        ("-66dBm", -66),
        (" -5 dbm ", -5),
        ("67dBm", 67),  # no sign fix-up: the device emits a signed value
        ("strong", None),
        ("-67", None),
        ("", None),
        (7, None),
        (None, None),
    ],
)
def test_signal_strength_parses_or_answers_none(
    value: object, expected: int | None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        assert parse_signal_strength(value) == expected
    assert (expected is None) == any(
        "wifiSignalStrength" in record.message for record in caplog.records
    )


# --- the one redaction ------------------------------------------------------


def test_redact_status_replaces_exactly_the_four_identifiers(
    reference_status_bytes: bytes,
) -> None:
    status = parse_status(mutated(reference_status_bytes, UNSCRUBBED))
    redacted = redact_status(status.document)
    assert redacted["id"] == "FIXTUREFIXTUREFIXTUREX"
    assert redacted["Network"]["mac"] == "02:00:00:00:00:01"
    assert redacted["Network"]["SSID"] == "SSID-REDACTED"
    assert redacted["Network"]["ipAddress"] == "10.0.0.2"
    assert redacted["name"] == "Näytehuone 1"
    assert redacted["room"] == "Bedroom"
    assert redacted["Network"]["wifiSignalStrength"] == "-66dBm"
    assert redacted["parameters"] == status.document["parameters"]
    # The original is untouched.
    assert status.document["id"] == UNSCRUBBED["id"]
    assert status.document["Network"]["mac"] == UNSCRUBBED["Network.mac"]


def test_the_wire_and_parsed_scrubs_agree_on_a_real_status(
    reference_status_bytes: bytes,
) -> None:
    """One scrub, two levels: the same document either way."""
    unscrubbed = mutated(reference_status_bytes, UNSCRUBBED)
    via_bytes = parse_status(redact_status_bytes(unscrubbed)).document
    via_document = redact_status(parse_status(unscrubbed).document)
    assert via_bytes == via_document


def test_redact_status_tolerates_a_status_without_a_network_block(
    reference_status_bytes: bytes,
) -> None:
    status = parse_status(mutated(reference_status_bytes, {"Network": ABSENT}))
    assert "Network" not in redact_status(status.document)


def test_redact_status_bytes_touches_nothing_but_the_four_values(
    reference_status_bytes: bytes,
) -> None:
    """Scrubbing real-looking values restores the committed bytes exactly.

    So ``0.00`` and the non-ASCII name survive the wire-level scrub.
    """
    unscrubbed = reference_status_bytes
    for path, real in UNSCRUBBED.items():
        key = path.rsplit(".", 1)[-1]
        placeholder = parse_status(reference_status_bytes).get_str(path)
        assert placeholder is not None
        unscrubbed = unscrubbed.replace(
            f'"{key}":"{placeholder}"'.encode(), f'"{key}":"{real}"'.encode()
        )
    assert unscrubbed != reference_status_bytes
    assert redact_status_bytes(unscrubbed) == reference_status_bytes
    assert b'"totalConsumption":0.00' in redact_status_bytes(unscrubbed)


def test_redact_status_bytes_is_shape_preserving_with_spaces() -> None:
    raw = b'{ "id" : "AbCdEfGhIjKlMnOpQrStUv", "Network": { "mac" : "AA:BB" } }'
    expected = (
        b'{ "id" : "FIXTUREFIXTUREFIXTUREX", '
        b'"Network": { "mac" : "02:00:00:00:00:01" } }'
    )
    assert redact_status_bytes(raw) == expected


# --- get_status over the wire -----------------------------------------------


async def test_the_non_ascii_name_survives_a_charset_less_content_type(
    client: HeatitClient,
    mocked: aioresponses,
    reference_status_bytes: bytes,
    reference_headers: dict[str, str],
) -> None:
    assert reference_headers["Content-Type"] == JSON  # the observed evidence
    mocked.get(STATUS_URL, body=reference_status_bytes, headers=reference_headers)

    status = await client.get_status()

    assert status.name == "Näytehuone 1"
    assert status.room == "Bedroom"


async def test_get_status_retains_the_raw_body_and_headers(
    client: HeatitClient, mocked: aioresponses, reference_status_bytes: bytes
) -> None:
    mocked.get(STATUS_URL, body=reference_status_bytes, content_type=JSON)

    await client.get_status()

    assert client.last_raw_body == reference_status_bytes
    assert client.last_raw_headers is not None
    assert client.last_raw_headers["Content-Type"] == JSON
    assert client.last_status_retried is False


async def test_get_status_logs_the_redacted_status_at_debug_and_never_the_bytes(
    client: HeatitClient,
    mocked: aioresponses,
    reference_status_bytes: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = mutated(reference_status_bytes, UNSCRUBBED)
    mocked.get(STATUS_URL, body=raw, content_type=JSON)

    with caplog.at_level(logging.DEBUG):
        await client.get_status()

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "FIXTUREFIXTUREFIXTUREX" in text
    assert "Näytehuone 1" in text
    assert f"{len(raw)} bytes" in text
    assert not any(value in text for value in UNSCRUBBED.values())


async def test_get_status_uses_the_five_second_budget_per_attempt(
    client: HeatitClient, mocked: aioresponses, reference_status_bytes: bytes
) -> None:
    mocked.get(STATUS_URL, body=reference_status_bytes, content_type=JSON)

    await client.get_status()

    [call] = mocked.requests[("GET", URL(STATUS_URL))]
    assert call.kwargs["timeout"] == aiohttp.ClientTimeout(total=5, connect=3)


async def test_get_status_is_retried_once_and_the_retry_logs_one_debug_line(
    client: HeatitClient,
    mocked: aioresponses,
    reference_status_bytes: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mocked.get(STATUS_URL, exception=TimeoutError())
    mocked.get(STATUS_URL, body=reference_status_bytes, content_type=JSON)

    with caplog.at_level(logging.DEBUG):
        status = await client.get_status()

    assert status.device_id == "FIXTUREFIXTUREFIXTUREX"
    assert client.last_status_retried is True
    retry_lines = [r for r in caplog.records if "retry" in r.getMessage()]
    assert len(retry_lines) == 1
    assert retry_lines[0].levelno == logging.DEBUG
    assert HOST in retry_lines[0].getMessage()


async def test_get_status_gives_up_after_two_attempts(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.get(STATUS_URL, exception=aiohttp.ClientConnectionError(), repeat=True)

    with pytest.raises(HeatitConnectionError):
        await client.get_status()

    assert len(mocked.requests[("GET", URL(STATUS_URL))]) == 2
    # The retry ran and did not help. A diagnostics download from a panel
    # that goes away has to be able to say so (§7.3).
    assert client.last_status_retried is True


async def test_a_non_200_status_read_is_not_retried(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.get(STATUS_URL, status=404, body="Nothing matches", content_type="text/html")
    mocked.get(STATUS_URL, status=404, body="Nothing matches", content_type="text/html")

    with pytest.raises(HeatitResponseError):
        await client.get_status()

    assert len(mocked.requests[("GET", URL(STATUS_URL))]) == 1


# --- one request in flight per panel ----------------------------------------


async def test_every_request_to_one_panel_waits_its_turn(
    client: HeatitClient, mocked: aioresponses, reference_status_bytes: bytes
) -> None:
    in_flight = 0
    peak = 0

    async def slow(_url: object, **_kwargs: object) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        in_flight -= 1

    mocked.get(
        STATUS_URL, body=reference_status_bytes, content_type=JSON, callback=slow
    )
    mocked.post(
        f"http://{HOST}/api/parameters?heatingSetpoint=19.0",
        body='{"status":"Success"}',
        content_type=JSON,
        callback=slow,
    )
    mocked.delete(
        f"http://{HOST}/api/reset/kwh?resetKwh=Reset",
        body='{"status":"Success"}',
        content_type=JSON,
        callback=slow,
    )

    await asyncio.gather(
        client.get_status(),
        client.set_parameter("heatingSetpoint", 19.0),
        client.reset_kwh(),
    )

    assert peak == 1


async def test_the_lock_is_per_client_instance(
    session: aiohttp.ClientSession, mocked: aioresponses, reference_status_bytes: bytes
) -> None:
    peak = 0
    in_flight = 0

    async def slow(_url: object, **_kwargs: object) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        in_flight -= 1

    mocked.get(
        STATUS_URL,
        body=reference_status_bytes,
        content_type=JSON,
        callback=slow,
        repeat=True,
    )
    first = HeatitClient(HOST, session=session)
    second = HeatitClient(HOST, session=session)

    await asyncio.gather(first.get_status(), second.get_status())

    assert peak == 2
