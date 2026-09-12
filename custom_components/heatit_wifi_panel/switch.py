"""The two switches: open window detection and the external sensor (§5.2).

Both are settings the panel's own display and the MyHeatit app offer. Both
are one boolean parameter each, so the platform is one entity class over a
description that names the parameter. ``openWindowDetection`` is read and
written in different shapes: nested under ``parameters.OWD`` on the way in,
flat on the way out. That difference is the registry's and stays there. This
module names the parameter, and nothing else knows the difference.

``external_sensor`` is here even though the panel's *write echo* lies about
it. With no sensor paired the write does **nothing**; it is not dangerous.
§5.4 keeps the optimistic update at one rule instead of giving this
parameter an honesty flag. What a user sees is the switch coming on and going
off again at the 1.5 s refresh. What the log gets is the *silent undo* warning
of §6.5, once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

from .entity import HeatitParameterEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator

PARALLEL_UPDATES = 1
"""One write at a time within this platform, on top of the client's own lock."""


@dataclass(frozen=True, kw_only=True)
class HeatitSwitchDescription(SwitchEntityDescription):
    """One boolean parameter, as a switch."""

    parameter: str
    """The wire name in the registry, which is *not* always ``key`` (§5.2)."""


SWITCHES: tuple[HeatitSwitchDescription, ...] = (
    HeatitSwitchDescription(
        key="open_window_detection",
        parameter="openWindowDetection",
        entity_category=EntityCategory.CONFIG,
    ),
    HeatitSwitchDescription(
        key="external_sensor",
        parameter="sensorMode",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001  # the platform signature is core's
    entry: HeatitWifiPanelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a switch for each parameter the panel returned at setup (§5.4)."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeatitPanelSwitch(coordinator, description)
        for description in SWITCHES
        if description.parameter in coordinator.observed_parameters
    )


class HeatitPanelSwitch(HeatitParameterEntity, SwitchEntity):
    """One boolean setting on the panel."""

    entity_description: HeatitSwitchDescription

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        description: HeatitSwitchDescription,
    ) -> None:
        """Bind to the parameter this switch flips."""
        super().__init__(coordinator, description.key, parameter=description.parameter)
        self.entity_description = description

    @property
    @override
    def is_on(self) -> bool | None:
        """The parameter, a pending *write echo* winning over the status.

        ``None`` for anything the registry's declared type cannot take, which
        is also when the entity is unavailable. The two answers agree because
        both come from the same read.
        """
        value = self.coordinator.parameter(self._parameter)
        return value if isinstance(value, bool) else None

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Write ``true``; the refresh at 1.5 s decides the state (§5.4)."""
        await self.coordinator.async_write_parameter(self._parameter, value=True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Write ``false``, on the same terms."""
        await self.coordinator.async_write_parameter(self._parameter, value=False)
