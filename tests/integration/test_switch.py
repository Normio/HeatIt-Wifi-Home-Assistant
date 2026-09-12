"""The two switches of §5.2: open window detection and the external sensor.

Two booleans the panel's own display and the MyHeatit app expose. One of them
is the one asymmetry in the parameter registry: ``openWindowDetection`` is
**read nested** under ``parameters.OWD`` and **written flat**. The write key is
asserted here as well as at the client seam. The switch a user touches is what
would silently write nothing if the two diverged.

The external sensor is the parameter whose *write echo* lies (§6.5, register
Q58). With no sensor paired, the panel acknowledges ``sensorMode=true`` and
does not apply it. The switch is exposed anyway: the write does nothing and is
not dangerous. A user sees §5.4's uniform optimistic update run its course. The
switch is on at once and off again at the 1.5 s refresh, with one warning in
the log and nothing after it.
"""

import logging
from typing import TYPE_CHECKING, NamedTuple

import pytest
from homeassistant.components.switch.const import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)

from custom_components.heatit_wifi_panel.const import DOMAIN, POST_WRITE_REFRESH_DELAY
from tests.integration.conftest import advance, entity_id, setup_entry

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from tests.fakes import FakeHeatitClient

LOGGER_NAME = f"custom_components.{DOMAIN}"


class Switch(NamedTuple):
    """One switch of §5.2, copied instead of read from the module."""

    key: str
    parameter: str
    """The wire name: the key a write carries, which is not the read path."""

    read_path: str


OPEN_WINDOW_DETECTION = Switch(
    key="open_window_detection",
    parameter="openWindowDetection",
    read_path="parameters.OWD.openWindowDetection",
)
EXTERNAL_SENSOR = Switch(
    key="external_sensor",
    parameter="sensorMode",
    read_path="parameters.sensorMode",
)
SWITCHES = [OPEN_WINDOW_DETECTION, EXTERNAL_SENSOR]

#: Turning a switch on and off, and the lowercase word each puts on the wire.
FLIPS = [(SERVICE_TURN_ON, "true"), (SERVICE_TURN_OFF, "false")]


def switch_id(hass: HomeAssistant, key: str) -> str:
    """Return one switch's entity id."""
    return entity_id(hass, SWITCH_DOMAIN, key)


def state_of(hass: HomeAssistant, key: str) -> str:
    """Return one switch's state."""
    state = hass.states.get(switch_id(hass, key))
    assert state is not None
    return state.state


async def call(hass: HomeAssistant, key: str, service: str) -> None:
    """Flip one switch through the service registry, as a user does."""
    await hass.services.async_call(
        SWITCH_DOMAIN,
        service,
        {ATTR_ENTITY_ID: switch_id(hass, key)},
        blocking=True,
    )


@pytest.mark.parametrize("row", SWITCHES, ids=lambda row: row.key)
async def test_each_switch_reads_its_own_parameter(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patched_client: FakeHeatitClient,
    row: Switch,
) -> None:
    """Both read ``false`` on the reference panel. Both follow their own path."""
    assert await setup_entry(hass, mock_config_entry)
    assert state_of(hass, row.key) == STATE_OFF

    patched_client.set_status({row.read_path: True})
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert state_of(hass, row.key) == STATE_ON


@pytest.mark.parametrize(("service", "wire"), FLIPS)
async def test_open_window_detection_is_written_flat(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    service: str,
    wire: str,
) -> None:
    """Read nested at ``parameters.OWD``, written flat as ``openWindowDetection``."""
    assert await setup_entry(hass, mock_config_entry)

    await call(hass, OPEN_WINDOW_DETECTION.key, service)

    assert patched_client.writes == [(OPEN_WINDOW_DETECTION.parameter, wire)]


@pytest.mark.parametrize(("service", "wire"), FLIPS)
async def test_the_external_sensor_writes_sensor_mode(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    service: str,
    wire: str,
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    await call(hass, EXTERNAL_SENSOR.key, service)

    assert patched_client.writes == [(EXTERNAL_SENSOR.parameter, wire)]


async def test_the_echo_shows_at_once_and_the_refresh_is_the_authority(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """§5.4's uniform optimistic update, on a switch the panel does apply."""
    assert await setup_entry(hass, mock_config_entry)
    reads = patched_client.status_reads

    await call(hass, OPEN_WINDOW_DETECTION.key, SERVICE_TURN_ON)

    assert state_of(hass, OPEN_WINDOW_DETECTION.key) == STATE_ON
    assert patched_client.status_reads == reads

    patched_client.set_status({OPEN_WINDOW_DETECTION.read_path: True})
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    assert patched_client.status_reads == reads + 1
    assert state_of(hass, OPEN_WINDOW_DETECTION.key) == STATE_ON


async def test_an_inert_external_sensor_write_flips_back_and_warns_once(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Register Q58, as a user sees it: on, then off, then nothing more.

    The echo says ``true``, and the panel's status goes on saying ``false``.
    §5.4's one rule is kept; there is no per-parameter honesty flag. The
    *silent undo* warning shows the exception, once per parameter per entry
    lifetime and debug from then on (§6.5).
    """
    assert await setup_entry(hass, mock_config_entry)
    patched_client.echoes[EXTERNAL_SENSOR.parameter] = True

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        for _ in range(2):
            await call(hass, EXTERNAL_SENSOR.key, SERVICE_TURN_ON)
            assert state_of(hass, EXTERNAL_SENSOR.key) == STATE_ON
            await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)
            assert state_of(hass, EXTERNAL_SENSOR.key) == STATE_OFF

    undone = [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and "acknowledged" in record.getMessage()
    ]
    assert [record.levelno for record in undone] == [logging.WARNING, logging.DEBUG]
    assert EXTERNAL_SENSOR.parameter in undone[0].getMessage()
