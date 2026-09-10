"""Setup, the device, unload, and §6.2's failure matrix.

Everything that fails at setup retries — a panel that answers nothing, a captive
page, a mid-reboot stack and a status short a *required core* field are
indistinguishable from a panel that is about to come back. The one exception is
a *foreign panel*, which retrying can never fix.
"""

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.heatit_wifi_panel.api import (
    HeatitConnectionError,
    HeatitMissingFieldError,
    HeatitProtocolError,
    HeatitResponseError,
)
from custom_components.heatit_wifi_panel.const import (
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MANUFACTURER,
)
from tests.fakes import ABSENT, FakeHeatitClient
from tests.integration.conftest import (
    REFERENCE_DEVICE_ID,
    panel_device,
    setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

INTEGRATION_DIR = Path(__file__).parents[2] / "custom_components" / "heatit_wifi_panel"

#: Everything §6.2 retries. A permanent error here would strand a panel that
#: comes back by itself, which is the common case for all four.
RETRYING_FAILURES = [
    HeatitConnectionError("timed out"),
    HeatitResponseError(404, "Not Found"),
    HeatitProtocolError("a captive page"),
    HeatitMissingFieldError("parameters.heatingSetpoint"),
]


async def test_setup_loads_the_entry_and_polls_once(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    assert patched_client.status_reads == 1
    coordinator = mock_config_entry.runtime_data
    assert coordinator.data.device_id == REFERENCE_DEVICE_ID
    assert coordinator.update_interval is not None
    assert coordinator.update_interval.total_seconds() == DEFAULT_POLL_INTERVAL
    # hass.data is untouched: runtime_data is the only home (§3.4).
    assert DOMAIN not in hass.data


@pytest.mark.usefixtures("patched_client")
async def test_setup_registers_one_device_and_no_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The device stands on its own; the platforms arrive with their tickets."""
    assert await setup_entry(hass, mock_config_entry)

    device = panel_device(hass, mock_config_entry)
    assert device.identifiers == {(DOMAIN, REFERENCE_DEVICE_ID)}
    assert device.connections == {(dr.CONNECTION_NETWORK_MAC, "02:00:00:00:00:01")}
    assert device.manufacturer == MANUFACTURER
    assert device.model == "Heatit WiFi Panel Heater"
    assert device.name == "Näytehuone 1"
    assert device.sw_version == "1.21"
    # The panel serves no web UI, so there is nothing to link to (§2.2).
    assert device.configuration_url is None

    entities = er.async_entries_for_config_entry(
        er.async_get(hass), mock_config_entry.entry_id
    )
    assert entities == []


@pytest.mark.usefixtures("patched_client")
async def test_the_assigned_room_becomes_an_area_suggestion(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A suggestion only: Home Assistant's own area wins from then on (§4.4)."""
    assert await setup_entry(hass, mock_config_entry)

    device = panel_device(hass, mock_config_entry)
    assert device.area_id is not None
    area = ar.async_get(hass).async_get_area(device.area_id)
    assert area is not None
    assert area.name == "Bedroom"


async def test_the_mac_is_normalised_by_core(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The device sends the MAC uppercase with colons; ``connections`` lowercases."""
    patched_client.set_status({"Network.mac": "AA:BB:CC:DD:EE:FF"})

    assert await setup_entry(hass, mock_config_entry)

    device = panel_device(hass, mock_config_entry)
    assert device.connections == {(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}


async def test_an_absent_mac_costs_only_the_connection(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Identity is the *device id*, so the whole ``Network`` block is optional."""
    patched_client.set_status({"Network": ABSENT})

    assert await setup_entry(hass, mock_config_entry)

    device = panel_device(hass, mock_config_entry)
    assert device.connections == set()


async def test_the_name_and_the_room_are_read_once_at_creation(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An app rename simply diverges; it does not reach Home Assistant (§4.4).

    Not only per poll: a reload does not pick it up either, because there is no
    way to tell "the user renamed this in Home Assistant" from "the user never
    touched it", and following the app would silently destroy the first.
    """
    assert await setup_entry(hass, mock_config_entry)
    original_area = panel_device(hass, mock_config_entry)
    patched_client.set_status({"name": "Renamed in the app", "room": "Hallway"})

    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)

    device = panel_device(hass, mock_config_entry)
    assert device.name == "Näytehuone 1"
    assert device.area_id == original_area.area_id
    assert mock_config_entry.title == "Näytehuone 1"


async def test_the_firmware_and_model_are_refreshed_on_a_reload(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Facts about the hardware, not labels the user owns (§3.5)."""
    assert await setup_entry(hass, mock_config_entry)
    patched_client.set_status({"firmware": "1.22"})

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)

    device = panel_device(hass, mock_config_entry)
    assert device.sw_version == "1.22"


@pytest.mark.parametrize("failure", RETRYING_FAILURES)
async def test_setup_retries_every_failure_but_a_foreign_panel(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    failure: Exception,
) -> None:
    patched_client.fail(failure)

    assert not await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_fails_permanently_on_a_foreign_panel(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Retrying can never fix it; the fix is the reconfigure step (§6.2)."""
    patched_client.set_status({"id": "OTHERPANELOTHERPANELXY"})

    assert not await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert mock_config_entry.error_reason_translation_key == "foreign_panel"
    assert mock_config_entry.error_reason_translation_placeholders == {
        "expected_id": REFERENCE_DEVICE_ID,
        "actual_id": "OTHERPANELOTHERPANELXY",
    }


async def test_a_retried_entry_loads_when_the_panel_returns(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    patched_client.fail(HeatitConnectionError("timed out"))
    assert not await setup_entry(hass, mock_config_entry)

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("patched_client")
async def test_unload_releases_the_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


def test_nothing_on_the_setup_path_sleeps() -> None:
    """§3.6: no startup stagger, ever, and no sleep in setup.

    Multi-device restart failures on related Heatit hardware were traced to
    swallowed exceptions and a missing ``ConfigEntryNotReady``, not to the
    device. ``async_config_entry_first_refresh`` and the coordinator's own
    jitter are what replace a stagger, so a ``sleep`` reappearing on this path
    is a regression to the thing that did not work. Asserted over the syntax
    tree, so the word may still be written in prose.
    """
    for name in ("__init__.py", "coordinator.py"):
        tree = ast.parse((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
        slept = [
            node
            for node in ast.walk(tree)
            if (isinstance(node, ast.Name) and node.id == "sleep")
            or (isinstance(node, ast.Attribute) and node.attr == "sleep")
        ]
        assert slept == [], f"{name} sleeps on line {slept[0].lineno}"
