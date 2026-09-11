"""The config numbers: every panel setting that is a quantity (§5.2, §5.4).

Eight rows, and what makes them more than a table is the second rule of §5.4:
**bounds are dynamic wherever they come from device state**. Both *setpoint
banks* are bounded by the *temperature limits*, each limit is bounded by the
other one, and the *load limit* is bounded by the *rated load* — all read from
coordinator data on every access and never cached at setup, so Home Assistant
never offers a value the panel is going to refuse.

The rest of each row is the registry's (§3.3): the step — per parameter, not
per type — the bounds that do not move, and the scale that turns the device's
units of 100 W and 10 % into the watts and percent a user sees. Nothing
dimensionless is exposed, and no range is restated here that the client already
validates every write against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
)

from .entity import HeatitParameterEntity
from .registry import PARAMETERS

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator
    from .registry import ParameterDescriptor

PARALLEL_UPDATES = 1
"""One write at a time within this platform, on top of the client's own lock."""

LOAD_LIMIT: Final = "loadLimit"

RATED_LOAD_PATH: Final = "parameters.maxLoad"
"""Where the *rated load* is read, spelled here rather than in the registry.

The registry is the client's **write** surface — every descriptor carries a
serialiser, a step and the bounds one write is validated against — and the
rated load is never written: it is the model's own rating, not a setting. Given
a descriptor it would become writable, which is worse than naming its one read
path at its one reader. §5.1 keeps it off the entity surface as well; it
surfaces as the *load limit*'s maximum and nowhere else.
"""

LIMIT_GAP: Final = 0.5
"""How far apart the two *temperature limits* must stay.

One step of the 0.5 °C grid both limits sit on, which is the smallest gap that
leaves ``min < max`` — the rule the device itself enforces — true with both
values still on the grid the device accepts.
"""

type Bound = Callable[[HeatitWifiPanelCoordinator], float]
"""A minimum or a maximum, answered from coordinator data on every access."""


def _registry_bound(
    descriptor: ParameterDescriptor, bound: float | None, which: str
) -> float:
    """Return one of the registry's own bounds, refusing a row that has none.

    The registry types a bound as optional because its enumerated parameters —
    the *panel mode*, the buttons — carry a closed set of choices instead. A
    ``number`` row for one of those is a mistake, and this is where it is
    caught: ``NUMBERS`` is written by hand, and the alternative to refusing it
    is silently offering a user core's default 0 .. 100 range in place of the
    panel's own.
    """
    if bound is None:
        msg = (
            f"{descriptor.key} has no {which} in the registry, so it cannot be "
            f"a number: an enumerated parameter belongs on a select"
        )
        raise ValueError(msg)
    return bound


def _standing(bound: float) -> Bound:
    """Adapt a bound that does not move to the signature of one that does.

    Ten of the sixteen bounds in §5.2's number rows are the registry's and stay
    put; answering them through the same call as the six that move is what
    keeps the entity free of a static case to branch on.
    """
    return lambda _coordinator: bound


def _lowest_setpoint(coordinator: HeatitWifiPanelCoordinator) -> float:
    """Return the floor of both *setpoint banks*: the *minimum temperature limit*."""
    return coordinator.minimum_temperature


def _highest_setpoint(coordinator: HeatitWifiPanelCoordinator) -> float:
    """Return the ceiling of both banks: the *maximum temperature limit*."""
    return coordinator.maximum_temperature


def _highest_minimum_limit(coordinator: HeatitWifiPanelCoordinator) -> float:
    """Return the most the *minimum* limit may be: the other limit, one step down."""
    return coordinator.maximum_temperature - LIMIT_GAP


def _lowest_maximum_limit(coordinator: HeatitWifiPanelCoordinator) -> float:
    """Return the least the *maximum* limit may be: the other limit, one step up."""
    return coordinator.minimum_temperature + LIMIT_GAP


def _rated_load(coordinator: HeatitWifiPanelCoordinator) -> float:
    """Return the *rated load* in watts: the most the *load limit* may be set to.

    ``maxLoad`` is reported in the same units of 100 W the load limit is
    written in, so the registry's scale is what turns it into watts. A firmware
    that does not report it falls back to the registry's own ceiling; the
    device refuses anything above its model's rating either way (Q17).
    """
    descriptor = PARAMETERS[LOAD_LIMIT]
    # Read from the status rather than through ``coordinator.numeric``, which
    # keys a parameter by its descriptor: this one has none, by the reasoning
    # at :data:`RATED_LOAD_PATH`. Nothing writes it, so there is no *write
    # echo* to prefer either.
    rated = coordinator.data.get_int(RATED_LOAD_PATH)
    if rated is None:
        return _registry_bound(descriptor, descriptor.maximum, "maximum")
    return float(rated * descriptor.scale)


@dataclass(frozen=True, kw_only=True)
class HeatitNumberDescription(NumberEntityDescription):
    """One ``number`` row of §5.2: a parameter, and where its bounds come from."""

    parameter: str
    """The *observed parameter* this row reads and writes, by wire name."""

    minimum_fn: Bound | None = None
    """The lowest value to offer, where §5.2 says it moves with device state.

    ``None`` leaves it to the registry's own bound, which is the answer for
    every row §5.2 does not mark dynamic.
    """

    maximum_fn: Bound | None = None
    """The highest value to offer, on the same terms."""


NUMBERS: tuple[HeatitNumberDescription, ...] = (
    HeatitNumberDescription(
        key="comfort_setpoint",
        parameter="heatingSetpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        minimum_fn=_lowest_setpoint,
        maximum_fn=_highest_setpoint,
        entity_category=EntityCategory.CONFIG,
    ),
    HeatitNumberDescription(
        key="eco_setpoint",
        parameter="ecoSetpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        minimum_fn=_lowest_setpoint,
        maximum_fn=_highest_setpoint,
        entity_category=EntityCategory.CONFIG,
    ),
    HeatitNumberDescription(
        key="minimum_temperature_limit",
        parameter="minimumTemperatureLimit",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        maximum_fn=_highest_minimum_limit,
        entity_category=EntityCategory.CONFIG,
    ),
    HeatitNumberDescription(
        key="maximum_temperature_limit",
        parameter="maximumTemperatureLimit",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        minimum_fn=_lowest_maximum_limit,
        entity_category=EntityCategory.CONFIG,
    ),
    # No device class, on purpose: this is an *offset*, and converting an
    # offset to °F is wrong — one degree Celsius of calibration is 1.8 °F of
    # calibration, not 33.8. Its icon comes from icons.json, which is what a
    # row with no device class to supply one is for.
    HeatitNumberDescription(
        key="sensor_calibration",
        parameter="sensorCalibration",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
    ),
    HeatitNumberDescription(
        key="load_limit",
        parameter=LOAD_LIMIT,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        maximum_fn=_rated_load,
        entity_category=EntityCategory.CONFIG,
    ),
    HeatitNumberDescription(
        key="active_display_brightness",
        parameter="activeDisplayBrightness",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
    HeatitNumberDescription(
        key="standby_display_brightness",
        parameter="standbyDisplayBrightness",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - the platform signature is core's
    entry: HeatitWifiPanelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a number per row whose parameter the panel returned at setup (§5.4).

    Presence is decided once, from the **first** status: a parameter this
    firmware does not return has no entity at all, and one that appears later
    is picked up on reload rather than live.
    """
    coordinator = entry.runtime_data
    async_add_entities(
        HeatitPanelNumber(coordinator, description)
        for description in NUMBERS
        if description.parameter in coordinator.observed_parameters
    )


class HeatitPanelNumber(HeatitParameterEntity, NumberEntity):
    """One panel setting a user gives a value to rather than chooses."""

    entity_description: HeatitNumberDescription

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        description: HeatitNumberDescription,
    ) -> None:
        """Bind to the parameter this row reads and writes.

        The two bounds are resolved to callables here so that every access
        afterwards is one call: a row §5.2 marks dynamic brought its own, and
        every other row takes the registry's, which is the same range the
        client will accept the write against.
        """
        super().__init__(coordinator, description.key, parameter=description.parameter)
        self.entity_description = description
        self._descriptor = PARAMETERS[self._parameter]
        """The registry's own, for the step and the bounds that do not move."""
        self._minimum: Bound = description.minimum_fn or _standing(
            _registry_bound(self._descriptor, self._descriptor.minimum, "minimum")
        )
        self._maximum: Bound = description.maximum_fn or _standing(
            _registry_bound(self._descriptor, self._descriptor.maximum, "maximum")
        )

    @property
    @override
    def native_value(self) -> float | None:
        """Return the reading in user units, a pending *write echo* winning."""
        return self.coordinator.numeric(self._parameter)

    @property
    @override
    def native_step(self) -> float | None:
        """Return the grid this parameter's own values sit on (§2.4).

        Per parameter, not per type: 0.5 °C on the four temperatures, 0.1 °C
        on the calibration, 100 W on the load limit, 10 % on the brightnesses.
        """
        return self._descriptor.step

    @property
    @override
    def native_min_value(self) -> float:
        """Return the minimum, from coordinator data and never cached (§5.4)."""
        return self._minimum(self.coordinator)

    @property
    @override
    def native_max_value(self) -> float:
        """Return the maximum, from coordinator data and never cached (§5.4)."""
        return self._maximum(self.coordinator)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write this row's parameter, and only ever this row's parameter.

        For the two *setpoint banks* that means the named bank is written
        **unconditionally, in any panel mode**: no mode is read and none is
        changed. Verified safe — a comfort write made in Eco is stored and does
        not change what the panel is regulating to (Q14). That is why these two
        exist alongside the climate entity, which can only reach the *live*
        bank.
        """
        await self.coordinator.async_write_parameter(self._parameter, value=value)
