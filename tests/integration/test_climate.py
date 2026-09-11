"""The climate entity: §5.3's table, row by row, and ADR-0004's consequences.

The panel has one three-way *panel mode* and two *setpoint banks*; Home
Assistant's climate entity has one target temperature. What that costs is
asserted here: ``hvac_modes`` is fixed at ``[OFF, HEAT]``, Eco is a preset, and
``target_temperature`` follows the *live setpoint* — which means it jumps when
the preset changes and is ``None`` while the panel is Off.

The *live bank* is re-read from device state **inside** every call, so a mode
change racing a ``set_temperature`` cannot write the wrong bank; the tests that
pass ``hvac_mode`` alongside a temperature are what pin that order.
"""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.climate.const import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    ATTR_TARGET_TEMP_STEP,
    PRESET_COMFORT,
    PRESET_ECO,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import async_fire_time_changed_exact

from custom_components.heatit_wifi_panel.api import HeatitConnectionError
from custom_components.heatit_wifi_panel.const import POST_WRITE_REFRESH_DELAY
from tests.integration.conftest import setup_entry

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from tests.fakes import FakeHeatitClient

#: The one climate entity, named after the device because ``_attr_name`` is
#: ``None`` — this entity *is* the panel (§5.2).
ENTITY_ID = "climate.naytehuone_1"

#: The reference capture's own values: Heating, comfort 19.0, eco 18.0, room
#: 23.0, relay Idle, limits 5.0 to 40.0.
COMFORT = 19.0
ECO = 18.0


async def loaded(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set the entry up and assert the climate entity arrived."""
    assert await setup_entry(hass, entry)
    assert hass.states.get(ENTITY_ID) is not None


def attributes(hass: HomeAssistant) -> dict[str, Any]:
    """Return the climate entity's state attributes."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    return dict(state.attributes)


async def advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move every clock on by ``seconds``, and let what that fires run.

    Both clocks, which is why the freezer is here rather than a bare
    ``async_fire_time_changed``: the refresh is scheduled against the event
    loop's, and the *write echo* it judges is held against ``monotonic()``. The
    *exact* variant fires nothing extra — the ordinary one adds half a second
    to cover the coordinator's scheduling jitter, and half a second is a third
    of the delay under test.
    """
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed_exact(hass)
    await hass.async_block_till_done()


async def call(hass: HomeAssistant, service: str, **data: object) -> None:
    """Call one of the climate services against the panel."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )


# --- the fixed shape --------------------------------------------------------


@pytest.mark.usefixtures("patched_client")
async def test_the_capability_list_is_fixed_and_never_computed(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A list computed from live state would flap; ADR-0004 forbids it."""
    await loaded(hass, mock_config_entry)

    assert attributes(hass)[ATTR_HVAC_MODES] == [HVACMode.OFF, HVACMode.HEAT]
    assert attributes(hass)[ATTR_PRESET_MODES] == [PRESET_COMFORT, PRESET_ECO]


@pytest.mark.usefixtures("patched_client")
async def test_turn_on_and_turn_off_are_declared_explicitly(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The 2024.2 shim that inferred them was deleted in 2025.1 (§5.3).

    Without them an area-targeted ``climate.turn_on`` silently skips this
    entity, with no warning anywhere.
    """
    await loaded(hass, mock_config_entry)

    assert attributes(hass)[ATTR_SUPPORTED_FEATURES] == (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )


@pytest.mark.usefixtures("patched_client")
async def test_the_reference_panel_reads_as_a_thermostat(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Every §5.3 reading, from the one status a real panel produced."""
    await loaded(hass, mock_config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_COMFORT
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 23.0
    assert state.attributes[ATTR_TEMPERATURE] == COMFORT
    assert state.attributes[ATTR_TARGET_TEMP_STEP] == 0.5
    assert state.attributes[ATTR_HVAC_ACTION] is HVACAction.IDLE


# --- the panel mode ---------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(0, HVACMode.OFF), (1, HVACMode.HEAT), (2, HVACMode.HEAT)],
)
async def test_eco_is_a_preset_and_never_a_third_hvac_mode(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    mode: int,
    expected: HVACMode,
) -> None:
    """The enum is closed and the state property raises on a non-member."""
    patched_client.set_status({"parameters.panelMode": mode})

    await loaded(hass, mock_config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == expected


@pytest.mark.parametrize(
    ("mode", "expected"), [(0, None), (1, PRESET_COMFORT), (2, PRESET_ECO)]
)
async def test_the_preset_follows_the_panel_mode(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    mode: int,
    expected: str | None,
) -> None:
    patched_client.set_status({"parameters.panelMode": mode})

    await loaded(hass, mock_config_entry)

    assert attributes(hass)[ATTR_PRESET_MODE] == expected


async def test_turning_off_writes_off(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_TURN_OFF)

    assert patched_client.writes == [("panelMode", "0")]


@pytest.mark.parametrize("service", [SERVICE_TURN_ON, SERVICE_SET_HVAC_MODE])
async def test_turning_on_always_lands_in_heating(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    service: str,
) -> None:
    """The panel has no "on" verb and remembers nothing, so neither do we."""
    patched_client.set_status({"parameters.panelMode": 0})
    await loaded(hass, mock_config_entry)

    extra = {"hvac_mode": HVACMode.HEAT} if service == SERVICE_SET_HVAC_MODE else {}
    await call(hass, service, **extra)

    assert patched_client.writes == [("panelMode", "1")]


@pytest.mark.parametrize("mode", [1, 2])
async def test_heat_while_already_on_is_a_no_op(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    mode: int,
) -> None:
    """Never flips Eco to comfort: ``HEAT`` is already true in both (§5.3)."""
    patched_client.set_status({"parameters.panelMode": mode})
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)

    assert patched_client.writes == []


@pytest.mark.parametrize(
    ("preset", "written"), [(PRESET_COMFORT, "1"), (PRESET_ECO, "2")]
)
async def test_a_preset_sends_the_mode_and_nothing_else(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    preset: str,
    written: str,
) -> None:
    """Never a temperature alongside it (§5.3)."""
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_SET_PRESET_MODE, preset_mode=preset)

    assert patched_client.writes == [("panelMode", written)]


@pytest.mark.parametrize(
    ("preset", "written"), [(PRESET_COMFORT, "1"), (PRESET_ECO, "2")]
)
async def test_a_preset_chosen_while_off_turns_the_panel_on_in_it(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    preset: str,
    written: str,
) -> None:
    """A preset is an explicit choice of on-mode (ADR-0004)."""
    patched_client.set_status({"parameters.panelMode": 0})
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_SET_PRESET_MODE, preset_mode=preset)

    assert patched_client.writes == [("panelMode", written)]


# --- the live setpoint ------------------------------------------------------


@pytest.mark.parametrize(("mode", "expected"), [(0, None), (1, COMFORT), (2, ECO)])
async def test_the_target_temperature_is_the_live_setpoint(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    mode: int,
    expected: float | None,
) -> None:
    """It jumps when the preset changes, and is blank while Off."""
    patched_client.set_status({"parameters.panelMode": mode})

    await loaded(hass, mock_config_entry)

    assert attributes(hass)[ATTR_TEMPERATURE] == expected


@pytest.mark.parametrize(("mode", "bank"), [(1, "heatingSetpoint"), (2, "ecoSetpoint")])
async def test_a_setpoint_write_lands_in_the_live_bank(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    mode: int,
    bank: str,
) -> None:
    patched_client.set_status({"parameters.panelMode": mode})
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)

    assert patched_client.writes == [(bank, "21.0")]


async def test_an_off_grid_temperature_is_refused_before_any_request(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The panel would snap 21.3 to the 0.5 grid; the registry refuses instead.

    Core validates a service call against ``min_temp`` and ``max_temp`` but not
    against ``target_temperature_step``, so the value arrives here as written
    and the refusal is what the caller sees — translated, not a raw traceback.
    """
    await loaded(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, SERVICE_SET_TEMPERATURE, temperature=21.3)

    assert raised.value.translation_key == "invalid_value"
    assert patched_client.writes == []


async def test_a_setpoint_write_while_off_refuses_loudly(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The floor thermostats drop it silently; we refuse so an automation learns."""
    patched_client.set_status({"parameters.panelMode": 0})
    await loaded(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as raised:
        await call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)

    assert raised.value.translation_key == "set_temperature_while_off"
    assert patched_client.writes == []


@pytest.mark.parametrize(
    ("mode", "bank"), [(0, "heatingSetpoint"), (2, "heatingSetpoint")]
)
async def test_a_mode_passed_with_the_temperature_switches_first(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    mode: int,
    bank: str,
) -> None:
    """Core passes ``hvac_mode`` through unvalidated and unapplied (§5.3).

    From Off the mode write is the one that makes the bank live; from Eco
    ``HEAT`` is a no-op and the *live bank* is still eco — so this is also the
    case that would write the wrong bank if the bank were cached.
    """
    patched_client.set_status({"parameters.panelMode": mode})
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0, hvac_mode=HVACMode.HEAT)

    written = [key for key, _ in patched_client.writes]
    assert written[-1] == ("ecoSetpoint" if mode == 2 else bank)


async def test_the_bank_is_re_read_inside_the_call(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Turning on from Off inside the same call makes comfort the live bank."""
    patched_client.set_status({"parameters.panelMode": 0})
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0, hvac_mode=HVACMode.HEAT)

    assert patched_client.writes == [("panelMode", "1"), ("heatingSetpoint", "21.0")]


# --- the limits, from the device --------------------------------------------


@pytest.mark.usefixtures("patched_client")
async def test_the_limits_are_the_devices_own(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    await loaded(hass, mock_config_entry)

    assert attributes(hass)[ATTR_MIN_TEMP] == 5.0
    assert attributes(hass)[ATTR_MAX_TEMP] == 40.0


async def test_the_limits_follow_the_device_with_no_clamping(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The device bounds both banks itself; narrowing clamps on the device."""
    await loaded(hass, mock_config_entry)
    patched_client.set_status(
        {
            "parameters.minimumTemperatureLimit": 16.0,
            "parameters.maximumTemperatureLimit": 24.0,
        }
    )

    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert attributes(hass)[ATTR_MIN_TEMP] == 16.0
    assert attributes(hass)[ATTR_MAX_TEMP] == 24.0


async def test_an_absent_limit_falls_back_to_the_panels_own_bounds(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A limit is an *optional parameter*; the bounds it narrows are not.

    The registry validates every setpoint write against those same two numbers,
    so a card offering them is offering exactly what the panel will accept.
    """
    patched_client.set_status(
        {
            "parameters.minimumTemperatureLimit": None,
            "parameters.maximumTemperatureLimit": None,
        }
    )

    await loaded(hass, mock_config_entry)

    assert attributes(hass)[ATTR_MIN_TEMP] == 5.0
    assert attributes(hass)[ATTR_MAX_TEMP] == 40.0


# --- hvac_action, from the relay --------------------------------------------


@pytest.mark.parametrize(
    ("relay", "mode", "expected"),
    [
        ("Heating", 0, HVACAction.HEATING),
        ("Heating", 1, HVACAction.HEATING),
        ("Heating", 2, HVACAction.HEATING),
        ("Idle", 0, HVACAction.OFF),
        ("Idle", 1, HVACAction.IDLE),
        ("Idle", 2, HVACAction.IDLE),
    ],
)
async def test_the_action_comes_from_the_relay_and_never_from_power(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    relay: str,
    mode: int,
    expected: HVACAction,
) -> None:
    """``state`` leads ``currentPower`` by ~15 s (Q20), so power cannot say it.

    ``Heating`` while Off stays ``HEATING``: the element is on, and that has to
    survive a future firmware whose frost protection heats in any mode.
    """
    patched_client.set_status(
        {"state": relay, "parameters.panelMode": mode, "currentPower": 600}
    )

    await loaded(hass, mock_config_entry)

    assert attributes(hass)[ATTR_HVAC_ACTION] is expected


# --- the optimistic update --------------------------------------------------


async def test_the_echo_shows_at_once_and_the_refresh_is_the_authority(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """One refresh, at 1.5 s, asserted by advancing the clock (§8.6.5)."""
    await loaded(hass, mock_config_entry)
    reads = patched_client.status_reads

    await call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)

    assert attributes(hass)[ATTR_TEMPERATURE] == 21.0
    assert patched_client.status_reads == reads

    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY - 0.5)
    assert patched_client.status_reads == reads

    # The panel took the write; the refresh confirms it rather than trusting it.
    patched_client.set_status({"parameters.heatingSetpoint": 21.0})
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    assert patched_client.status_reads == reads + 1
    assert attributes(hass)[ATTR_TEMPERATURE] == 21.0


@pytest.mark.usefixtures("patched_client")
async def test_the_refresh_wins_over_the_echo(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A write the panel acknowledged and did not apply ends up shown as it is."""
    await loaded(hass, mock_config_entry)

    await call(hass, SERVICE_SET_PRESET_MODE, preset_mode=PRESET_ECO)
    assert attributes(hass)[ATTR_PRESET_MODE] == PRESET_ECO

    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    # The fake's status still reads mode 1: the panel did not apply it.
    assert attributes(hass)[ATTR_PRESET_MODE] == PRESET_COMFORT


# --- availability -----------------------------------------------------------


async def test_the_entity_goes_unavailable_on_the_first_failed_poll(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The poll is the sole judge (§6.1); a failed write never decides."""
    await loaded(hass, mock_config_entry)
    patched_client.fail(HeatitConnectionError("timed out"))

    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
