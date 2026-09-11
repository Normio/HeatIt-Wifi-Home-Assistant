"""Fixtures for the client seam: a booted ``hass``, an entry, and the fake."""

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.heatit_wifi_panel.const import DOMAIN
from tests.fakes import FakeHeatitClient

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceEntry

REFERENCE_DEVICE_ID = "FIXTUREFIXTUREFIXTUREX"
"""The reference capture's scrubbed ``id``: 22 chars, mixed case, as a real one."""

REFERENCE_HOST = "10.0.0.2"
"""Any address will do — the fake never looks at it — but a plausible one reads."""

FOREIGN_DEVICE_ID = "OTHERPANELOTHERPANELXY"
"""A *foreign panel*'s id: another unit that has taken over the address.

Same shape as a real one, and deliberately never :data:`REFERENCE_DEVICE_ID` —
the three suites that need one all mean the same panel, so they share it rather
than each minting a look-alike.
"""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest) -> None:
    """Let ``hass`` load ``custom_components/heatit_wifi_panel``."""
    request.getfixturevalue("enable_custom_integrations")


@pytest.fixture
def fake_client(
    reference_status_bytes: bytes, reference_headers: dict[str, str]
) -> FakeHeatitClient:
    """One fake panel, answering from the reference capture's bytes and headers."""
    return FakeHeatitClient(reference_status_bytes, reference_headers)


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


def entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    """Return one entity's id, asked of the registry rather than spelled out.

    The id core generates is core's business and moves between releases: Home
    Assistant 2026.9 began prefixing it with the device's area, turning
    ``climate.naytehuone_1`` into ``climate.bedroom_naytehuone_1`` under this
    very fixture. The unique id is ours and does not move, so it is what an
    entity is found by — ``{device id}-{key}``, §5.2's own two halves.
    """
    found = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{REFERENCE_DEVICE_ID}-{key}"
    )
    assert found is not None
    return found


def panel_device(hass: HomeAssistant, entry: MockConfigEntry) -> DeviceEntry:
    """Return the one device the entry owns.

    Looked up by config entry rather than by identifiers: one entry is one
    device (§4.7), and ``async_get_device`` is deprecated from Home Assistant
    2026.9 — it raises for a test caller, which is how the ``latest`` row of
    §8.7's matrix earns its keep. Callers assert the identifiers themselves.
    """
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    return devices[0]


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    """Add ``entry`` to ``hass`` and set it up; return whether it loaded."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.state is ConfigEntryState.LOADED
