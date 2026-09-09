"""Every transcribed write-path response behaves as its manifest says (§8.3).

The manifest is the provenance record; this test is what keeps a file from
sitting unused, and what tells the probe which ones its captures replace.
"""

import json
from typing import TYPE_CHECKING, Any

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.heatit_wifi_panel.api import (
    HeatitClient,
    HeatitParameterRejected,
    HeatitResponseError,
)
from tests.conftest import SYNTHESISED_DIR
from tests.fakes import synthesised, synthesised_manifest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

HOST = "panel.test"
MANIFEST = synthesised_manifest()


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def mocked() -> Iterator[aioresponses]:
    with aioresponses() as mock:
        yield mock


@pytest.fixture
def client(session: aiohttp.ClientSession) -> HeatitClient:
    return HeatitClient(HOST, session=session)


def test_the_manifest_and_the_directory_agree() -> None:
    files = {p.name for p in SYNTHESISED_DIR.iterdir()} - {"manifest.json"}
    assert files == set(MANIFEST)
    assert all(entry["source"] for entry in MANIFEST.values())


@pytest.mark.parametrize("name", list(MANIFEST), ids=list(MANIFEST))
async def test_each_synthesised_response_behaves_as_documented(
    client: HeatitClient, mocked: aioresponses, name: str
) -> None:
    entry: dict[str, Any] = MANIFEST[name]
    body = synthesised(name)
    kind = entry["kind"]
    if kind == "write-echo":
        parameter = entry["parameter"]
        mocked.post(
            f"http://{HOST}/api/parameters?{parameter}={_wire(parameter, entry)}",
            body=body,
            content_type="application/json",
        )
        applied = await client.set_parameter(parameter, entry["applied"])
        assert applied == entry["applied"]
        assert type(applied) is type(entry["applied"])
    elif kind == "rejection":
        parameter = entry["parameter"]
        mocked.post(
            f"http://{HOST}/api/parameters?{parameter}={_wire(parameter, entry)}",
            status=entry["status"],
            body=body,
            content_type="application/json",
        )
        with pytest.raises(HeatitParameterRejected) as excinfo:
            await client.set_parameter(parameter, _value(parameter))
        assert excinfo.value.parameter == parameter
        assert excinfo.value.reason == entry["reason"]
        assert json.loads(body)["reason"] == entry["reason"]
    elif kind == "reset":
        mocked.delete(
            f"http://{HOST}/api/reset/kwh?resetKwh=Reset",
            body=body,
            content_type="application/json",
        )
        await client.reset_kwh()
    elif kind == "response-error":
        mocked.get(
            f"http://{HOST}/api/status",
            status=entry["status"],
            body=body,
            content_type=entry["content_type"],
        )
        with pytest.raises(HeatitResponseError) as response_error:
            await client.get_status()
        assert response_error.value.status_code == entry["status"]
    else:  # pragma: no cover - a new kind needs a new branch
        pytest.fail(f"unknown kind {kind!r} for {name}")


def _value(parameter: str) -> object:
    """Pick a locally valid value for a parameter, so the request is sent."""
    return {
        "heatingSetpoint": 19.0,
        "standbyDisplayBrightness": 50,
        "minimumTemperatureLimit": 5.0,
        "sensorCalibration": -1.0,
        "openWindowDetection": True,
        "sensorMode": True,
    }[parameter]


def _wire(parameter: str, entry: dict[str, Any]) -> str:
    from custom_components.heatit_wifi_panel.registry import PARAMETERS  # noqa: PLC0415

    value = entry.get("applied", _value(parameter))
    return PARAMETERS[parameter].encode(value)
