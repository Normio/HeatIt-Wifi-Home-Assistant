"""The five sensors of §5.2, and the energy rules of §5.5.

The entity table in ``test_entity.py`` already pins the device classes, the
units, the state classes, the categories and which row is disabled. None of
that is repeated here. This file asserts the behaviour behind those rows. Each
sensor follows its own reading. The energy sensor claims no ``last_reset``. The
signal strength is the panel's own signed number or nothing at all. A reading
this firmware does not return costs exactly one sensor.
"""

import logging
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er

from custom_components.heatit_wifi_panel import sensor
from custom_components.heatit_wifi_panel.sensor import SENSORS, HeatitPanelSensor
from tests.fakes import ABSENT, FakeHeatitClient
from tests.integration.conftest import (
    REFERENCE_DEVICE_ID,
    entity_id,
    setup_entry,
)
from tests.integration.test_entity import ENTITY_TABLE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.heatit_wifi_panel.coordinator import (
        HeatitWifiPanelCoordinator,
    )

#: Every sensor that can be absent, with the read path §5.2 gives it. The room
#: temperature is missing on purpose: it is *required core*, so a status without
#: it is not a status. The poll fails and no sensor goes away.
OPTIONAL_READINGS = [
    ("power", "currentPower"),
    ("energy", "totalConsumption"),
    ("signal_strength", "Network.wifiSignalStrength"),
    ("open_window_time_remaining", "parameters.OWD.activeTime"),
]


def description(key: str) -> sensor.HeatitSensorEntityDescription:
    """Return the shipped description for one sensor key."""
    return next(item for item in SENSORS if item.key == key)


def sensor_id(hass: HomeAssistant, key: str) -> str:
    """Return one sensor's entity id, read from the registry."""
    return entity_id(hass, SENSOR_DOMAIN, key)


def unique_ids(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    """Return every unique id the entry owns."""
    return {
        registered.unique_id
        for registered in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }


async def loaded(
    hass: HomeAssistant, entry: MockConfigEntry
) -> HeatitWifiPanelCoordinator:
    """Set the entry up and return its coordinator."""
    assert await setup_entry(hass, entry)
    coordinator: HeatitWifiPanelCoordinator = entry.runtime_data
    return coordinator


def test_a_read_only_platform_serialises_nothing() -> None:
    """§3.5: nothing here writes, so there is nothing to hold a queue for."""
    assert sensor.PARALLEL_UPDATES == 0


@pytest.mark.parametrize(
    ("key", "read_path", "reading", "state"),
    [
        ("temperature", "roomTemperature", 21.5, "21.5"),
        ("power", "currentPower", 591, "591.0"),
        ("energy", "totalConsumption", 1.24, "1.24"),
        ("open_window_time_remaining", "parameters.OWD.activeTime", 900, "900"),
    ],
)
async def test_each_sensor_follows_its_own_reading(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    key: str,
    read_path: str,
    reading: float,
    state: str,
) -> None:
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.set_status({read_path: reading})

    await coordinator.async_refresh()

    reported = hass.states.get(sensor_id(hass, key))
    assert reported is not None
    assert reported.state == state


@pytest.mark.usefixtures("patched_client")
async def test_the_energy_sensor_claims_no_last_reset(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """§5.5: the counter is zeroed from the app too, and we never learn when.

    ``total_increasing``, which the entity table pins, is the state class that
    needs no such attribute. A ``last_reset`` would be a claim about a moment
    Home Assistant only knows when it pressed the button itself. It would be
    wrong the first time anyone else pressed one.
    """
    await loaded(hass, mock_config_entry)

    reported = hass.states.get(sensor_id(hass, "energy"))
    assert reported is not None
    assert "last_reset" not in reported.attributes


@pytest.mark.parametrize(
    ("reading", "value"),
    [
        ("-66dBm", -66),
        ("-5 DBM", -5),
        # No sign fix-up: the device sends a signed value, so an unsigned one
        # is reported as it came, not guessed at.
        ("67dBm", 67),
        ("strong", None),
    ],
)
async def test_the_signal_strength_is_the_panels_own_number_or_nothing(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    reading: str,
    value: int | None,
) -> None:
    """A reading we cannot parse is *unknown*, never an exception.

    The sensor is built here instead of read out of ``hass``. §5.2 has it
    disabled by default as a noisy diagnostic, so it has no state until a user
    enables it. Under test is the reading, not the registry.
    """
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.set_status({"Network.wifiSignalStrength": reading})
    await coordinator.async_refresh()

    with caplog.at_level(logging.DEBUG):
        entity = HeatitPanelSensor(coordinator, description("signal_strength"))
        assert entity.native_value == value

    # A value we could not read is still a value the panel returned. So the
    # entity stays available and only its own state is unknown (§6.3).
    assert entity.available is True
    assert (value is None) == any(
        "wifiSignalStrength" in record.message for record in caplog.records
    )


@pytest.mark.parametrize(("key", "read_path"), OPTIONAL_READINGS)
async def test_a_reading_absent_at_setup_makes_no_entity(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    key: str,
    read_path: str,
) -> None:
    """§5.4: presence is decided by the first status, and costs one entity.

    §8.5 wants the other half said out loud: *every other entity present*. So
    the surviving set is compared against §5.2's full table less this row.
    """
    patched_client.set_status({read_path: ABSENT})

    assert await setup_entry(hass, mock_config_entry)

    assert unique_ids(hass, mock_config_entry) == {
        f"{REFERENCE_DEVICE_ID}-{row.key}" for row in ENTITY_TABLE if row.key != key
    }


async def test_a_reading_that_vanishes_takes_only_its_own_sensor(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """§6.3, against a path the *parameter registry* knows nothing about."""
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.set_status({"currentPower": ABSENT})

    await coordinator.async_refresh()

    power = hass.states.get(sensor_id(hass, "power"))
    temperature = hass.states.get(sensor_id(hass, "temperature"))
    assert power is not None
    assert temperature is not None
    assert power.state == STATE_UNAVAILABLE
    assert temperature.state != STATE_UNAVAILABLE


async def test_a_reading_of_the_wrong_type_is_unknown_rather_than_an_error(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The path resolves, so the sensor is there. The value is not a number."""
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.set_status({"currentPower": "lots"})

    await coordinator.async_refresh()

    reported = hass.states.get(sensor_id(hass, "power"))
    assert reported is not None
    assert reported.state == STATE_UNKNOWN
