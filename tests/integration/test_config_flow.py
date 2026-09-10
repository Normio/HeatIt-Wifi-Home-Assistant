"""Every path through the config flow (§4), at 100 % line coverage.

The gate is in ``scripts/check.sh``: this module is small, and a missed path in
it is a user-facing bug rather than a coverage statistic.
"""

from typing import TYPE_CHECKING

import pytest
import voluptuous as vol
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.heatit_wifi_panel.api import (
    HeatitConnectionError,
    HeatitMissingFieldError,
    HeatitProtocolError,
    HeatitResponseError,
)
from custom_components.heatit_wifi_panel.config_flow import OPTIONS_SCHEMA
from custom_components.heatit_wifi_panel.const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    FALLBACK_DEVICE_NAME,
    MIN_POLL_INTERVAL,
)
from tests.fakes import ABSENT, FakeHeatitClient
from tests.integration.conftest import (
    FOREIGN_DEVICE_ID,
    REFERENCE_DEVICE_ID,
    REFERENCE_HOST,
    setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

OTHER_HOST = "10.0.0.3"

DISCOVERY = DhcpServiceInfo(ip=OTHER_HOST, hostname="heatit", macaddress="020000000001")

#: The two failure classes §4.2 separates, and the error each must show. A
#: refused connection is one thing; something answering that is not a panel is
#: another, and the *required core* is what tells them apart.
VALIDATION_FAILURES = [
    (HeatitConnectionError("refused"), "cannot_connect"),
    (HeatitMissingFieldError("parameters.panelMode"), "invalid_response"),
    (HeatitProtocolError("not json"), "invalid_response"),
    (HeatitResponseError(404, "Not Found"), "invalid_response"),
]


# --- the user step ----------------------------------------------------------


@pytest.mark.usefixtures("patched_client")
async def test_user_step_shows_a_host_field_alone(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    schema = result["data_schema"]
    assert schema is not None
    assert list(schema.schema) == [CONF_HOST]


@pytest.mark.usefixtures("patched_client")
async def test_user_step_creates_an_entry_titled_from_the_panel(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: REFERENCE_HOST}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Näytehuone 1"
    assert result["data"] == {CONF_HOST: REFERENCE_HOST}
    assert result["result"].unique_id == REFERENCE_DEVICE_ID
    # Options are the poll interval's home and start empty: the default lives
    # in the code, not in a value written at creation.
    assert result["result"].options == {}


async def test_user_step_falls_back_to_a_name_when_the_panel_has_none(
    hass: HomeAssistant, patched_client: FakeHeatitClient
) -> None:
    patched_client.set_status({"name": ABSENT})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: REFERENCE_HOST}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == FALLBACK_DEVICE_NAME


async def test_user_step_does_not_gate_on_model(
    hass: HomeAssistant, patched_client: FakeHeatitClient
) -> None:
    """``model`` is undocumented and spent on ``DeviceInfo`` alone (§4.2)."""
    patched_client.set_status({"model": ABSENT})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: REFERENCE_HOST}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(("failure", "error"), VALIDATION_FAILURES)
async def test_user_step_reports_the_failure_and_recovers(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    failure: Exception,
    error: str,
) -> None:
    patched_client.fail(failure)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: REFERENCE_HOST}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    # The form is live, not terminal: a corrected address goes straight through.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: REFERENCE_HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("patched_client")
async def test_user_step_aborts_rather_than_repointing_a_configured_panel(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """``_abort_if_unique_id_configured()`` is bare: adding is adding (§4.2)."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: OTHER_HOST}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data == {CONF_HOST: REFERENCE_HOST}


# --- discovery --------------------------------------------------------------


async def test_dhcp_follows_a_configured_panel_to_its_new_address(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data == {CONF_HOST: OTHER_HOST}
    # The device id is not in the DHCP packet, so the status read is what
    # identified the panel — repointing on the MAC alone would skip it.
    assert patched_client.status_reads == 1


@pytest.mark.parametrize(("failure", "_error"), VALIDATION_FAILURES)
async def test_dhcp_aborts_quietly_on_any_failure(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    failure: Exception,
    _error: str,
) -> None:
    """Home Assistant re-fires on the next DHCP event; nothing is shown (§4.3)."""
    mock_config_entry.add_to_hass(hass)
    patched_client.fail(failure)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
    assert mock_config_entry.data == {CONF_HOST: REFERENCE_HOST}


@pytest.mark.usefixtures("patched_client")
async def test_dhcp_aborts_when_the_panel_is_not_one_of_ours(
    hass: HomeAssistant,
) -> None:
    """``registered_devices`` should make this unreachable; it is still handled."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_configured"
    assert not hass.config_entries.async_entries(DOMAIN)


# --- reconfigure ------------------------------------------------------------


@pytest.mark.usefixtures("patched_client")
async def test_reconfigure_shows_the_current_host(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    schema = result["data_schema"]
    assert schema is not None
    host_field = next(iter(schema.schema))
    assert host_field == CONF_HOST
    # Suggested, not defaulted: the field is pre-filled with where the entry
    # currently points, and the user replaces it.
    assert host_field.description == {"suggested_value": REFERENCE_HOST}


@pytest.mark.usefixtures("patched_client")
async def test_reconfigure_updates_the_host_and_reloads(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: OTHER_HOST}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data == {CONF_HOST: OTHER_HOST}
    # The title was read once at creation and is not rewritten here (§4.4).
    assert mock_config_entry.title == "Näytehuone 1"


@pytest.mark.parametrize(("failure", "error"), VALIDATION_FAILURES)
async def test_reconfigure_reports_the_failure(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
    failure: Exception,
    error: str,
) -> None:
    mock_config_entry.add_to_hass(hass)
    patched_client.fail(failure)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: OTHER_HOST}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert mock_config_entry.data == {CONF_HOST: REFERENCE_HOST}


async def test_reconfigure_never_adopts_a_replacement_panel(
    hass: HomeAssistant,
    patched_client: FakeHeatitClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A replaced unit means delete-and-re-add, with the history loss (§4.5)."""
    mock_config_entry.add_to_hass(hass)
    patched_client.set_status({"id": FOREIGN_DEVICE_ID})

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: OTHER_HOST}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_panel"
    assert result["description_placeholders"] == {
        "expected_id": REFERENCE_DEVICE_ID,
        "actual_id": FOREIGN_DEVICE_ID,
    }
    assert mock_config_entry.unique_id == REFERENCE_DEVICE_ID
    assert mock_config_entry.data == {CONF_HOST: REFERENCE_HOST}


# --- options ----------------------------------------------------------------


@pytest.mark.usefixtures("patched_client")
async def test_options_hold_the_poll_interval_alone(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    assert await setup_entry(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    schema = result["data_schema"]
    assert schema is not None
    assert list(schema.schema) == [CONF_POLL_INTERVAL]
    assert schema({})[CONF_POLL_INTERVAL] == DEFAULT_POLL_INTERVAL


@pytest.mark.usefixtures("patched_client")
async def test_options_reload_the_entry_and_retime_the_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """``OptionsFlowWithReload`` reloads; nothing is retimed in place (§3.4)."""
    assert await setup_entry(hass, mock_config_entry)
    assert mock_config_entry.runtime_data.update_interval.total_seconds() == (
        DEFAULT_POLL_INTERVAL
    )

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: MIN_POLL_INTERVAL}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_POLL_INTERVAL: MIN_POLL_INTERVAL}
    assert mock_config_entry.runtime_data.update_interval.total_seconds() == (
        MIN_POLL_INTERVAL
    )


def test_the_poll_interval_has_a_floor() -> None:
    """30 s is three times the *poll budget*; below it is not offered (§4.6)."""
    assert OPTIONS_SCHEMA({CONF_POLL_INTERVAL: MIN_POLL_INTERVAL}) == {
        CONF_POLL_INTERVAL: MIN_POLL_INTERVAL
    }
    with pytest.raises(vol.Invalid):
        OPTIONS_SCHEMA({CONF_POLL_INTERVAL: MIN_POLL_INTERVAL - 1})


def test_the_poll_interval_is_stored_as_a_whole_number() -> None:
    """The number selector answers a float; the option is an ``int``."""
    interval = OPTIONS_SCHEMA({CONF_POLL_INTERVAL: 45.0})[CONF_POLL_INTERVAL]

    assert isinstance(interval, int)
    assert interval == 45
