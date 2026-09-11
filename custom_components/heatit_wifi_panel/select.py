"""The two selects: the standby display and the physical buttons (§5.2).

Neither of these is a switch, and for two different reasons.

``temperatureDisplay`` has **two meaningful states**: the panel's standby
display shows the setpoint or it shows the measured temperature. Neither is the
absence of the other, so a switch would have to call one of them "on" and leave
the user to guess which.

``disableButtons`` has **three**, and a switch cannot hold three: a boolean
would silently lose *menu locked*. It is named the way the device and the
MyHeatit app name it — Buttons, *enabled* first — and deliberately **not**
inverted into a lock, which would have "off" mean working buttons.

Each description carries the option names and the device value behind each, and
that one mapping is read both ways: an option chosen becomes a value written, a
value read becomes the option shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory

from .entity import HeatitWifiPanelEntity
from .registry import PARAMETERS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator

PARALLEL_UPDATES = 1
"""One write at a time within this platform, on top of the client's own lock."""


@dataclass(frozen=True, kw_only=True)
class HeatitSelectDescription(SelectEntityDescription):
    """One enumerated parameter, as a select."""

    parameter: str
    """The wire name in the registry, which is *not* always ``key`` (§5.2)."""

    states: Mapping[str, bool | int]
    """Each option and the device value behind it, in the order offered.

    The option names are also state-translation keys, resolved at
    ``entity.select.<key>.state.<option>``; the values are the device's own —
    ``false``/``true``, or 0/1/2 — and the registry validates them on the way
    out.
    """


def _select(
    key: str, parameter: str, states: Mapping[str, bool | int]
) -> HeatitSelectDescription:
    """Build a select's description, its options taken from its own states.

    ``options`` is what Home Assistant offers and ``states`` is what each one
    means to the panel; deriving the first from the second is what keeps a
    select from offering an option it cannot write.
    """
    return HeatitSelectDescription(
        key=key,
        parameter=parameter,
        states=states,
        options=list(states),
        entity_category=EntityCategory.CONFIG,
    )


SELECTS: tuple[HeatitSelectDescription, ...] = (
    _select(
        "standby_display",
        "temperatureDisplay",
        MappingProxyType({"setpoint": False, "measured_temperature": True}),
    ),
    _select(
        "buttons",
        "disableButtons",
        MappingProxyType({"enabled": 0, "disabled": 1, "menu_locked": 2}),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - the platform signature is core's
    entry: HeatitWifiPanelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a select for each parameter the panel returned at setup (§5.4)."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeatitPanelSelect(coordinator, description)
        for description in SELECTS
        if description.parameter in coordinator.observed_parameters
    )


class HeatitPanelSelect(HeatitWifiPanelEntity, SelectEntity):
    """One enumerated setting on the panel."""

    entity_description: HeatitSelectDescription

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        description: HeatitSelectDescription,
    ) -> None:
        """Bind to the parameter this select chooses, read at its own path."""
        super().__init__(
            coordinator,
            description.key,
            read_path=PARAMETERS[description.parameter].read_path,
        )
        self.entity_description = description
        self._options_by_value: dict[float | bool, str] = {
            value: option for option, value in description.states.items()
        }
        """The same mapping read the other way: what the panel answers, named."""

    @property
    @override
    def current_option(self) -> str | None:
        """The option the panel's value names, a pending *write echo* winning.

        ``None`` for a value no option names — a firmware that grows a fourth
        button state shows nothing rather than the wrong thing, and adding the
        option is then a deliberate edit with a fixture behind it.
        """
        value = self.coordinator.parameter(self.entity_description.parameter)
        return None if value is None else self._options_by_value.get(value)

    @override
    async def async_select_option(self, option: str) -> None:
        """Write the value behind ``option``; the refresh at 1.5 s settles it."""
        await self.coordinator.async_write_parameter(
            self.entity_description.parameter,
            value=self.entity_description.states[option],
        )
