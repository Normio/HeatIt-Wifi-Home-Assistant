"""The panel's readings as history (§5.2, §5.5).

Five sensors, and nothing else:

- the room temperature
- the power draw right now
- the *energy counter* that feeds the Energy dashboard
- the WiFi signal, as a diagnostic
- the *open window detection* countdown

**The temperature sensor is the one mirror of climate state.** There is no
heating sensor, because the power reading and ``hvac_action`` already say it.
There are no setpoint sensors, because the config ``number`` entities record
that history (§5.4). Anything not in §5.2's table is left out, not created
disabled.

Each row reads a path straight out of the *status*. None of these is a
*parameter* the panel accepts a write for. So the registry has no descriptor
for any of them, and the read path lives in the description here. Presence is
still §5.4's rule. A path the first status does not have makes no entity, and
one that vanishes later makes its own entity unavailable (§6.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)

from .api import TOTAL_CONSUMPTION, WIFI_SIGNAL_STRENGTH
from .entity import HeatitWifiPanelEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .api import PanelStatus
    from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator

PARALLEL_UPDATES = 0
"""Read-only: nothing here writes, so there is nothing to run one at a time (§3.5)."""

ROOM_TEMPERATURE: Final = "roomTemperature"
CURRENT_POWER: Final = "currentPower"
OPEN_WINDOW_ACTIVE_TIME: Final = "parameters.OWD.activeTime"


@dataclass(frozen=True, kw_only=True)
class HeatitSensorEntityDescription(SensorEntityDescription):
    """One §5.2 sensor row: where it reads, and what that reading becomes."""

    read_path: str
    """The dotted path in the *status*, also the presence and availability test."""

    value_fn: Callable[[PanelStatus], int | float | None]
    """The reading as a state. ``None`` is *unknown*, never an exception."""


SENSORS: Final[tuple[HeatitSensorEntityDescription, ...]] = (
    HeatitSensorEntityDescription(
        key="temperature",
        read_path=ROOM_TEMPERATURE,
        value_fn=lambda status: status.get_float(ROOM_TEMPERATURE),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    HeatitSensorEntityDescription(
        key="power",
        read_path=CURRENT_POWER,
        value_fn=lambda status: status.get_float(CURRENT_POWER),
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # ``total_increasing`` and never ``total`` with ``last_reset``: the counter
    # can be zeroed from the MyHeatit app, and Home Assistant can never learn
    # when. So a ``last_reset`` would be wrong the first time anyone else
    # pressed it. The 10 % dip tolerance is safe because a reset lands the
    # counter at exactly 0.00 (Q21). §5.5.
    HeatitSensorEntityDescription(
        key="energy",
        read_path=TOTAL_CONSUMPTION,
        value_fn=lambda status: status.get_float(TOTAL_CONSUMPTION),
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Disabled by default as a noisy diagnostic. With the two reset-shaped
    # buttons, that is one of the only two things the marker means (§5.4).
    # The parse is the client's, and it does **no sign fix-up**. The device
    # sends a signed value, so an unsigned one is reported as it came, not
    # corrected. An unreadable one is ``None`` plus a debug line.
    HeatitSensorEntityDescription(
        key="signal_strength",
        read_path=WIFI_SIGNAL_STRENGTH,
        value_fn=lambda status: status.signal_strength_dbm,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # No state class: this is a countdown, neither a measurement to average
    # nor a total to sum. It reads 0 whenever no open window is detected (Q25).
    # Whether it counts down while one is detected is register row Q47, still
    # open.
    HeatitSensorEntityDescription(
        key="open_window_time_remaining",
        read_path=OPEN_WINDOW_ACTIVE_TIME,
        value_fn=lambda status: status.get_int(OPEN_WINDOW_ACTIVE_TIME),
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001  # the platform signature is core's
    entry: HeatitWifiPanelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add every sensor whose read path is in the **first** status (§5.4)."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeatitPanelSensor(coordinator, description)
        for description in SENSORS
        if coordinator.data.get(description.read_path) is not None
    )


class HeatitPanelSensor(HeatitWifiPanelEntity, SensorEntity):
    """One reading of one panel, kept as history."""

    entity_description: HeatitSensorEntityDescription

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        description: HeatitSensorEntityDescription,
    ) -> None:
        """Bind to the panel, named and read by the description's key and path."""
        super().__init__(coordinator, description.key, read_path=description.read_path)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> int | float | None:
        """The current reading, or ``None``, which Home Assistant shows as unknown.

        A reading the panel stopped returning never reaches here: the base
        entity has already made this entity unavailable (§6.3). ``None`` from a
        path that *is* there is a value we could not read. For the signal
        strength that is the documented outcome and never an exception.
        """
        return self.entity_description.value_fn(self.coordinator.data)
