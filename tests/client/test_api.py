"""The client at the HTTP seam: the real client over aioresponses, no hass.

Every expected request line here is transcribed from the spec (§2.2, §2.5,
§8.5), never derived from the registry, so the two encodings can disagree.
"""

import ast
import inspect
import re
from typing import TYPE_CHECKING

import aiohttp
import pytest
from yarl import URL

from custom_components.heatit_wifi_panel import api, const, registry
from custom_components.heatit_wifi_panel.api import (
    HeatitClient,
    HeatitConnectionError,
    HeatitParameterRejected,
    HeatitProtocolError,
    HeatitResponseError,
)
from custom_components.heatit_wifi_panel.registry import PARAMETERS

if TYPE_CHECKING:
    import types

    from aioresponses import aioresponses

from tests.client.conftest import HOST, JSON

PARAMETERS_URL = f"http://{HOST}/api/parameters"
RESET_KWH_URL = f"http://{HOST}/api/reset/kwh?resetKwh=Reset"
RESET_SETTINGS_URL = f"http://{HOST}/api/reset/settings"
ANY_URL = re.compile(r".*")

HTML = "text/html"
NOT_FOUND_BODY = "Nothing matches the given URI"


def requests_made(mocked: aioresponses) -> list[tuple[str, str]]:
    """Every request the mock saw, as ``(METHOD, url-with-query)`` in order."""
    return [
        (method, str(url))
        for (method, url), calls in mocked.requests.items()
        for _ in calls
    ]


def timeouts_used(mocked: aioresponses) -> list[aiohttp.ClientTimeout]:
    return [
        call.kwargs["timeout"] for calls in mocked.requests.values() for call in calls
    ]


# --- public surface ---------------------------------------------------------


def test_public_surface_is_exactly_four_methods_and_none_takes_a_retry() -> None:
    public = {
        name
        for name, member in inspect.getmembers(HeatitClient)
        if not name.startswith("_") and inspect.isfunction(member)
    }
    assert public == {"get_status", "set_parameter", "reset_kwh", "reset_settings"}
    for name in public:
        parameters = inspect.signature(getattr(HeatitClient, name)).parameters
        assert not any(
            re.search(r"retr|attempt", parameter, re.IGNORECASE)
            for parameter in parameters
        ), name


@pytest.mark.parametrize("module", [api, registry, const])
def test_the_client_imports_nothing_from_homeassistant(
    module: types.ModuleType,
) -> None:
    tree = ast.parse(inspect.getsource(module))
    imported = [
        name
        for node in ast.walk(tree)
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    ]
    assert not [name for name in imported if name.startswith("homeassistant")]


# --- the exact request per serialisation class ------------------------------


@pytest.mark.parametrize(
    ("key", "value", "query"),
    [
        ("heatingSetpoint", 19.0, "heatingSetpoint=19.0"),
        ("ecoSetpoint", 18.5, "ecoSetpoint=18.5"),
        ("sensorCalibration", 1.1, "sensorCalibration=1.1"),
        ("sensorCalibration", -1.0, "sensorCalibration=-1.0"),
        ("standbyDisplayBrightness", 50, "standbyDisplayBrightness=5"),
        ("activeDisplayBrightness", 100.0, "activeDisplayBrightness=10"),
        ("loadLimit", 600, "loadLimit=6"),
        ("openWindowDetection", False, "openWindowDetection=false"),
        ("sensorMode", True, "sensorMode=true"),
        ("panelMode", 2, "panelMode=2"),
    ],
)
async def test_set_parameter_sends_exactly_one_query_parameter(
    client: HeatitClient,
    mocked: aioresponses,
    key: str,
    value: object,
    query: str,
) -> None:
    mocked.post(
        f"{PARAMETERS_URL}?{query}", body='{"status":"Success"}', content_type=JSON
    )

    await client.set_parameter(key, value)

    assert requests_made(mocked) == [("POST", f"{PARAMETERS_URL}?{query}")]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("heatingSetpoint", 19.3),
        ("heatingSetpoint", 41.0),
        ("sensorCalibration", 1.15),
        ("loadLimit", 650),
        ("standbyDisplayBrightness", 55),
        ("panelMode", 7),
        ("openWindowDetection", 1),
        ("notAParameter", 1),
    ],
)
async def test_local_rejection_emits_no_request(
    client: HeatitClient, mocked: aioresponses, key: str, value: object
) -> None:
    mocked.post(ANY_URL, body='{"status":"Success"}', content_type=JSON)

    with pytest.raises(ValueError, match=key):
        await client.set_parameter(key, value)

    assert requests_made(mocked) == []


async def test_no_code_path_emits_a_parameter_less_post(
    client: HeatitClient, mocked: aioresponses
) -> None:
    """Across the whole write surface, every POST carries a query."""
    mocked.post(ANY_URL, body='{"status":"Success"}', content_type=JSON, repeat=True)
    mocked.delete(ANY_URL, body='{"status":"Success"}', content_type=JSON, repeat=True)
    for descriptor in PARAMETERS.values():
        value: object = True
        if descriptor.choices is not None:
            value = descriptor.choices[-1]
        elif descriptor.maximum is not None:
            value = descriptor.maximum
        await client.set_parameter(descriptor.key, value)
        with pytest.raises(ValueError, match=descriptor.key):
            await client.set_parameter(descriptor.key, "bogus")
    await client.reset_kwh()
    await client.reset_settings()

    posts = [url for method, url in requests_made(mocked) if method == "POST"]
    assert len(posts) == len(PARAMETERS)
    assert all(URL(url).query for url in posts), posts
    assert all(url.startswith(f"{PARAMETERS_URL}?") for url in posts), posts


# --- the verdict ------------------------------------------------------------


@pytest.mark.parametrize("status", ["Success", "success", "Success.", " SUCCESS!\n"])
async def test_verdict_matches_status_after_stripping(
    client: HeatitClient, mocked: aioresponses, status: str
) -> None:
    mocked.post(
        f"{PARAMETERS_URL}?heatingSetpoint=19.0",
        body=f'{{"status":"{status!s}","heatingSetpoint":19}}'.replace("\n", "\\n"),
        content_type=JSON,
    )

    assert await client.set_parameter("heatingSetpoint", 19.0) == 19.0


async def test_a_200_whose_status_is_failed_is_a_rejection(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.post(
        f"{PARAMETERS_URL}?heatingSetpoint=19.0",
        body='{"status":"failed","reason":"heatingSetpoint is invalid!"}',
        content_type=JSON,
    )

    with pytest.raises(HeatitParameterRejected) as excinfo:
        await client.set_parameter("heatingSetpoint", 19.0)

    assert excinfo.value.parameter == "heatingSetpoint"
    assert excinfo.value.reason == "heatingSetpoint is invalid!"


# --- echo handling ----------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value", "echo", "applied"),
    [
        ("heatingSetpoint", 19.0, "19", 19.0),
        ("sensorCalibration", -1.0, "-1", -1.0),
        ("loadLimit", 600, "6", 600),
        ("activeDisplayBrightness", 50, "5", 50),
        ("openWindowDetection", True, "true", True),
    ],
)
async def test_the_applied_value_is_returned_coerced_to_the_declared_type(
    client: HeatitClient,
    mocked: aioresponses,
    key: str,
    value: object,
    echo: str,
    applied: object,
) -> None:
    mocked.post(
        ANY_URL, body=f'{{"status":"Success","{key}":{echo}}}', content_type=JSON
    )

    result = await client.set_parameter(key, value)

    assert result == applied
    assert type(result) is type(applied)


@pytest.mark.parametrize(
    "body",
    [
        '{"status":"Success"}',
        '{"status":"Success","heatingSetpoint":"19.0"}',
        '{"status":"Success","heatingSetpoint":null}',
        '{"status":"Success","ecoSetpoint":19}',
    ],
)
async def test_a_missing_or_unparseable_echo_falls_back_to_the_requested_value(
    client: HeatitClient, mocked: aioresponses, body: str
) -> None:
    mocked.post(ANY_URL, body=body, content_type=JSON)

    assert await client.set_parameter("heatingSetpoint", 19) == 19.0


# --- the exception taxonomy -------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        "heatingSetpoint is invalid!",
        "standbyDisplayBrightness is not in range 0~10",
        "heatingSetpoint must be step values of 0.5",
        "heatingSetpoint outrange of temperature limit(min or max)",
        (
            "minimumTemperatureLimit is greater than current max temperature "
            "limit or equal to it"
        ),
    ],
)
async def test_a_400_is_a_rejection_naming_the_parameter_we_sent(
    client: HeatitClient, mocked: aioresponses, reason: str
) -> None:
    mocked.post(
        ANY_URL,
        status=400,
        body=f'{{"status":"failed","reason":"{reason}"}}',
        content_type=JSON,
    )

    with pytest.raises(HeatitParameterRejected) as excinfo:
        await client.set_parameter("heatingSetpoint", 19.0)

    assert excinfo.value.parameter == "heatingSetpoint"
    assert excinfo.value.reason == reason
    assert excinfo.value.status_code == 400
    assert isinstance(excinfo.value, HeatitResponseError)
    assert reason in str(excinfo.value)


async def test_a_400_on_a_reset_is_a_response_error_not_a_rejection(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.delete(
        RESET_KWH_URL,
        status=400,
        body='{"status":"failed","reason":"nothing to reset."}',
        content_type=JSON,
    )

    with pytest.raises(HeatitResponseError) as excinfo:
        await client.reset_kwh()

    assert excinfo.value.status_code == 400
    assert excinfo.value.reason == "nothing to reset."
    assert not isinstance(excinfo.value, HeatitParameterRejected)


async def test_a_500_on_a_write_is_a_response_error_not_a_rejection(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.post(ANY_URL, status=500, body="boom", content_type=HTML, reason="Oops")

    with pytest.raises(HeatitResponseError) as excinfo:
        await client.set_parameter("heatingSetpoint", 19.0)

    assert excinfo.value.status_code == 500
    assert excinfo.value.reason == "Oops"
    assert not isinstance(excinfo.value, HeatitParameterRejected)


async def test_a_400_without_a_reason_falls_back_to_the_http_reason_phrase(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.post(
        ANY_URL,
        status=400,
        body='{"status":"failed"}',
        content_type=JSON,
        reason="Bad Request",
    )

    with pytest.raises(HeatitParameterRejected) as excinfo:
        await client.set_parameter("heatingSetpoint", 19.0)

    assert excinfo.value.reason == "Bad Request"


@pytest.mark.parametrize("status_code", [404, 405, 500])
async def test_an_unexpected_status_is_a_response_error_with_its_code(
    client: HeatitClient, mocked: aioresponses, status_code: int
) -> None:
    mocked.get(
        f"http://{HOST}/api/status",
        status=status_code,
        body=NOT_FOUND_BODY,
        content_type=HTML,
    )

    with pytest.raises(HeatitResponseError) as excinfo:
        await client.get_status()

    assert excinfo.value.status_code == status_code
    assert not isinstance(excinfo.value, HeatitParameterRejected)
    assert requests_made(mocked) == [("GET", f"http://{HOST}/api/status")]


@pytest.mark.parametrize(
    "error",
    [
        aiohttp.ClientConnectionError("refused"),
        aiohttp.ServerDisconnectedError(),
        TimeoutError(),
    ],
)
async def test_a_transport_failure_is_a_connection_error(
    client: HeatitClient, mocked: aioresponses, error: Exception
) -> None:
    mocked.post(ANY_URL, exception=error)

    with pytest.raises(HeatitConnectionError):
        await client.set_parameter("heatingSetpoint", 19.0)


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (NOT_FOUND_BODY, HTML),
        ("", JSON),
        ('{"reason":"no status key"}', JSON),
        ('{"status":7}', JSON),
        ("[1, 2]", JSON),
        (b"\xff\xfe not utf-8", JSON),
    ],
)
async def test_a_200_we_cannot_make_sense_of_is_a_protocol_error(
    client: HeatitClient, mocked: aioresponses, body: str | bytes, content_type: str
) -> None:
    mocked.post(ANY_URL, body=body, content_type=content_type)

    with pytest.raises(HeatitProtocolError) as excinfo:
        await client.set_parameter("heatingSetpoint", 19.0)

    message = str(excinfo.value)
    assert content_type in message
    assert "bytes" in message
    assert NOT_FOUND_BODY not in message


# --- resets -----------------------------------------------------------------


async def test_reset_kwh_sends_exactly_the_documented_delete(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.delete(RESET_KWH_URL, body='{"status":"Success"}', content_type=JSON)

    await client.reset_kwh()

    assert requests_made(mocked) == [("DELETE", RESET_KWH_URL)]


async def test_reset_settings_sends_exactly_the_bare_delete(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.delete(RESET_SETTINGS_URL, body='{"status":"Success"}', content_type=JSON)

    await client.reset_settings()

    assert requests_made(mocked) == [("DELETE", RESET_SETTINGS_URL)]


async def test_a_reset_uses_the_one_status_envelope(
    client: HeatitClient, mocked: aioresponses
) -> None:
    """There is no ``reset`` key: a body carrying one instead is not success."""
    mocked.delete(RESET_KWH_URL, body='{"reset":"success"}', content_type=JSON)

    with pytest.raises(HeatitProtocolError):
        await client.reset_kwh()


async def test_a_reset_the_device_refuses_is_a_response_error(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.delete(
        RESET_SETTINGS_URL,
        body='{"status":"failed","reason":"busy."}',
        content_type=JSON,
    )

    with pytest.raises(HeatitResponseError) as excinfo:
        await client.reset_settings()

    assert excinfo.value.reason == "busy."
    assert not isinstance(excinfo.value, HeatitParameterRejected)


@pytest.mark.parametrize("method_name", ["reset_kwh", "reset_settings"])
async def test_a_reset_is_never_retried(
    client: HeatitClient, mocked: aioresponses, method_name: str
) -> None:
    mocked.delete(ANY_URL, exception=TimeoutError(), repeat=True)

    with pytest.raises(HeatitConnectionError):
        await getattr(client, method_name)()

    assert len(requests_made(mocked)) == 1


async def test_a_write_is_never_retried(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.post(ANY_URL, exception=aiohttp.ClientConnectionError(), repeat=True)

    with pytest.raises(HeatitConnectionError):
        await client.set_parameter("heatingSetpoint", 19.0)

    assert len(requests_made(mocked)) == 1


# --- timeouts ---------------------------------------------------------------


async def test_writes_and_resets_use_the_ten_second_budget(
    client: HeatitClient, mocked: aioresponses
) -> None:
    mocked.post(ANY_URL, body='{"status":"Success"}', content_type=JSON)
    mocked.delete(ANY_URL, body='{"status":"Success"}', content_type=JSON, repeat=True)

    await client.set_parameter("heatingSetpoint", 19.0)
    await client.reset_kwh()
    await client.reset_settings()

    assert timeouts_used(mocked) == [aiohttp.ClientTimeout(total=10, connect=3)] * 3
