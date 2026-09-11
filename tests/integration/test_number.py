"""The eight config numbers: §5.2's rows, and §5.4's rule about their bounds.

The rule is the reason this file is longer than a table check. **Bounds are
dynamic wherever they come from device state**, so every assertion about one is
made twice: once against the reference panel, and once after moving the fake's
status underneath it. A bound cached at setup passes the first and fails the
second, which is the failure this file exists to catch.

The other half is what reaches the wire. A user sets watts and percent; the
device is sent its own units of 100 W and 10 %, and the registry's per-parameter
step decides what is on the grid — so the write assertions here are made against
``patched_client.writes``, which records the serialised query value.
"""

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.number.const import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.components.number.const import (
    DOMAIN as NUMBER_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.heatit_wifi_panel.const import POST_WRITE_REFRESH_DELAY
from custom_components.heatit_wifi_panel.number import (
    NUMBERS,
    HeatitNumberDescription,
    HeatitPanelNumber,
)
from custom_components.heatit_wifi_panel.registry import PARAMETERS
from tests.fakes import ABSENT
from tests.integration.conftest import advance, entity_id, setup_entry

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from tests.fakes import FakeHeatitClient

#: The reference capture's own values: comfort 19.0, eco 18.0, limits 5.0 and
#: 40.0, calibration 0.0, `loadLimit` and `maxLoad` both 6 — a 600 W panel —
#: and the two brightnesses at 10 and 0, which is 100 % and 0 %.
COMFORT = 19.0
ECO = 18.0


def attributes(hass: HomeAssistant, key: str) -> dict[str, object]:
    """Return one number's state attributes."""
    state = hass.states.get(entity_id(hass, NUMBER_DOMAIN, key))
    assert state is not None
    return dict(state.attributes)


def bounds(hass: HomeAssistant, key: str) -> tuple[object, object]:
    """Return one number's minimum and maximum as Home Assistant reports them."""
    shown = attributes(hass, key)
    return shown[ATTR_MIN], shown[ATTR_MAX]


def value(hass: HomeAssistant, key: str) -> str:
    """Return one number's state."""
    state = hass.states.get(entity_id(hass, NUMBER_DOMAIN, key))
    assert state is not None
    return state.state


async def loaded(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set the entry up and assert the numbers arrived."""
    assert await setup_entry(hass, entry)


async def repoll(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: FakeHeatitClient,
    changes: dict[str, object],
) -> None:
    """Move the panel underneath a loaded entry, by one ordinary poll.

    Deliberately **not** a reload: a reload builds every entity again, so a
    bound computed once at setup would survive one and the assertions below
    would pass against exactly the implementation §5.4 forbids.
    """
    client.set_status(changes)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def set_value(hass: HomeAssistant, key: str, to: float) -> None:
    """Call ``number.set_value`` against one of the panel's numbers."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id(hass, NUMBER_DOMAIN, key), ATTR_VALUE: to},
        blocking=True,
    )


# --- the steps, which are per parameter and not per type --------------------


@pytest.mark.usefixtures("patched_client")
@pytest.mark.parametrize(
    ("key", "step"),
    [
        ("comfort_setpoint", 0.5),
        ("eco_setpoint", 0.5),
        ("minimum_temperature_limit", 0.5),
        ("maximum_temperature_limit", 0.5),
        ("sensor_calibration", 0.1),
        ("load_limit", 100),
        ("active_display_brightness", 10),
        ("standby_display_brightness", 10),
    ],
)
async def test_each_number_carries_its_own_step(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, key: str, step: float
) -> None:
    """§5.2's steps, transcribed: four temperatures do not share one rule."""
    await loaded(hass, mock_config_entry)

    assert attributes(hass, key)[ATTR_STEP] == step


# --- the dynamic bounds (§5.4, §8.5) ----------------------------------------


@pytest.mark.parametrize("key", ["comfort_setpoint", "eco_setpoint"])
async def test_a_setpoint_is_bounded_by_the_limits_as_they_are_now(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    key: str,
) -> None:
    """The limits bound both banks, and they move (§5.4)."""
    await loaded(hass, mock_config_entry)
    assert bounds(hass, key) == (5.0, 40.0)

    await repoll(
        hass,
        mock_config_entry,
        patched_client,
        {
            "parameters.minimumTemperatureLimit": 16.0,
            "parameters.maximumTemperatureLimit": 24.0,
        },
    )

    assert bounds(hass, key) == (16.0, 24.0)


@pytest.mark.parametrize("key", ["comfort_setpoint", "eco_setpoint"])
async def test_a_setpoint_falls_back_to_the_panels_own_bounds(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    key: str,
) -> None:
    """A firmware returning no limits still has two setpoints (§5.3)."""
    patched_client.set_status(
        {
            "parameters.minimumTemperatureLimit": ABSENT,
            "parameters.maximumTemperatureLimit": ABSENT,
        }
    )

    await loaded(hass, mock_config_entry)

    assert bounds(hass, key) == (5.0, 40.0)


async def test_each_limit_stops_half_a_degree_short_of_the_other(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """So Home Assistant never offers a value the device rejects for min >= max."""
    await loaded(hass, mock_config_entry)
    assert bounds(hass, "minimum_temperature_limit") == (5.0, 39.5)
    assert bounds(hass, "maximum_temperature_limit") == (5.5, 40.0)

    await repoll(
        hass,
        mock_config_entry,
        patched_client,
        {
            "parameters.minimumTemperatureLimit": 16.0,
            "parameters.maximumTemperatureLimit": 24.0,
        },
    )

    assert bounds(hass, "minimum_temperature_limit") == (5.0, 23.5)
    assert bounds(hass, "maximum_temperature_limit") == (16.5, 40.0)


async def test_the_load_limit_is_bounded_by_the_rated_load(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """``maxLoad`` is in units of 100 W, and the user is offered watts."""
    await loaded(hass, mock_config_entry)
    assert bounds(hass, "load_limit") == (100, 600.0)

    await repoll(hass, mock_config_entry, patched_client, {"parameters.maxLoad": 15})

    assert bounds(hass, "load_limit") == (100, 1500.0)


async def test_an_unreported_rated_load_leaves_the_registrys_own_ceiling(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """``maxLoad`` is not a registry parameter, so its absence takes no entity."""
    patched_client.set_status({"parameters.maxLoad": ABSENT})

    await loaded(hass, mock_config_entry)

    # 1500 W is the largest model Heatit sells, and §2.4's own ceiling.
    assert bounds(hass, "load_limit") == (100, 1500)


@pytest.mark.usefixtures("patched_client")
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("sensor_calibration", (-6.0, 6.0)),
        ("active_display_brightness", (10, 100)),
        ("standby_display_brightness", (0, 100)),
    ],
)
async def test_a_bound_the_device_does_not_move_is_the_registrys(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    key: str,
    expected: tuple[float, float],
) -> None:
    """§5.2's static ranges, in user units — percent, not the device's tens."""
    await loaded(hass, mock_config_entry)

    assert bounds(hass, key) == expected


@pytest.mark.usefixtures("patched_client")
async def test_a_row_naming_an_enumerated_parameter_refuses_to_be_built(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """``NUMBERS`` is written by hand, so a wrong row is a real mistake.

    An enumerated parameter carries choices rather than bounds and belongs on a
    select. Refusing it is what stops the alternative: silently offering a user
    core's default 0 .. 100 range in place of the panel's own.
    """
    await loaded(hass, mock_config_entry)

    with pytest.raises(ValueError, match="cannot be a number"):
        HeatitPanelNumber(
            mock_config_entry.runtime_data,
            HeatitNumberDescription(key="panel_mode", parameter="panelMode"),
        )


# --- what reaches the wire --------------------------------------------------


@pytest.mark.parametrize(
    ("key", "set_to", "written"),
    [
        ("comfort_setpoint", 21.5, ("heatingSetpoint", "21.5")),
        ("eco_setpoint", 17.0, ("ecoSetpoint", "17.0")),
        ("minimum_temperature_limit", 10.0, ("minimumTemperatureLimit", "10.0")),
        ("maximum_temperature_limit", 30.0, ("maximumTemperatureLimit", "30.0")),
        ("sensor_calibration", -1.1, ("sensorCalibration", "-1.1")),
        # Scaled down to the device's own units, and a bare integer: the panel
        # rejects ``5.0`` where it wants ``5``.
        ("load_limit", 300, ("loadLimit", "3")),
        ("active_display_brightness", 50, ("activeDisplayBrightness", "5")),
        ("standby_display_brightness", 20, ("standbyDisplayBrightness", "2")),
    ],
)
async def test_a_number_writes_its_own_parameter_in_the_devices_units(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    key: str,
    set_to: float,
    written: tuple[str, str],
) -> None:
    """One row, one parameter, and the scale applied on the way out (§5.4)."""
    await loaded(hass, mock_config_entry)

    await set_value(hass, key, set_to)

    assert patched_client.writes == [written]


@pytest.mark.parametrize("mode", [0, 1, 2])
@pytest.mark.parametrize(
    ("key", "parameter"),
    [
        ("comfort_setpoint", "heatingSetpoint"),
        ("eco_setpoint", "ecoSetpoint"),
    ],
)
async def test_a_setpoint_bank_is_written_in_any_panel_mode(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    mode: int,
    key: str,
    parameter: str,
) -> None:
    """Unconditionally, Off included: no mode is read and none is changed.

    Verified safe on a real panel — a comfort write made in Eco is stored and
    does not change regulation (Q14) — and it is the whole reason these two
    numbers exist alongside the climate entity, which can only reach the live
    bank.
    """
    patched_client.set_status({"parameters.panelMode": mode})
    await loaded(hass, mock_config_entry)

    await set_value(hass, key, 20.0)

    assert patched_client.writes == [(parameter, "20.0")]


async def test_an_off_step_value_never_reaches_the_panel(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Core checks the bounds but never the step, so the registry is the guard.

    The error is translated rather than raised raw at whoever called the
    service (§6.4), and no request is emitted at all.
    """
    await loaded(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError) as raised:
        await set_value(hass, "comfort_setpoint", 20.3)

    assert raised.value.translation_key == "invalid_value"
    assert patched_client.writes == []


async def test_a_value_outside_the_dynamic_bounds_is_refused_by_core(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The point of the dynamic maximum: a 600 W panel is never sent 1500 W."""
    await loaded(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError):
        await set_value(hass, "load_limit", 1500)

    assert patched_client.writes == []


# --- the optimistic update --------------------------------------------------


async def test_the_echo_shows_at_once_and_the_refresh_is_the_authority(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """One refresh, at 1.5 s, asserted by advancing the clock (§8.6.5).

    The panel is made to land somewhere other than the echoed value, so the
    closing assertion can only pass if the refresh actually displaced it.
    """
    await loaded(hass, mock_config_entry)
    reads = patched_client.status_reads

    await set_value(hass, "load_limit", 400)

    assert value(hass, "load_limit") == "400.0"
    assert patched_client.status_reads == reads

    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY - 0.5)
    assert patched_client.status_reads == reads

    patched_client.set_status({"parameters.loadLimit": 5})
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    assert patched_client.status_reads == reads + 1
    assert value(hass, "load_limit") == "500.0"

    # And exactly one: the write scheduled a single refresh, not a repeating
    # one, so the next thing to read the panel is the ordinary poll interval.
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)
    assert patched_client.status_reads == reads + 1


@pytest.mark.usefixtures("patched_client")
async def test_the_refresh_wins_over_the_echo(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A write the panel acknowledged and did not apply ends up shown as it is."""
    await loaded(hass, mock_config_entry)

    await set_value(hass, "comfort_setpoint", 21.0)
    assert value(hass, "comfort_setpoint") == "21.0"

    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    # The fake's status still reads 19.0: the panel did not apply it.
    assert value(hass, "comfort_setpoint") == str(COMFORT)


@pytest.mark.usefixtures("patched_client")
async def test_writing_one_limit_moves_the_others_bound_before_the_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A bound is a reading, so the optimistic update reaches it too (§5.4).

    Both halves of the rule meet here: the *write echo* is what every entity
    shows until the refresh, and a bound is read on access rather than cached.
    Without either, a user who has just raised the minimum limit is still
    offered the old floor on the maximum one until the next poll lands.
    """
    await loaded(hass, mock_config_entry)
    assert bounds(hass, "maximum_temperature_limit") == (5.5, 40.0)

    await set_value(hass, "minimum_temperature_limit", 16.0)

    assert bounds(hass, "maximum_temperature_limit") == (16.5, 40.0)


# --- availability -----------------------------------------------------------


async def test_a_vanished_parameter_takes_only_its_own_number(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """§6.3: the entity stays registered and goes unavailable, alone."""
    await loaded(hass, mock_config_entry)

    await repoll(
        hass,
        mock_config_entry,
        patched_client,
        {"parameters.sensorCalibration": ABSENT},
    )

    assert value(hass, "sensor_calibration") == STATE_UNAVAILABLE
    assert value(hass, "comfort_setpoint") == str(COMFORT)
    assert value(hass, "eco_setpoint") == str(ECO)


# --- the table's own shape --------------------------------------------------


def test_every_row_names_a_parameter_the_registry_holds() -> None:
    """A typo in a wire name is an entity that reads nothing and writes nowhere."""
    for description in NUMBERS:
        assert description.parameter in PARAMETERS


def test_the_rows_marked_dynamic_are_the_ones_section_5_4_names() -> None:
    """Transcribed from §5.4: the setpoints, the two limits, the load limit."""
    dynamic = {
        description.key: (
            description.minimum_fn is not None,
            description.maximum_fn is not None,
        )
        for description in NUMBERS
    }
    assert dynamic == {
        "comfort_setpoint": (True, True),
        "eco_setpoint": (True, True),
        "minimum_temperature_limit": (False, True),
        "maximum_temperature_limit": (True, False),
        "sensor_calibration": (False, False),
        "load_limit": (False, True),
        "active_display_brightness": (False, False),
        "standby_display_brightness": (False, False),
    }
