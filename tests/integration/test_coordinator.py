"""Only the poll decides availability (§6), and the §7.2 log table.

Every entity goes unavailable on the **first** failed poll: no coordinator-level
grace period, no failure counter of our own, no stale data served as fresh. A
single dropped packet is forgiven one layer down, in the status read's own
retry inside the *poll budget*.
"""

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from homeassistant.exceptions import (
    ConfigEntryError,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed_exact

from custom_components.heatit_wifi_panel.api import (
    TOTAL_CONSUMPTION,
    HeatitConnectionError,
    HeatitMissingFieldError,
    HeatitParameterRejected,
    HeatitProtocolError,
    HeatitResponseError,
)
from custom_components.heatit_wifi_panel.const import (
    DOMAIN,
    POST_WRITE_REFRESH_DELAY,
    RESET_VERIFY_DELAY,
    VERIFIED_FIRMWARES,
)
from custom_components.heatit_wifi_panel.registry import PARAMETERS
from tests.fakes import ABSENT, FakeHeatitClient
from tests.integration.conftest import (
    FOREIGN_DEVICE_ID,
    REFERENCE_DEVICE_ID,
    setup_entry,
)

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.heatit_wifi_panel.coordinator import (
        HeatitWifiPanelCoordinator,
    )

#: What each client failure becomes, and the placeholders the message needs.
#: The dotted path travels on the exception instead of being parsed again here.
POLL_FAILURES = [
    (HeatitConnectionError("timed out"), "cannot_connect", None),
    (
        HeatitMissingFieldError("parameters.ecoSetpoint"),
        "missing_field",
        {"field": "parameters.ecoSetpoint"},
    ),
    (HeatitProtocolError("a captive page"), "invalid_response", None),
    (HeatitResponseError(404, "Not Found"), "invalid_response", None),
]

#: §6.4's table. Every one is a ``HomeAssistantError`` and never a
#: ``ServiceValidationError``, which stays reserved for the one local case the
#: climate entity owns.
WRITE_FAILURES = [
    (
        HeatitParameterRejected("heatingSetpoint", 400, "invalid data for setpoint"),
        "parameter_rejected",
        {"parameter": "heatingSetpoint", "reason": "invalid data for setpoint"},
    ),
    (HeatitConnectionError("timed out"), "cannot_connect", None),
    (HeatitProtocolError("a captive page"), "unexpected_response", None),
    (HeatitResponseError(405, "Method Not Allowed"), "unexpected_response", None),
]

#: §6.4's table again, for a request that carries no parameter. A reset has
#: nothing for the registry to bound and nothing for a ``400`` to name. So the
#: rejection row is the one row it cannot reach.
RESET_FAILURES = [
    (HeatitConnectionError("timed out"), "cannot_connect"),
    (HeatitProtocolError("a captive page"), "unexpected_response"),
    (HeatitResponseError(405, "Method Not Allowed"), "unexpected_response"),
]

#: The coordinator's two resets. Everything §6.4 asks of a reset it asks of
#: both, and only the *energy* one is verified afterwards (§5.5).
RESETS = ["async_reset_energy", "async_reset_settings"]

LOGGER_NAME = f"custom_components.{DOMAIN}"


async def loaded(
    hass: HomeAssistant, entry: MockConfigEntry
) -> HeatitWifiPanelCoordinator:
    """Set the entry up and hand back its coordinator."""
    assert await setup_entry(hass, entry)
    coordinator: HeatitWifiPanelCoordinator = entry.runtime_data
    return coordinator


def panel_lines(
    caplog: pytest.LogCaptureFixture, level: int = logging.INFO
) -> list[logging.LogRecord]:
    """Return only this integration's own lines, at ``level`` or above.

    ``caplog`` captures whatever reaches the root logger, Home Assistant's own
    setup noise included, and §7.2 is a table about *our* lines.
    """
    return [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno >= level
    ]


@pytest.mark.parametrize(("failure", "key", "placeholders"), POLL_FAILURES)
async def test_a_failed_poll_names_what_went_wrong(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    failure: Exception,
    key: str,
    placeholders: dict[str, str] | None,
) -> None:
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.fail(failure)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    error = coordinator.last_exception
    assert isinstance(error, UpdateFailed)
    assert error.translation_domain == DOMAIN
    assert error.translation_key == key
    if placeholders is not None:
        assert error.translation_placeholders == placeholders


async def test_the_first_failed_poll_is_enough(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """No grace period, and the last good status is not served as fresh."""
    coordinator = await loaded(hass, mock_config_entry)
    assert coordinator.last_update_success is True
    patched_client.fail(HeatitConnectionError("timed out"))

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False


async def test_recovery_is_the_next_good_poll(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two log lines for a panel that was away, and nothing in between (§6.1)."""
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.fail(HeatitConnectionError("timed out"), times=3)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        for _ in range(3):
            await coordinator.async_refresh()
        assert coordinator.last_update_success is False
        await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert [record.levelno for record in panel_lines(caplog)] == [
        logging.ERROR,
        logging.INFO,
    ]


async def test_a_foreign_panel_fails_the_poll_rather_than_becoming_data(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The alternative is writing one bedroom's setpoints into another (§6.2)."""
    coordinator = await loaded(hass, mock_config_entry)
    good_status = coordinator.data
    patched_client.set_status({"id": FOREIGN_DEVICE_ID})

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert coordinator.data is good_status
    error = coordinator.last_exception
    assert isinstance(error, ConfigEntryError)
    assert error.translation_key == "foreign_panel"
    assert error.translation_placeholders == {
        "expected_id": REFERENCE_DEVICE_ID,
        "actual_id": FOREIGN_DEVICE_ID,
    }


async def test_a_foreign_panel_at_poll_time_is_never_escalated(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Keep the entry loaded: the user sees one error line, not a dead entry.

    A reload is what turns a *foreign panel* into the permanent setup error
    (§6.2). The coordinator itself never passes one up.
    """
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.set_status({"id": FOREIGN_DEVICE_ID})

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert mock_config_entry.state is mock_config_entry.state.LOADED


# --- presence, fixed at setup ----------------------------------------------


@pytest.mark.usefixtures("patched_client")
async def test_presence_is_fixed_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    coordinator = await loaded(hass, mock_config_entry)

    assert coordinator.observed_parameters == frozenset(PARAMETERS)
    assert coordinator.vanished_parameters == set()


async def test_a_parameter_absent_at_setup_is_simply_absent(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Setup succeeds; only that one reading is unknown (§6.3)."""
    patched_client.set_status({"parameters.loadLimit": ABSENT})

    coordinator = await loaded(hass, mock_config_entry)

    assert "loadLimit" not in coordinator.observed_parameters
    assert coordinator.vanished_parameters == set()


async def test_null_is_absent(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """No panel has ever returned one, and the integration models no third state."""
    patched_client.set_status({"parameters.loadLimit": None})

    coordinator = await loaded(hass, mock_config_entry)

    assert "loadLimit" not in coordinator.observed_parameters


async def test_an_unknown_key_is_ignored(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    patched_client.set_status(
        {"somethingNew": 1, "parameters.somethingNewer": "whatever"}
    )

    coordinator = await loaded(hass, mock_config_entry)

    assert coordinator.observed_parameters == frozenset(PARAMETERS)


async def test_a_vanished_parameter_warns_once_and_its_return_informs(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Once per transition, both ways. Nothing repeats per poll (§7.2)."""
    coordinator = await loaded(hass, mock_config_entry)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        patched_client.set_status({"parameters.disableButtons": ABSENT})
        await coordinator.async_refresh()
        await coordinator.async_refresh()
        warnings = panel_lines(caplog, logging.WARNING)
        assert len(warnings) == 1
        assert "disableButtons" in warnings[0].getMessage()
        assert coordinator.vanished_parameters == {"disableButtons"}

        caplog.clear()
        patched_client.set_status({"parameters.disableButtons": 1})
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    returns = panel_lines(caplog)
    assert len(returns) == 1
    assert "disableButtons" in returns[0].getMessage()
    assert coordinator.vanished_parameters == set()


async def test_a_parameter_appearing_after_setup_waits_for_a_reload(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug, once, and no entity is added at run time (§6.3)."""
    patched_client.set_status({"parameters.sensorMode": ABSENT})
    coordinator = await loaded(hass, mock_config_entry)
    assert "sensorMode" not in coordinator.observed_parameters

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        patched_client.set_status({"parameters.sensorMode": False})
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    appeared = [
        record
        for record in panel_lines(caplog, logging.DEBUG)
        if "sensorMode" in record.getMessage()
    ]
    assert len(appeared) == 1
    assert appeared[0].levelno == logging.DEBUG
    assert coordinator.observed_parameters == frozenset(PARAMETERS) - {"sensorMode"}

    # The reload is what picks it up.
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    assert mock_config_entry.runtime_data.observed_parameters == frozenset(PARAMETERS)


async def test_a_late_parameter_is_noted_once_per_transition(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§7.2 says *once per transition*, and a transition can happen twice.

    A parameter that was absent at setup, appeared, went away again and came
    back has appeared **twice**. The second debug line records that the panel
    is going back and forth, not that it changed once.
    """
    patched_client.set_status({"parameters.sensorMode": ABSENT})
    coordinator = await loaded(hass, mock_config_entry)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        for value in (False, ABSENT, False):
            patched_client.set_status({"parameters.sensorMode": value})
            await coordinator.async_refresh()
            await coordinator.async_refresh()

    appeared = [
        record
        for record in panel_lines(caplog, logging.DEBUG)
        if "sensorMode" in record.getMessage()
    ]
    assert len(appeared) == 2
    assert {record.levelno for record in appeared} == {logging.DEBUG}


# --- firmware ---------------------------------------------------------------


@pytest.mark.usefixtures("patched_client")
async def test_a_verified_firmware_says_nothing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await loaded(hass, mock_config_entry)

    assert panel_lines(caplog) == []


@pytest.mark.parametrize("firmware", ["1.22", ABSENT])
async def test_an_unverified_firmware_informs_once_per_setup(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    firmware: object,
) -> None:
    """Unverified is not unsupported, and an absent version is unverified too."""
    patched_client.set_status({"firmware": firmware})

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        coordinator = await loaded(hass, mock_config_entry)
        await coordinator.async_refresh()
        await coordinator.async_refresh()

    lines = panel_lines(caplog)
    assert len(lines) == 1
    assert next(iter(VERIFIED_FIRMWARES)) in lines[0].getMessage()


# --- the write path ---------------------------------------------------------


@pytest.mark.parametrize(("failure", "key", "placeholders"), WRITE_FAILURES)
async def test_a_failed_write_says_what_the_panel_said(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    failure: Exception,
    key: str,
    placeholders: dict[str, str] | None,
) -> None:
    """§6.4's table, with the device's ``reason`` word for word and never parsed.

    A ``400`` is not a user error. Home Assistant's own layers and the registry
    have both bounded the value before the device sees it. So a rejection means
    our bounds and the panel's disagree. That is drift, and drift is an error.
    """
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.refuse(failure)

    with pytest.raises(HomeAssistantError) as raised:
        await coordinator.async_write_parameter("heatingSetpoint", value=21.0)

    assert not isinstance(raised.value, ServiceValidationError)
    assert raised.value.translation_domain == DOMAIN
    assert raised.value.translation_key == key
    if placeholders is not None:
        assert raised.value.translation_placeholders == placeholders


async def test_a_failed_write_leaves_availability_alone(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The poll decides whether the panel is gone, not the write (§6.4)."""
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.refuse(HeatitConnectionError("timed out"))

    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_parameter("heatingSetpoint", value=21.0)

    assert coordinator.last_update_success is True


async def test_the_refresh_is_scheduled_even_when_the_write_failed(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The panel commits in 300-600 ms, so a lost *response* proves nothing.

    The refresh is what brings Home Assistant in line with what the device did.
    """
    coordinator = await loaded(hass, mock_config_entry)
    reads = patched_client.status_reads
    patched_client.refuse(HeatitConnectionError("timed out"))

    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_parameter("heatingSetpoint", value=21.0)
    async_fire_time_changed_exact(
        hass, dt_util.utcnow() + timedelta(seconds=POST_WRITE_REFRESH_DELAY)
    )
    await hass.async_block_till_done()

    assert patched_client.status_reads == reads + 1


async def test_a_silent_undo_warns_once_per_parameter(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """§6.5's one known instance: ``sensorMode`` with no sensor paired.

    Client-side rounding to the grid has already removed the snap case, so
    every mismatch that survives is a device refusal that looks like success.
    Warn once per parameter per entry lifetime, debug after that (§7.2).
    """
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.echoes["sensorMode"] = True

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        for _ in range(2):
            await coordinator.async_write_parameter("sensorMode", value=True)
            freezer.tick(timedelta(seconds=POST_WRITE_REFRESH_DELAY))
            await coordinator.async_refresh()

    lines = [
        record
        for record in panel_lines(caplog, logging.DEBUG)
        if "acknowledged" in record.getMessage()
    ]
    assert [record.levelno for record in lines] == [logging.WARNING, logging.DEBUG]
    assert "sensorMode" in lines[0].getMessage()


async def test_a_write_the_panel_applied_says_nothing(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    coordinator = await loaded(hass, mock_config_entry)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        await coordinator.async_write_parameter("heatingSetpoint", value=21.0)
        patched_client.set_status({"parameters.heatingSetpoint": 21.0})
        freezer.tick(timedelta(seconds=POST_WRITE_REFRESH_DELAY))
        await coordinator.async_refresh()

    assert [
        record
        for record in panel_lines(caplog)
        if "acknowledged" in record.getMessage()
    ] == []


async def test_a_vanished_parameter_is_not_also_a_silent_undo(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """One absence is one anomaly: the vanishing, which §6.3 already named."""
    coordinator = await loaded(hass, mock_config_entry)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        await coordinator.async_write_parameter("loadLimit", value=700)
        patched_client.set_status({"parameters.loadLimit": ABSENT})
        freezer.tick(timedelta(seconds=POST_WRITE_REFRESH_DELAY))
        await coordinator.async_refresh()

    warnings = panel_lines(caplog, logging.WARNING)
    assert len(warnings) == 1
    assert "acknowledged" not in warnings[0].getMessage()


async def test_a_poll_inside_the_window_neither_judges_nor_drops_the_echo(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A poll can land in the 1.5 s a write needs to reach the status (Q31).

    Core cancels the debounced refresh when a scheduled poll runs, so that poll
    is the only one coming. Checking it would report a *silent undo* that never
    happened and drop the user's value back for a full *poll interval*. §6.5
    names the **post-write** refresh, and this is not yet it.
    """
    coordinator = await loaded(hass, mock_config_entry)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        await coordinator.async_write_parameter("heatingSetpoint", value=21.0)
        # The panel has acknowledged it and has not committed it yet.
        await coordinator.async_refresh()
        assert coordinator.parameter("heatingSetpoint") == 21.0

        patched_client.set_status({"parameters.heatingSetpoint": 21.0})
        freezer.tick(timedelta(seconds=POST_WRITE_REFRESH_DELAY))
        await coordinator.async_refresh()

    assert coordinator.parameter("heatingSetpoint") == 21.0
    assert panel_lines(caplog, logging.WARNING) == []


async def test_a_value_the_registry_refuses_never_reaches_the_panel(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Off the 0.5 grid, refused locally, and §6.4 wants that translated too.

    Core checks a ``climate.set_temperature`` against ``min_temp`` and
    ``max_temp`` and never against ``target_temperature_step``. So an off-grid
    value does reach the registry, which raises before a request exists.
    """
    coordinator = await loaded(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError) as raised:
        await coordinator.async_write_parameter("heatingSetpoint", value=21.3)

    assert raised.value.translation_key == "invalid_value"
    assert raised.value.translation_placeholders is not None
    assert "21.3" in raised.value.translation_placeholders["error"]
    assert patched_client.writes == []


# --- the reset path ---------------------------------------------------------


@pytest.mark.parametrize(("failure", "key"), RESET_FAILURES)
@pytest.mark.parametrize("reset", RESETS)
async def test_a_failed_reset_says_what_the_panel_said(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    reset: str,
    failure: Exception,
    key: str,
) -> None:
    """A reset fails the way a write fails (§6.4), minus the rejection row.

    There is no parameter to name and no value to bound, so the device's
    ``400`` reaches the client as a plain response error. The user gets the
    panel's own words either way.
    """
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.refuse_reset(failure)

    with pytest.raises(HomeAssistantError) as raised:
        await getattr(coordinator, reset)()

    assert not isinstance(raised.value, ServiceValidationError)
    assert raised.value.translation_domain == DOMAIN
    assert raised.value.translation_key == key


@pytest.mark.parametrize("reset", RESETS)
async def test_a_failed_reset_leaves_availability_alone(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    reset: str,
) -> None:
    """The poll decides whether the panel is gone, a reset never does (§6)."""
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.refuse_reset(HeatitConnectionError("timed out"))

    with pytest.raises(HomeAssistantError):
        await getattr(coordinator, reset)()

    assert coordinator.last_update_success is True


@pytest.mark.parametrize("reset", RESETS)
async def test_the_refresh_is_scheduled_even_when_the_reset_failed(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    reset: str,
) -> None:
    """A lost *response* proves nothing about what the panel did with it."""
    coordinator = await loaded(hass, mock_config_entry)
    reads = patched_client.status_reads
    patched_client.refuse_reset(HeatitConnectionError("timed out"))

    with pytest.raises(HomeAssistantError):
        await getattr(coordinator, reset)()
    async_fire_time_changed_exact(
        hass, dt_util.utcnow() + timedelta(seconds=POST_WRITE_REFRESH_DELAY)
    )
    await hass.async_block_till_done()

    assert patched_client.status_reads == reads + 1


async def test_a_reset_the_panel_never_acknowledged_verifies_nothing(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§5.5 records the *ack*, so a press that never got one is not pending.

    The request never arrived, so the counter did not fall. Warning about that
    would blame the panel for a network failure the user has already been told
    about.
    """
    patched_client.set_status({TOTAL_CONSUMPTION: 4.32})
    coordinator = await loaded(hass, mock_config_entry)
    patched_client.refuse_reset(HeatitConnectionError("timed out"))

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        with pytest.raises(HomeAssistantError):
            await coordinator.async_reset_energy()
        freezer.tick(timedelta(seconds=RESET_VERIFY_DELAY))
        await coordinator.async_refresh()

    assert [
        record
        for record in panel_lines(caplog, logging.DEBUG)
        if "reset" in record.getMessage()
    ] == []
