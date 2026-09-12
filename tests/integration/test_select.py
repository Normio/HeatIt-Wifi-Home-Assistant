"""The two selects of §5.2: the standby display and the physical buttons.

Neither is a switch, and for two different reasons. ``temperatureDisplay`` has
two states a user would choose between by name: the standby display shows the
setpoint or the measured temperature. Calling one of them "on" would make the
card ask a question nobody asked. ``disableButtons`` has three states, so a
switch cannot hold it at all: a boolean would silently lose *menu locked*.

Both are **named as the device and the MyHeatit app name them**. The parameter
is called ``disableButtons``; the entity is called Buttons, with *enabled*
first. Turning it into a lock would have a user reading "off" and getting
working buttons.
"""

from typing import TYPE_CHECKING, NamedTuple

import pytest
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID

from custom_components.heatit_wifi_panel.const import POST_WRITE_REFRESH_DELAY
from tests.integration.conftest import advance, entity_id, setup_entry

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from tests.fakes import FakeHeatitClient


class Select(NamedTuple):
    """One select of §5.2, copied instead of read from the module."""

    key: str
    parameter: str
    read_path: str
    options: tuple[str, ...]
    reference: str
    """The option the reference capture reads as."""


class Choice(NamedTuple):
    """One option and the value the panel is sent for it."""

    select: Select
    option: str
    wire: str


STANDBY_DISPLAY = Select(
    key="standby_display",
    parameter="temperatureDisplay",
    read_path="parameters.temperatureDisplay",
    options=("setpoint", "measured_temperature"),
    reference="measured_temperature",
)
BUTTONS = Select(
    key="buttons",
    parameter="disableButtons",
    read_path="parameters.disableButtons",
    options=("enabled", "disabled", "menu_locked"),
    reference="disabled",
)
SELECTS = [STANDBY_DISPLAY, BUTTONS]

#: Every option, and what it puts on the wire: lowercase ``true``/``false`` for
#: the boolean parameter, a bare integer for the three-state one.
CHOICES = [
    Choice(STANDBY_DISPLAY, "setpoint", "false"),
    Choice(STANDBY_DISPLAY, "measured_temperature", "true"),
    Choice(BUTTONS, "enabled", "0"),
    Choice(BUTTONS, "disabled", "1"),
    Choice(BUTTONS, "menu_locked", "2"),
]


def select_id(hass: HomeAssistant, key: str) -> str:
    """Return one select's entity id."""
    return entity_id(hass, SELECT_DOMAIN, key)


def state_of(hass: HomeAssistant, key: str) -> str:
    """Return the option one select currently shows."""
    state = hass.states.get(select_id(hass, key))
    assert state is not None
    return state.state


def options_of(hass: HomeAssistant, key: str) -> list[str]:
    """Return the options one select offers, in the order it offers them."""
    state = hass.states.get(select_id(hass, key))
    assert state is not None
    options: list[str] = state.attributes[ATTR_OPTIONS]
    return options


async def choose(hass: HomeAssistant, key: str, option: str) -> None:
    """Pick an option through the service registry, as a user does."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: select_id(hass, key), ATTR_OPTION: option},
        blocking=True,
    )


@pytest.mark.usefixtures("patched_client")
@pytest.mark.parametrize("row", SELECTS, ids=lambda row: row.key)
async def test_each_select_offers_its_options_and_reads_the_panel(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, row: Select
) -> None:
    """The options are the device's own names, in the device's own order."""
    assert await setup_entry(hass, mock_config_entry)

    assert options_of(hass, row.key) == list(row.options)
    assert state_of(hass, row.key) == row.reference


@pytest.mark.parametrize(
    "choice", CHOICES, ids=lambda choice: f"{choice.select.key}-{choice.option}"
)
async def test_choosing_an_option_writes_the_value_behind_it(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    choice: Choice,
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    await choose(hass, choice.select.key, choice.option)

    assert patched_client.writes == [(choice.select.parameter, choice.wire)]


@pytest.mark.usefixtures("patched_client")
@pytest.mark.parametrize(
    "choice", CHOICES, ids=lambda choice: f"{choice.select.key}-{choice.option}"
)
async def test_every_option_is_a_state_the_select_can_show(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, choice: Choice
) -> None:
    """Each option comes back as the state, so no reading falls off the map.

    One mapping is read both ways round. This is the half a reversed or
    duplicated entry would break: the panel would then answer a value the
    select shows as unknown.
    """
    assert await setup_entry(hass, mock_config_entry)

    await choose(hass, choice.select.key, choice.option)

    assert state_of(hass, choice.select.key) == choice.option


async def test_the_echo_shows_at_once_and_the_refresh_is_the_authority(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """§5.4's uniform optimistic update, on a three-state parameter."""
    assert await setup_entry(hass, mock_config_entry)
    reads = patched_client.status_reads

    await choose(hass, BUTTONS.key, "menu_locked")

    assert state_of(hass, BUTTONS.key) == "menu_locked"
    assert patched_client.status_reads == reads

    patched_client.set_status({BUTTONS.read_path: 2})
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    assert patched_client.status_reads == reads + 1
    assert state_of(hass, BUTTONS.key) == "menu_locked"
