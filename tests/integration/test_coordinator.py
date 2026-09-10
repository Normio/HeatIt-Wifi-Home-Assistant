"""The poll is the sole judge of availability (§6), and the §7.2 log table.

Every entity goes unavailable on the **first** failed poll: no coordinator-level
grace, no hand-rolled failure counter, no stale data served as fresh. The
tolerance for a single dropped packet lives one layer down, in the status read's
own retry inside the *poll budget*.
"""

import logging
from typing import TYPE_CHECKING

import pytest
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.heatit_wifi_panel.api import (
    HeatitConnectionError,
    HeatitMissingFieldError,
    HeatitProtocolError,
    HeatitResponseError,
)
from custom_components.heatit_wifi_panel.const import DOMAIN, VERIFIED_FIRMWARES
from custom_components.heatit_wifi_panel.registry import PARAMETERS
from tests.fakes import ABSENT, FakeHeatitClient
from tests.integration.conftest import (
    FOREIGN_DEVICE_ID,
    REFERENCE_DEVICE_ID,
    setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.heatit_wifi_panel.coordinator import (
        HeatitWifiPanelCoordinator,
    )

#: What each client failure becomes, and the placeholders the message needs.
#: The dotted path travels on the exception rather than being re-parsed here.
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
    """Only this integration's own lines, at ``level`` or above.

    ``caplog`` captures whatever propagates to the root, Home Assistant's own
    setup chatter included, and §7.2 is a table about *our* lines.
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
    """No grace, and the last good status is not served as fresh."""
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
    (§6.2); the coordinator itself never escalates one.
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
    """Once per transition, both ways — nothing repeats per poll (§7.2)."""
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
    """Debug, once, and no dynamic entity addition (§6.3)."""
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
    back has appeared **twice**, and the second debug line is the record that
    the panel is flapping rather than that it changed once.
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
