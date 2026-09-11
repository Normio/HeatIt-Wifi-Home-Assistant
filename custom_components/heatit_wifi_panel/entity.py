"""The base entity every platform builds on (§3.5).

Three things live here, and they are the three every one of the six platforms
would otherwise get subtly different: which device an entity belongs to, what
its unique id is, and when it is unavailable.

:class:`HeatitParameterEntity` is the second base, for the platforms whose
entity *is* one *observed parameter*: it resolves that parameter's read path in
the registry once, so no platform module repeats the lookup.

**Names are not one of them.** Every entity sets ``has_entity_name`` and takes
its name from ``translation_key`` resolved in ``translations/en.json``;
``_attr_name`` is checked *before* ``translation_key`` in core's resolution and
``_attr_name = None`` counts as set, so an entity that sets both silently loses
its key. The one entity that sets ``_attr_name = None`` is the climate entity,
marking it the main feature.
"""

from __future__ import annotations

from typing import override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

# Imported for real, not under ``TYPE_CHECKING``: the class subscript below is
# evaluated when this module is imported, whatever the annotations do.
from .coordinator import HeatitWifiPanelCoordinator
from .registry import PARAMETERS


class HeatitWifiPanelEntity(CoordinatorEntity[HeatitWifiPanelCoordinator]):
    """One reading or one control on one panel."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        key: str,
        *,
        read_path: str | None = None,
    ) -> None:
        """Bind to the panel's coordinator, named by ``key`` (§5.2).

        ``key`` is both the ``translation_key`` and the suffix of the unique
        id, so the two cannot drift. ``read_path`` is the dotted path in the
        *status* this entity reads, and it is what decides availability once
        the panel itself is answering; an entity with nothing to read — one
        that only writes — leaves it ``None``.

        The device is joined by identifiers alone. It is registered from the
        first status in ``__init__.py``, where `name` and the *assigned room*
        are spent once and never overwritten (§4.4); repeating them here would
        undo a rename in Home Assistant on every restart.
        """
        super().__init__(coordinator)
        self._read_path = read_path
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.data.device_id}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.device_id)}
        )

    @property
    @override
    def available(self) -> bool:
        """``super().available`` **and** this entity's read path resolving.

        The first half is the poll, the sole judge of whether the panel is
        there (§6.1). The second is §6.3: a parameter that vanishes from the
        status makes its own entity unavailable and leaves every other one
        alone, and nothing is removed from the entity registry either way.
        """
        if not super().available:
            return False
        return (
            self._read_path is None
            or self.coordinator.data.get(self._read_path) is not None
        )


class HeatitParameterEntity(HeatitWifiPanelEntity):
    """One *observed parameter*, as one entity.

    Every write platform but the climate entity is this shape: one parameter,
    read through the coordinator and written back through it. What is shared is
    only the binding — the parameter's wire name, and the read path the registry
    holds for it — so that each platform module carries what makes it that
    platform and not the lookup every one of them would otherwise repeat.

    Reading and writing are deliberately **not** wrapped here. They are two
    calls on the coordinator, which is where the *write echo*, the debounced
    refresh and the *silent undo* already live; a pair of methods forwarding to
    it would only put a second name on each.
    """

    def __init__(
        self,
        coordinator: HeatitWifiPanelCoordinator,
        key: str,
        *,
        parameter: str,
    ) -> None:
        """Bind to one registry parameter, read at the path the registry gives.

        ``key`` is the entity's, from §5.2, and ``parameter`` is the wire name;
        the two differ wherever the device's name for a setting is not the name
        a user should read — ``sensorMode`` is the External sensor switch, and
        ``disableButtons`` is the Buttons select.
        """
        super().__init__(coordinator, key, read_path=PARAMETERS[parameter].read_path)
        self._parameter = parameter
        """The wire name: what the coordinator is asked for and written with."""
