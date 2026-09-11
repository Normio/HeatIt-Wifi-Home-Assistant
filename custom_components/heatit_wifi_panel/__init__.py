"""The Heatit WiFi Panel integration.

Setup order is fixed (§3.4): first refresh → ``runtime_data`` → the device →
forward platforms. ``hass.data`` is untouched, ``runtime_data`` is never cleared
on unload (core removes it), and there is **no sleep of any kind** here — the
first refresh raises ``ConfigEntryNotReady`` and Home Assistant retries with its
own backoff, the status read has its own retry, and ``DataUpdateCoordinator``
already jitters every scheduled refresh (§3.6).

The device is registered here rather than by an entity, so a panel with no
platforms yet still appears as one device, and so `name` and *assigned room*
are spent at setup and never touched by a poll (§4.4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import UNDEFINED

from .api import HeatitClient
from .const import DOMAIN, FALLBACK_DEVICE_NAME, MANUFACTURER
from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import PanelStatus

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
]
"""The platform modules to forward to; each platform ticket adds its own."""


async def async_setup_entry(
    hass: HomeAssistant, entry: HeatitWifiPanelConfigEntry
) -> bool:
    """Set one panel up: one client, one coordinator, one device."""
    client = HeatitClient(entry.data[CONF_HOST], session=async_get_clientsession(hass))
    coordinator = HeatitWifiPanelCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _async_register_device(hass, entry, coordinator.data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HeatitWifiPanelConfigEntry
) -> bool:
    """Unload the entry's platforms. The session is Home Assistant's to keep."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_register_device(
    hass: HomeAssistant, entry: HeatitWifiPanelConfigEntry, status: PanelStatus
) -> None:
    """Register the panel as one device, from the first status (§3.5).

    Identity is the *device id*; the MAC sits in ``connections``, where core
    normalises it through ``format_mac``, so a firmware found to churn the
    device id has a migration path rather than a dead end (ADR-0003). There is
    deliberately **no** ``configuration_url``: the panel serves no web UI.

    ``name`` and ``suggested_area`` are written **at creation only** (§4.4).
    The registry honours ``suggested_area`` when it makes the device and
    ignores it afterwards; ``name`` is withheld on every later setup, so a
    rename in the MyHeatit app simply diverges instead of overwriting what
    Home Assistant shows. ``model`` and ``sw_version`` are refreshed each
    setup instead — they are facts about the hardware, and §3.5 has a firmware
    change picked up on reload.
    """
    device_registry = dr.async_get(hass)
    # Asked of the entry, not of the identifiers: one entry is one device
    # (§4.7), so "does this entry already own one?" is the question, and it is
    # the question that keeps working — ``async_get_device`` is deprecated from
    # Home Assistant 2026.9 because identifiers stopped being unique across
    # entries, and it breaks in 2027.8.
    creating = not dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, status.device_id)},
        connections=(
            {(dr.CONNECTION_NETWORK_MAC, status.mac)} if status.mac else set()
        ),
        manufacturer=MANUFACTURER,
        model=status.model,
        name=(status.name or FALLBACK_DEVICE_NAME) if creating else UNDEFINED,
        suggested_area=status.room or None,
        sw_version=status.firmware,
    )
