"""The two buttons of §5.2, and the reset verification of §5.5.

Both buttons discard device state on purpose. One zeroes the *energy
counter*, the other puts every setting back to its default, so both ship
**disabled by default**. A button entity has no confirmation dialog, and §5.4
makes opt-in the only guard the platform offers for a press that throws
something away.

The verification is the other half of the file. A parameter write has a *write
echo* to compare against. A reset has none, so the only check available is
whether the counter dropped. That buys one warning when the panel acknowledged
a reset and the counter did not move. It never complains about a drop Home
Assistant did not cause. A reset from the MyHeatit app is a valid act, not the
device going wrong.
"""

import logging
from typing import TYPE_CHECKING, NamedTuple

import pytest
from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button.const import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er

from custom_components.heatit_wifi_panel.api import TOTAL_CONSUMPTION
from custom_components.heatit_wifi_panel.button import BUTTONS, HeatitPanelButton
from custom_components.heatit_wifi_panel.const import (
    DOMAIN,
    POST_WRITE_REFRESH_DELAY,
    RESET_VERIFY_DELAY,
)
from tests.fakes import ABSENT
from tests.integration.conftest import (
    REFERENCE_DEVICE_ID,
    advance,
    entity_id,
    setup_entry,
)

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.heatit_wifi_panel import button
    from custom_components.heatit_wifi_panel.coordinator import (
        HeatitWifiPanelCoordinator,
    )
    from tests.fakes import FakeHeatitClient

LOGGER_NAME = f"custom_components.{DOMAIN}"

#: A reading well above zero, so the *energy counter* has nowhere to go from
#: it but down. The reference panel reports ``0.00``, which is the one reading
#: §5.5 has nothing to verify against.
BANKED_KWH = 4.32


class Button(NamedTuple):
    """One button of §5.2, written out instead of read from the module."""

    key: str
    reset: str
    """Which of the client's two resets the press must reach."""


RESET_ENERGY = Button(key="reset_energy", reset="kwh")
RESTORE_DEFAULTS = Button(key="restore_defaults", reset="settings")
BUTTON_ROWS = [RESET_ENERGY, RESTORE_DEFAULTS]


def description(key: str) -> button.HeatitButtonDescription:
    """Return the shipped description for one button key."""
    return next(item for item in BUTTONS if item.key == key)


async def loaded(
    hass: HomeAssistant, entry: MockConfigEntry
) -> HeatitWifiPanelCoordinator:
    """Set the entry up and hand back its coordinator."""
    assert await setup_entry(hass, entry)
    coordinator: HeatitWifiPanelCoordinator = entry.runtime_data
    return coordinator


async def press(
    hass: HomeAssistant, entry: MockConfigEntry, key: str
) -> HeatitWifiPanelCoordinator:
    """Press one button by building it, the way a disabled entity is reached.

    Both buttons ship disabled, so neither has a state or an entity id until a
    user enables one. These tests are about what a press *does*, not the
    registry. The press through the service registry, enabling included, is
    its own test below.
    """
    coordinator = await loaded(hass, entry)
    await HeatitPanelButton(coordinator, description(key)).async_press()
    return coordinator


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return this integration's own lines at warning or above.

    ``caplog`` captures whatever reaches the root logger, Home Assistant's
    untested-custom-integration warning included, and §7.2 is a table about
    *our* lines.
    """
    return [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno >= logging.WARNING
    ]


def reset_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return every line this integration wrote about an energy reset."""
    return [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and "reset" in record.getMessage()
    ]


# --- the two buttons --------------------------------------------------------


@pytest.mark.parametrize("row", BUTTON_ROWS, ids=lambda row: row.key)
async def test_each_button_sends_its_own_reset_once(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    row: Button,
) -> None:
    """One press, one request: a reset is never retried (§3.6).

    The ``DELETE`` each press becomes on the wire,
    ``/api/reset/kwh?resetKwh=Reset`` and ``/api/reset/settings``, is asserted
    at the HTTP seam. The query parameter and the bare path are the client's
    business (§8.4).
    """
    await press(hass, mock_config_entry, row.key)

    assert patched_client.resets == [row.reset]


@pytest.mark.parametrize("row", BUTTON_ROWS, ids=lambda row: row.key)
@pytest.mark.usefixtures("patched_client")
async def test_both_buttons_ship_disabled(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, row: Button
) -> None:
    """§5.4's opt-in rule, for the two presses that discard device state.

    A button entity gets no confirmation dialog, so this is the only guard
    Home Assistant offers. The entity is registered either way, so a user
    enables one with a switch, not a reload they have to know about.
    """
    assert await setup_entry(hass, mock_config_entry)

    registered = er.async_get(hass).async_get_entity_id(
        BUTTON_DOMAIN, DOMAIN, f"{REFERENCE_DEVICE_ID}-{row.key}"
    )
    assert registered is not None
    entry = er.async_get(hass).async_get(registered)
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.parametrize("row", BUTTON_ROWS, ids=lambda row: row.key)
async def test_a_button_a_user_enabled_presses_through_the_service_registry(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    row: Button,
) -> None:
    """The path a user walks: enable the entity, then press it."""
    assert await setup_entry(hass, mock_config_entry)
    er.async_get(hass).async_update_entity(
        entity_id(hass, BUTTON_DOMAIN, row.key), disabled_by=None
    )
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: entity_id(hass, BUTTON_DOMAIN, row.key)},
        blocking=True,
    )

    assert patched_client.resets == [row.reset]


async def test_a_settings_reset_lets_the_staggered_state_settle_itself(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """It applies over about 5 s, so the 1.5 s refresh catches it half-way (§5.2).

    A half-applied state costs no warning and no second request. The refresh
    reports whatever the panel says at that moment and a later poll carries
    the rest. A reset is one request, and the poll stays the only thing that
    decides. A partial state is the *hardest* case for that rule, so it is the
    one set up here. On the panel itself the 1.5 s refresh saw the pre-reset
    state instead (§15, 2026-09-11), the easier half of the same rule.
    """
    coordinator = await press(hass, mock_config_entry, RESTORE_DEFAULTS.key)
    reads = patched_client.status_reads

    # Half-way through the spread-out apply: the setpoint is back to its
    # default and the brightness has not moved yet.
    patched_client.set_status({"parameters.heatingSetpoint": 21.0})
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    assert patched_client.status_reads == reads + 1
    assert coordinator.numeric("heatingSetpoint") == 21.0
    assert patched_client.resets == [RESTORE_DEFAULTS.reset]
    assert warnings_of(caplog) == []


# --- the energy reset, verified at a later poll -----------------------------


async def test_a_reset_the_counter_did_not_follow_warns_once(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§5.5: a non-zero reading that did not fall is one warning, then debug.

    The warning names both numbers, because "the reset did not take" is only
    useful next to what the counter read before and reads now.
    """
    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH})

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        coordinator = await press(hass, mock_config_entry, RESET_ENERGY.key)
        await advance(hass, freezer, RESET_VERIFY_DELAY)
        await coordinator.async_refresh()

        judged = reset_lines(caplog)
        assert [record.levelno for record in judged] == [logging.WARNING]
        assert str(BANKED_KWH) in judged[0].getMessage()

        await HeatitPanelButton(
            coordinator, description(RESET_ENERGY.key)
        ).async_press()
        await advance(hass, freezer, RESET_VERIFY_DELAY)
        await coordinator.async_refresh()

    assert [record.levelno for record in reset_lines(caplog)] == [
        logging.WARNING,
        logging.DEBUG,
    ]


async def test_a_poll_before_the_delay_neither_judges_nor_drops_the_record(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The counter reads ``0.00`` within 5 s of the ack (Q45), not sooner.

    So the write-triggered refresh at 1.5 s is too early to decide anything,
    and the record it cannot check has to survive it. Otherwise the press that
    mattered is the one never checked.
    """
    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH})

    coordinator = await press(hass, mock_config_entry, RESET_ENERGY.key)
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    assert warnings_of(caplog) == []

    await advance(hass, freezer, RESET_VERIFY_DELAY)
    await coordinator.async_refresh()

    assert [record.levelno for record in reset_lines(caplog)] == [logging.WARNING]


async def test_a_reset_the_counter_followed_says_nothing(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ordinary press: the counter drops to ``0.00`` and the log is quiet."""
    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH})

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        coordinator = await press(hass, mock_config_entry, RESET_ENERGY.key)
        patched_client.set_status({TOTAL_CONSUMPTION: 0.0})
        await advance(hass, freezer, RESET_VERIFY_DELAY)
        await coordinator.async_refresh()

    assert reset_lines(caplog) == []


async def test_pressing_at_zero_still_sends_and_verifies_nothing(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reference panel reads ``0.00``: the request goes, the check does not.

    The last reading may be a *poll interval* stale and the request is
    harmless either way, so the press is never held back. A zero reading
    cannot fall below itself, so it is not checked.
    """
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        coordinator = await press(hass, mock_config_entry, RESET_ENERGY.key)
        await advance(hass, freezer, RESET_VERIFY_DELAY)
        await coordinator.async_refresh()

    assert patched_client.resets == [RESET_ENERGY.reset]
    assert reset_lines(caplog) == []


async def test_a_second_press_replaces_the_pending_record(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two presses are one pending record: the second one's (§5.5).

    The counter falls between the presses, so the two records disagree about
    the outcome. Against the first reading the drop is a reset that took.
    Against the second it is a counter that did not move. The warning is the
    second record's, the one the user's last press made.
    """
    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH})
    coordinator = await press(hass, mock_config_entry, RESET_ENERGY.key)

    patched_client.set_status({TOTAL_CONSUMPTION: 1.0})
    await advance(hass, freezer, POST_WRITE_REFRESH_DELAY)

    assert warnings_of(caplog) == []

    await HeatitPanelButton(coordinator, description(RESET_ENERGY.key)).async_press()
    await advance(hass, freezer, RESET_VERIFY_DELAY)

    judged = reset_lines(caplog)
    assert [record.levelno for record in judged] == [logging.WARNING]
    assert "1.0" in judged[0].getMessage()
    assert str(BANKED_KWH) not in judged[0].getMessage()


async def test_a_press_at_zero_clears_a_record_still_pending(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A zero reading replaces the pending record with nothing to verify.

    The counter then climbs back above where the *first* press found it. A
    record left standing from that press would read the climb as a reset that
    did not take and warn about it.
    """
    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH})
    coordinator = await press(hass, mock_config_entry, RESET_ENERGY.key)

    patched_client.set_status({TOTAL_CONSUMPTION: 0.0})
    await coordinator.async_refresh()
    await HeatitPanelButton(coordinator, description(RESET_ENERGY.key)).async_press()

    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH + 1})
    await advance(hass, freezer, RESET_VERIFY_DELAY)
    await coordinator.async_refresh()

    assert patched_client.resets == [RESET_ENERGY.reset, RESET_ENERGY.reset]
    assert warnings_of(caplog) == []


async def test_a_counter_the_panel_stopped_returning_ends_the_check_quietly(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A reading that is gone is not a reset that failed (§6.3).

    The *energy counter* has no registry descriptor, so the coordinator's
    vanished-parameter warning never covers it. The energy sensor going
    unavailable is how §6.3 reports this one. The verification owes one
    ``debug`` line saying it gave up, and no blame.
    """
    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH})

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        coordinator = await press(hass, mock_config_entry, RESET_ENERGY.key)
        patched_client.set_status({TOTAL_CONSUMPTION: ABSENT})
        await advance(hass, freezer, RESET_VERIFY_DELAY)
        await coordinator.async_refresh()

    assert warnings_of(caplog) == []
    assert [record.levelno for record in reset_lines(caplog)] == [logging.DEBUG]


async def test_a_drop_home_assistant_did_not_cause_is_never_logged(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A reset from the MyHeatit app is a valid act, not an anomaly (§5.5).

    The statistics engine already treats the drop as a new meter cycle, and
    nothing about it says the panel is going wrong. So there is nothing to say
    about it at any level.
    """
    patched_client.set_status({TOTAL_CONSUMPTION: BANKED_KWH})
    coordinator = await loaded(hass, mock_config_entry)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        patched_client.set_status({TOTAL_CONSUMPTION: 0.0})
        await advance(hass, freezer, RESET_VERIFY_DELAY)
        await coordinator.async_refresh()

    assert reset_lines(caplog) == []
