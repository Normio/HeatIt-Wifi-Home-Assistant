"""The base entity's three rules, and the entity table of §5.2.

The rules are the ones every platform would otherwise get subtly different:
which device an entity belongs to, what its unique id is, and when it is
unavailable. They are asserted here once, against the base class itself, rather
than six times against six platforms.

The table is §8.5's: a **test-side literal** transcribed from §5.2 and, by rule,
never derived from the integration's own descriptors — the point is to compare
two independent encodings, so a row is added here by hand when a platform
ships. Its final form is 21 entities, of which 3 are disabled by default.
"""

from typing import TYPE_CHECKING, NamedTuple

import pytest
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er

from custom_components.heatit_wifi_panel.api import HeatitConnectionError
from custom_components.heatit_wifi_panel.const import DOMAIN
from custom_components.heatit_wifi_panel.entity import HeatitWifiPanelEntity
from tests.fakes import ABSENT, FakeHeatitClient
from tests.integration.conftest import REFERENCE_DEVICE_ID, panel_device, setup_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.heatit_wifi_panel.coordinator import (
        HeatitWifiPanelCoordinator,
    )


class Row(NamedTuple):
    """One row of §5.2, as the user meets it."""

    platform: Platform
    key: str
    name: str | None
    device_class: str | None
    unit: str | None
    state_class: str | None
    category: str | None
    enabled: bool
    state: str


#: §5.2, transcribed. The climate entity's name is ``None`` because it takes
#: the device's own — it *is* the panel — and its three measurement columns are
#: empty because a thermostat is not a measurement.
ENTITY_TABLE = [
    Row(
        platform=Platform.CLIMATE,
        key="panel",
        name=None,
        device_class=None,
        unit=None,
        state_class=None,
        category=None,
        enabled=True,
        state=HVACMode.HEAT,
    ),
]


def registry_entries(
    hass: HomeAssistant, entry: MockConfigEntry
) -> dict[str, er.RegistryEntry]:
    """Every entity the entry owns, by unique id."""
    return {
        registered.unique_id: registered
        for registered in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }


@pytest.mark.usefixtures("patched_client")
async def test_setup_creates_exactly_the_entities_the_table_lists(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    assert set(registry_entries(hass, mock_config_entry)) == {
        f"{REFERENCE_DEVICE_ID}-{row.key}" for row in ENTITY_TABLE
    }


@pytest.mark.usefixtures("patched_client")
@pytest.mark.parametrize("row", ENTITY_TABLE, ids=lambda row: row.key)
async def test_each_entity_is_the_one_the_table_describes(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, row: Row
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    registered = registry_entries(hass, mock_config_entry)[
        f"{REFERENCE_DEVICE_ID}-{row.key}"
    ]
    assert registered.domain == row.platform
    assert registered.original_name == row.name
    assert registered.entity_category == row.category
    assert (registered.disabled_by is None) == row.enabled

    state = hass.states.get(registered.entity_id)
    assert state is not None
    assert state.state == row.state
    assert state.attributes.get("device_class") == row.device_class
    assert state.attributes.get("unit_of_measurement") == row.unit
    assert state.attributes.get("state_class") == row.state_class


# --- the base entity's rules ------------------------------------------------


async def loaded(
    hass: HomeAssistant, entry: MockConfigEntry
) -> HeatitWifiPanelCoordinator:
    """Set the entry up and hand back its coordinator."""
    assert await setup_entry(hass, entry)
    coordinator: HeatitWifiPanelCoordinator = entry.runtime_data
    return coordinator


@pytest.mark.usefixtures("patched_client")
async def test_an_entity_is_named_by_its_key_on_both_sides(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The key is the unique-id suffix *and* the translation key (§5.2)."""
    coordinator = await loaded(hass, mock_config_entry)

    entity = HeatitWifiPanelEntity(coordinator, "probe")

    assert entity.unique_id == f"{REFERENCE_DEVICE_ID}-probe"
    assert entity.translation_key == "probe"
    assert entity.has_entity_name is True


@pytest.mark.usefixtures("patched_client")
async def test_an_entity_joins_the_device_by_identifiers_alone(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Repeating the device's name here would undo a rename on every restart.

    The device is registered from the first status in ``__init__.py``, where
    ``name`` and the *assigned room* are spent once (§4.4).
    """
    coordinator = await loaded(hass, mock_config_entry)
    device = panel_device(hass, mock_config_entry)

    entity = HeatitWifiPanelEntity(coordinator, "probe")

    assert entity.device_info == {"identifiers": {(DOMAIN, REFERENCE_DEVICE_ID)}}
    assert device.identifiers == {(DOMAIN, REFERENCE_DEVICE_ID)}


async def test_a_vanished_read_path_takes_only_its_own_entity(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """§6.3: one absence is one unavailable entity, and nothing else moves."""
    coordinator = await loaded(hass, mock_config_entry)
    reads_the_parameter = HeatitWifiPanelEntity(
        coordinator, "probe", read_path="parameters.sensorCalibration"
    )
    reads_nothing = HeatitWifiPanelEntity(coordinator, "writes-only")
    assert reads_the_parameter.available is True

    patched_client.set_status({"parameters.sensorCalibration": ABSENT})
    await coordinator.async_refresh()

    assert reads_the_parameter.available is False
    assert reads_nothing.available is True


async def test_nothing_stays_available_while_the_poll_is_failing(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The poll is the sole judge, the reset buttons included (§6.3)."""
    coordinator = await loaded(hass, mock_config_entry)
    entity = HeatitWifiPanelEntity(coordinator, "writes-only")
    patched_client.fail(HeatitConnectionError("timed out"))

    await coordinator.async_refresh()

    assert entity.available is False
