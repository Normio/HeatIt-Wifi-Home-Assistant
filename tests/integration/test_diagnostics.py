"""The diagnostics download: everything a bug report needs, no network (§7.3).

Fetched over the real HTTP endpoint rather than by calling the module, so the
platform is proved to be wired and the payload to be JSON — a ``bytes`` in it
would 500 here and pass a direct call.

The leak test is the rule test §9.2 names for ``diagnostics``: a status carrying
a real panel's four identifiers goes in, and neither the parsed nor the raw
section may carry any of them out.
"""

import json
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.heatit_wifi_panel import diagnostics
from custom_components.heatit_wifi_panel.api import HeatitConnectionError
from custom_components.heatit_wifi_panel.const import (
    CONF_POLL_INTERVAL,
    DOMAIN,
    VERIFIED_FIRMWARES,
)
from custom_components.heatit_wifi_panel.registry import PARAMETERS
from tests.conftest import REFERENCE_FIRMWARE
from tests.fakes import ABSENT, UNSCRUBBED, FakeHeatitClient
from tests.integration.conftest import setup_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

REAL_HOST = "192.168.1.77"
"""A host that is nobody's placeholder: the reference capture's is ``10.0.0.2``."""


async def fetch(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, entry: MockConfigEntry
) -> dict[str, Any]:
    """Fetch a loaded entry's diagnostics over the HTTP endpoint."""
    payload: dict[str, Any] = dict(
        await get_diagnostics_for_config_entry(hass, hass_client, entry)
    )
    return payload


async def download(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, entry: MockConfigEntry
) -> dict[str, Any]:
    """Set the entry up, then fetch."""
    assert await setup_entry(hass, entry)
    return await fetch(hass, hass_client, entry)


@pytest.mark.usefixtures("patched_client")
async def test_the_download_carries_the_whole_picture(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    reference_status_bytes: bytes,
    reference_headers: dict[str, str],
) -> None:
    payload = await download(hass, hass_client, mock_config_entry)

    assert payload["entry_data"] == {CONF_HOST: "**REDACTED**"}
    assert payload["options"] == {}
    assert payload["status"] == json.loads(reference_status_bytes)
    assert payload["firmware"] == REFERENCE_FIRMWARE
    assert payload["firmware_verified"] is True
    assert payload["observed_parameters"] == sorted(PARAMETERS)
    assert payload["vanished_parameters"] == []
    assert payload["last_poll"] == {
        "outcome": "ok",
        "duration_seconds": pytest.approx(0, abs=1),
        "retried": False,
    }
    assert payload["raw"]["headers"] == reference_headers
    assert payload["raw"]["body"].encode("utf-8") == reference_status_bytes


@pytest.mark.usefixtures("patched_client")
async def test_the_options_are_the_poll_interval(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The one option key there is, at a value nothing defaults to."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_POLL_INTERVAL: 45}
    )

    payload = await download(hass, hass_client, mock_config_entry)

    assert payload["options"] == {CONF_POLL_INTERVAL: 45}


@pytest.mark.usefixtures("patched_client")
async def test_no_identifier_of_the_users_network_survives(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    patched_client: FakeHeatitClient,
) -> None:
    """§9.2's ``diagnostics`` rule test: neither section carries one out."""
    patched_client.set_status(UNSCRUBBED)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Näytehuone 1",
        unique_id=UNSCRUBBED["id"],
        data={CONF_HOST: REAL_HOST},
    )

    payload = await download(hass, hass_client, entry)

    text = json.dumps(payload, ensure_ascii=False)
    assert not [real for real in UNSCRUBBED.values() if real in text]
    assert REAL_HOST not in text
    # Both sections scrubbed, not one of them dropped.
    assert payload["status"]["id"] == "FIXTUREFIXTUREFIXTUREX"
    assert payload["status"]["Network"]["SSID"] == "SSID-REDACTED"
    assert '"SSID-REDACTED"' in payload["raw"]["body"]
    assert '"02:00:00:00:00:01"' in payload["raw"]["body"]
    # ``name`` is a label, not an identifier, and it is what proves the
    # charset-less UTF-8 decode: logging and diagnostics keep it (§8.3).
    assert payload["status"]["name"] == "Näytehuone 1"


async def test_a_failed_poll_is_what_the_download_reports(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The last status still stands, and the poll that failed is named."""
    assert await setup_entry(hass, mock_config_entry)
    patched_client.fail(HeatitConnectionError("timed out"))
    await mock_config_entry.runtime_data.async_refresh()

    payload = await fetch(hass, hass_client, mock_config_entry)

    assert payload["last_poll"]["outcome"] == "cannot_connect"
    assert payload["status"]["id"] == "FIXTUREFIXTUREFIXTUREX"


async def test_a_retried_poll_says_the_retry_was_used(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The one dropped-packet tolerance there is, visible in the download."""
    patched_client.last_status_retried = True

    payload = await download(hass, hass_client, mock_config_entry)

    assert payload["last_poll"]["retried"] is True


async def test_an_unverified_firmware_is_named_as_such(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The download from an unverified firmware is the fixture candidate."""
    patched_client.set_status({"firmware": "1.22"})

    payload = await download(hass, hass_client, mock_config_entry)

    assert payload["firmware"] == "1.22"
    assert payload["firmware_verified"] is False
    assert "1.22" not in VERIFIED_FIRMWARES


async def test_a_firmware_the_panel_never_reported_is_unverified_too(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    patched_client.set_status({"firmware": ABSENT})

    payload = await download(hass, hass_client, mock_config_entry)

    assert payload["firmware"] is None
    assert payload["firmware_verified"] is False


async def test_a_vanished_parameter_reaches_the_download(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Which is the point of shipping both lists: the difference is the report."""
    assert await setup_entry(hass, mock_config_entry)
    patched_client.set_status({"parameters.disableButtons": ABSENT})
    await mock_config_entry.runtime_data.async_refresh()

    payload = await fetch(hass, hass_client, mock_config_entry)

    assert payload["vanished_parameters"] == ["disableButtons"]
    assert "disableButtons" in payload["observed_parameters"]


async def test_a_client_holding_no_bytes_still_produces_a_download(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The raw section is the one part that can be missing, never an error."""
    assert await setup_entry(hass, mock_config_entry)
    patched_client.last_raw_body = None

    payload = await fetch(hass, hass_client, mock_config_entry)

    assert payload["raw"] is None
    assert payload["status"]["id"] == "FIXTUREFIXTUREFIXTUREX"


def test_only_config_entry_diagnostics_is_implemented() -> None:
    """One entry is one device, so a device download would repeat this one."""
    assert hasattr(diagnostics, "async_get_config_entry_diagnostics")
    assert not hasattr(diagnostics, "async_get_device_diagnostics")
