"""The climate entity: the panel as a thermostat (§5.3, ADR-0004).

The panel has one three-way *panel mode* and two *setpoint banks*; a climate
entity has one target temperature. The decision, recorded in ADR-0004, is that
``hvac_modes`` stays ``[OFF, HEAT]``, Eco is a **preset**, and
``target_temperature`` follows the *live setpoint* — jumping when the preset
changes, and blank while the panel is Off. Eco could not be a third
``HVACMode`` in any case: the enum is closed, core coerces ``set_hvac_mode`` to
it, and the entity's ``state`` property raises on a non-member.

Both banks are *also* config ``number`` entities, which is where the honest
per-bank history lives; this entity only ever writes the live one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, override

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    PRESET_COMFORT,
    PRESET_ECO,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .entity import HeatitWifiPanelEntity
from .registry import PARAMETERS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import HeatitWifiPanelConfigEntry, HeatitWifiPanelCoordinator

PARALLEL_UPDATES = 1
"""One write at a time within this platform, on top of the client's own lock."""

KEY: Final = "panel"
"""The entity key: its ``translation_key`` and its unique-id suffix (§5.2)."""

PANEL_MODE: Final = "panelMode"
COMFORT_SETPOINT: Final = "heatingSetpoint"
ECO_SETPOINT: Final = "ecoSetpoint"

MODE_OFF: Final = 0
MODE_HEATING: Final = 1
MODE_ECO: Final = 2

#: The two on-modes, and what each means to a climate entity: the preset it
#: shows, and the *setpoint bank* it is regulating to. Off appears in neither,
#: which is what makes both lookups answer ``None`` there.
MODE_TO_PRESET: Final[dict[int, str]] = {
    MODE_HEATING: PRESET_COMFORT,
    MODE_ECO: PRESET_ECO,
}
MODE_TO_BANK: Final[dict[int, str]] = {
    MODE_HEATING: COMFORT_SETPOINT,
    MODE_ECO: ECO_SETPOINT,
}
PRESET_TO_MODE: Final = {preset: mode for mode, preset in MODE_TO_PRESET.items()}

RELAY_HEATING: Final = "heating"
"""The *relay state* that means the element is on, matched case-insensitively.

The device sends ``Heating`` and ``Idle``; folding the case is the same
robustness the client's success sentinel takes, and here it is the difference
between reporting a running heater and reporting an idle one.
"""


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - the platform signature is core's
    entry: HeatitWifiPanelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the one climate entity.

    Never presence-gated away: the *panel mode* is *required core*, so a status
    without it is not a status at all (§5.4).
    """
    async_add_entities([HeatitPanelClimate(entry.runtime_data)])


class HeatitPanelClimate(HeatitWifiPanelEntity, ClimateEntity):
    """The panel itself: off and heat, comfort and eco, one live setpoint."""

    _attr_name = None
    """This entity *is* the panel, so it takes the device's name (§5.2).

    Its ``translation_key`` therefore serves state and icon translations only —
    ``_attr_name`` is resolved first, and ``None`` counts as set.
    """

    _attr_translation_key = KEY
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    # Core types both of these as lists, and both are read-only in practice:
    # fixed, never computed from live state, so the capability list cannot flap.
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]  # noqa: RUF012
    _attr_preset_modes = [PRESET_COMFORT, PRESET_ECO]  # noqa: RUF012
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        # Mandatory and explicit: the shim that inferred these from
        # ``HVACMode.OFF in hvac_modes`` was deleted in Home Assistant 2025.1,
        # and an area-targeted service call now silently skips an entity that
        # does not declare them.
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: HeatitWifiPanelCoordinator) -> None:
        """Bind to the panel; the *panel mode* is what it reads."""
        super().__init__(coordinator, KEY, read_path=PARAMETERS[PANEL_MODE].read_path)

    @property
    def _panel_mode(self) -> int:
        """The *panel mode*, a pending *write echo* winning over the status.

        Read fresh on every use rather than cached, so that a mode written
        earlier in a service call is the mode the rest of that call sees.
        ``panelMode`` is *required core* and an integer parameter, so the
        status always yields one and the second half is unreachable in
        practice; it is here because the registry's reading is typed for every
        parameter rather than for this one.
        """
        mode = self.coordinator.parameter(PANEL_MODE)
        return mode if isinstance(mode, int) else self.coordinator.data.panel_mode

    @property
    def _live_bank(self) -> str | None:
        """Which *setpoint bank* the panel is regulating to; ``None`` while Off."""
        return MODE_TO_BANK.get(self._panel_mode)

    @property
    @override
    def hvac_mode(self) -> HVACMode:
        """Off or Heat. Eco is a preset, and Heat covers both on-modes."""
        return HVACMode.OFF if self._panel_mode == MODE_OFF else HVACMode.HEAT

    @property
    @override
    def preset_mode(self) -> str | None:
        """Comfort or Eco; ``None`` while Off, where neither is chosen."""
        return MODE_TO_PRESET.get(self._panel_mode)

    @property
    @override
    def hvac_action(self) -> HVACAction:
        """From the *relay state*, never from power, which trails it by ~15 s.

        ``Heating`` is ``HEATING`` in every mode — the element is on, and that
        stays true if a future firmware's frost protection heats while Off.
        ``Idle`` while Off is ``OFF``, which the device has no value for and we
        synthesise; core's convention, and the one place this deliberately
        differs from the dev's floor thermostats.
        """
        if self.coordinator.data.relay_state.casefold() == RELAY_HEATING:
            return HVACAction.HEATING
        return HVACAction.OFF if self._panel_mode == MODE_OFF else HVACAction.IDLE

    @property
    @override
    def current_temperature(self) -> float:
        """The room temperature, *required core* and so always present."""
        return self.coordinator.data.room_temperature

    @property
    @override
    def target_temperature(self) -> float | None:
        """The *live setpoint*; ``None`` while Off, where there is none."""
        bank = self._live_bank
        return None if bank is None else self.coordinator.numeric(bank)

    @property
    @override
    def min_temp(self) -> float:
        """The device's minimum, reported truthfully — no client-side clamping.

        The device bounds both banks itself, enforces min < max and clamps a
        stored setpoint when a limit narrows past it, so there is no
        out-of-bounds display to defend against: a limit change is followed by
        a refresh and the card agrees with the panel again.
        """
        return self.coordinator.minimum_temperature

    @property
    @override
    def max_temp(self) -> float:
        """The device's maximum, on the same terms as :attr:`min_temp`."""
        return self.coordinator.maximum_temperature

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Off writes Off; Heat from Off lands in Heating and never leaves Eco.

        Turning on means comfort: the panel has no "on" verb and remembers
        nothing, so Home Assistant invents no memory either. Heat while already
        Heating **or Eco** is a no-op, because both already *are* Heat — the
        alternative silently drags a user out of Eco.
        """
        if hvac_mode is HVACMode.OFF:
            await self.coordinator.async_write_parameter(PANEL_MODE, value=MODE_OFF)
        elif self._panel_mode == MODE_OFF:
            await self.coordinator.async_write_parameter(PANEL_MODE, value=MODE_HEATING)

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Send the mode, and only the mode — never a temperature with it.

        Chosen while Off, this turns the panel on in that mode: a preset is an
        explicit choice of on-mode.
        """
        await self.coordinator.async_write_parameter(
            PANEL_MODE, value=PRESET_TO_MODE[preset_mode]
        )

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write the *live bank*, re-read from device state inside this call.

        A cached bank would write the wrong one when the panel's mode changed
        under us — from the app, from its own buttons, or from the
        ``hvac_mode`` this very call carries, which core passes through
        unvalidated and unapplied. So the mode is applied first and the bank is
        asked for afterwards.

        While Off there is no live bank and no target to move, and this refuses
        loudly rather than guessing one, so an automation learns it did nothing.
        The signature takes ``**kwargs`` because core leaks ``entity_id`` into
        them.
        """
        hvac_mode: HVACMode | None = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None:
            await self.async_set_hvac_mode(hvac_mode)
        bank = self._live_bank
        if bank is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="set_temperature_while_off",
            )
        await self.coordinator.async_write_parameter(
            bank, value=kwargs[ATTR_TEMPERATURE]
        )
