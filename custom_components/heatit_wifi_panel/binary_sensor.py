"""The *open window detection* result, as on and off (§5.2).

One entity, and it carries **no device class**. `Open`/`Closed` would claim the
panel knows a window moved. It does not. It detects an open window from a
temperature drop and lowers the *live setpoint* until its countdown runs out.
So this is On/Off. The two window icons do the describing, and the countdown
beside it is the ``open_window_time_remaining`` sensor.

Three concepts, three names (§5.4). The *setting* is the "Open window
detection" switch. The *detection* is this entity. The *countdown* is that
sensor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, override

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .entity import HeatitWifiPanelEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .api import PanelStatus
    from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator

PARALLEL_UPDATES = 0
"""Read-only: nothing here writes, so there is nothing to run one at a time (§3.5)."""

OPEN_WINDOW_ACTIVE_NOW: Final = "parameters.OWD.activeNow"


@dataclass(frozen=True, kw_only=True)
class HeatitBinarySensorEntityDescription(BinarySensorEntityDescription):
    """One §5.2 binary-sensor row: where it reads, and what that reading means."""

    read_path: str
    """The dotted path in the *status*, also the presence and availability test."""

    value_fn: Callable[[PanelStatus], bool | None]
    """Whether it is on. ``None`` is *unknown*, never an exception."""


BINARY_SENSORS: Final[tuple[HeatitBinarySensorEntityDescription, ...]] = (
    HeatitBinarySensorEntityDescription(
        key="open_window_detected",
        read_path=OPEN_WINDOW_ACTIVE_NOW,
        value_fn=lambda status: status.get_bool(OPEN_WINDOW_ACTIVE_NOW),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001  # the platform signature is core's
    entry: HeatitWifiPanelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add every binary sensor whose read path is in the **first** status (§5.4)."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeatitPanelBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if coordinator.data.get(description.read_path) is not None
    )


class HeatitPanelBinarySensor(HeatitWifiPanelEntity, BinarySensorEntity):
    """One thing the panel works out about its own room."""

    entity_description: HeatitBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        description: HeatitBinarySensorEntityDescription,
    ) -> None:
        """Bind to the panel, named and read by the description's key and path."""
        super().__init__(coordinator, description.key, read_path=description.read_path)
        self.entity_description = description

    @property
    @override
    def is_on(self) -> bool | None:
        """Whether the panel currently detects an open window."""
        return self.entity_description.value_fn(self.coordinator.data)
