"""The two presses that discard device state (§5.2, §5.5).

One zeroes the *energy counter*, the other puts every setting back to its
default. Neither reads anything from the *status*: a button only writes, which
is why these are the two entities on the panel that no firmware returning one
field less can take away.

**Both ship disabled by default**, and that is the whole of §5.4's opt-in rule:
a *noisy diagnostic*, or a button whose press discards device state. Home
Assistant offers a button entity no confirmation dialog, so opt-in is the only
guard there is — and a mis-tap is bounded either way, at one unpublished energy
step lost in Home Assistant and the panel's own counter zeroed (§5.5).

Neither press is retried and neither touches availability. Both go through the
coordinator, which is where §6.4's translated failures and — for the energy
reset — the verification that the counter actually fell already live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory

from .entity import HeatitWifiPanelEntity

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator

PARALLEL_UPDATES = 1
"""One press at a time within this platform, on top of the client's own lock."""


@dataclass(frozen=True, kw_only=True)
class HeatitButtonDescription(ButtonEntityDescription):
    """One §5.2 button row: what a press asks the panel to throw away."""

    press_fn: Callable[[HeatitWifiPanelCoordinator], Awaitable[None]]
    """What one press does. The coordinator owns the request and its verdict."""


BUTTONS: Final[tuple[HeatitButtonDescription, ...]] = (
    HeatitButtonDescription(
        key="reset_energy",
        press_fn=lambda coordinator: coordinator.async_reset_energy(),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    HeatitButtonDescription(
        key="restore_defaults",
        press_fn=lambda coordinator: coordinator.async_reset_settings(),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - the platform signature is core's
    entry: HeatitWifiPanelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add both buttons: neither is gated on a reading, because neither has one.

    §5.4's presence rule is about a parameter a firmware may not return. These
    two are endpoints, not parameters — a panel that answers a *status* at all
    is a panel both requests can be sent to.
    """
    coordinator = entry.runtime_data
    async_add_entities(
        HeatitPanelButton(coordinator, description) for description in BUTTONS
    )


class HeatitPanelButton(HeatitWifiPanelEntity, ButtonEntity):
    """One press that discards something the panel is holding."""

    entity_description: HeatitButtonDescription

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        description: HeatitButtonDescription,
    ) -> None:
        """Bind to the panel, named by the description's key.

        No ``read_path``: there is nothing to read, so the poll alone decides
        whether this button is available (§6.3).
        """
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @override
    async def async_press(self) -> None:
        """Send the one request, once. The next poll is what follows up."""
        await self.entity_description.press_fn(self.coordinator)
