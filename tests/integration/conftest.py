"""Fixtures for the client seam: a booted ``hass``, an entry, and the fake."""

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heatit_wifi_panel.const import DOMAIN
from tests.fakes import FakeHeatitClient

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant

REFERENCE_DEVICE_ID = "FIXTUREFIXTUREFIXTUREX"
"""The reference capture's scrubbed ``id``: 22 chars, mixed case, as a real one."""

REFERENCE_HOST = "10.0.0.2"
"""Any address will do — the fake never looks at it — but a plausible one reads."""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest) -> None:
    """Let ``hass`` load ``custom_components/heatit_wifi_panel``."""
    request.getfixturevalue("enable_custom_integrations")


@pytest.fixture
def fake_client(reference_status_bytes: bytes) -> FakeHeatitClient:
    """One fake panel, answering from the reference capture's bytes."""
    return FakeHeatitClient(reference_status_bytes)


@pytest.fixture
def patched_client(fake_client: FakeHeatitClient) -> Generator[FakeHeatitClient]:
    """Hand every ``HeatitClient(...)`` call the same fake, whoever builds it.

    Setup and the config flow each construct their own client, so both
    construction sites are patched; a test that wants them to disagree patches
    one of them itself.
    """
    with (
        patch(
            "custom_components.heatit_wifi_panel.HeatitClient",
            return_value=fake_client,
        ),
        patch(
            "custom_components.heatit_wifi_panel.config_flow.HeatitClient",
            return_value=fake_client,
        ),
    ):
        yield fake_client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Build an entry for the reference panel: ``data`` is the host, alone (§4.6)."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Näytehuone 1",
        unique_id=REFERENCE_DEVICE_ID,
        data={CONF_HOST: REFERENCE_HOST},
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    """Add ``entry`` to ``hass`` and set it up; return whether it loaded."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.state is ConfigEntryState.LOADED
