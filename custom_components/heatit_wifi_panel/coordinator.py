"""The config entry alias and the coordinator: one poll, one panel (§3.4).

The poll is the sole judge of availability (§6). Setup, writes and resets never
decide whether the panel is there — they raise to whoever called them and let
the next status read settle it. So the whole failure model lives here: a failed
poll is ``UpdateFailed`` and every entity goes unavailable on the **first** one,
the only dropped-packet tolerance being the single status retry one layer down
inside the *poll budget*.

The one exception is a *foreign panel*, which is ``ConfigEntryError``. Raised
from the first refresh it is a permanent setup failure; raised from a scheduled
poll ``DataUpdateCoordinator`` catches it, logs one error line and fails the
poll — never escalating it, and never accepting the foreign status as data.

Writing is here too, and for the same reason: a write is optimistic, and the
poll is what settles it. :meth:`HeatitWifiPanelCoordinator.async_write_parameter`
is the one write path every platform uses, so the *write echo*, the debounced
refresh at :data:`POST_WRITE_REFRESH_DELAY` and the *silent undo* warning are
written once rather than six times.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    HeatitConnectionError,
    HeatitMissingFieldError,
    HeatitParameterRejected,
    HeatitProtocolError,
    HeatitResponseError,
    PanelStatus,
)
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER,
    POST_WRITE_REFRESH_DELAY,
    VERIFIED_FIRMWARES,
    foreign_panel_placeholders,
)
from .registry import PARAMETERS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import HeatitClient

type HeatitWifiPanelConfigEntry = ConfigEntry[HeatitWifiPanelCoordinator]
"""The entry with its runtime data typed. ``hass.data`` is untouched (§3.4)."""


def poll_interval(entry: ConfigEntry) -> timedelta:
    """Read the *poll interval* from the entry's options, in seconds.

    Options carry the interval alone, and an option change is applied by
    reloading the entry — ``update_interval`` is never retimed in place (§4.6).
    """
    seconds = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    return timedelta(seconds=seconds)


class HeatitWifiPanelCoordinator(DataUpdateCoordinator[PanelStatus]):
    """Read one panel's whole *status* on a schedule, and judge availability."""

    config_entry: HeatitWifiPanelConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HeatitWifiPanelConfigEntry,
        client: HeatitClient,
    ) -> None:
        """Bind to one entry and one client, at the entry's *poll interval*."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=poll_interval(entry),
            # Core's own debouncer, retimed: every write asks for a refresh and
            # a burst of them collapses into the one that judges them all.
            # ``immediate=False`` is the whole point — refreshing *now* would
            # read the panel before it has committed the write (Q31).
            request_refresh_debouncer=Debouncer(
                hass,
                LOGGER,
                cooldown=POST_WRITE_REFRESH_DELAY,
                immediate=False,
            ),
        )
        self.client = client
        self.observed_parameters: frozenset[str] = frozenset()
        """The parameters the panel returned on the **first** poll.

        Presence is decided once, at setup: a parameter appearing later is
        logged at debug and waits for a reload, and no entity is added or
        removed at runtime (§6.3).
        """
        self.vanished_parameters: set[str] = set()
        """Those of :attr:`observed_parameters` the panel has stopped returning."""
        self._appeared_parameters: set[str] = set()
        self._presence_recorded = False
        self._echoes: dict[str, object] = {}
        """The *write echo* of each write awaiting its refresh, by wire name."""
        self._undone_parameters: set[str] = set()
        """Those a *silent undo* has already been warned about (§6.5)."""

    def value_of(self, key: str) -> float | None:
        """One parameter's value in user units, a pending *write echo* winning.

        The echo is what the panel says it *applied*, so it is what an entity
        shows until the refresh at :data:`POST_WRITE_REFRESH_DELAY` replaces it
        with what the panel actually reports (§5.4).

        ``None`` when this firmware does not return the parameter at all — the
        entity is then unavailable rather than guessing. The view is numeric,
        which covers every parameter behind a climate or number entity; a
        boolean one reads as ``None`` here and wants its own accessor.
        """
        value = (
            self._echoes[key]
            if key in self._echoes
            else PARAMETERS[key].read(self.data)
        )
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)

    async def async_write_parameter(self, key: str, *, value: float | bool) -> None:
        """Write one parameter: the echo shows now, the refresh decides (§5.4).

        ``value`` is in user-facing units, and keyword-only: a bare ``True``
        at a call site says nothing about which switch it flips.

        Every client failure becomes a ``HomeAssistantError`` carrying §6.4's
        translation key, with the device's ``reason`` passed through verbatim;
        a ``400`` is *not* a user error: Home Assistant's own layers and the
        registry have both bounded the value already, so one that still reaches
        the device means our bounds and the device's disagree.

        The refresh is scheduled whether or not the write succeeded: the panel
        commits within 300-600 ms, so a timeout on the *response* does not mean
        the value did not stick. Availability is never touched here — the next
        poll decides whether the panel is gone (§6.4).
        """
        try:
            applied = await self.client.set_parameter(key, value)
        except HeatitParameterRejected as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="parameter_rejected",
                translation_placeholders={
                    "parameter": err.parameter,
                    "reason": err.reason,
                },
            ) from err
        except HeatitConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except (HeatitProtocolError, HeatitResponseError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unexpected_response",
                translation_placeholders={"status": str(err)},
            ) from err
        finally:
            await self.async_request_refresh()
        self._echoes[key] = applied
        self.async_update_listeners()

    @override
    async def _async_update_data(self) -> PanelStatus:
        """Read one status, or fail the poll. There is no third outcome."""
        try:
            status = await self.client.get_status()
        except HeatitConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except HeatitMissingFieldError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="missing_field",
                translation_placeholders={"field": err.path},
            ) from err
        except (HeatitProtocolError, HeatitResponseError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_response",
                translation_placeholders={"error": str(err)},
            ) from err

        expected_id = self.config_entry.unique_id
        if status.device_id != expected_id:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="foreign_panel",
                translation_placeholders=foreign_panel_placeholders(
                    str(expected_id), status.device_id
                ),
            )

        self._note_presence(status)
        self._judge_echoes(status)
        return status

    def _judge_echoes(self, status: PanelStatus) -> None:
        """Compare each pending *write echo* with what the panel now reports.

        A mismatch is a *silent undo*: a write the panel acknowledged and then
        did not apply. Client-side quantisation has already removed the snap
        case, so what remains is a genuine refusal disguised as success — a
        ``warning`` once per parameter per entry lifetime, ``debug`` after that
        (§6.5, §7.2). A parameter that has *vanished* reads as ``None`` and is
        not judged: :meth:`_note_presence` has already said so, and one absence
        is not two anomalies.
        """
        for key, echoed in self._echoes.items():
            applied = PARAMETERS[key].read(status)
            if applied is None or applied == echoed:
                continue
            first = key not in self._undone_parameters
            self._undone_parameters.add(key)
            LOGGER.log(
                logging.WARNING if first else logging.DEBUG,
                "the panel acknowledged %s=%r and its status now reads %r; the "
                "write was accepted and not applied",
                key,
                echoed,
                applied,
            )
        self._echoes.clear()

    def _note_presence(self, status: PanelStatus) -> None:
        """Fix the observed parameters at setup, then log every transition.

        The levels are §7.2's: a parameter that vanishes is a ``warning`` once,
        its return an ``info``, and one that was never there at setup a
        ``debug``. Nothing here repeats per poll.
        """
        present = frozenset(
            key
            for key, descriptor in PARAMETERS.items()
            if descriptor.present_in(status)
        )
        if not self._presence_recorded:
            self._presence_recorded = True
            self.observed_parameters = present
            self._note_firmware(status)
            LOGGER.debug("observed parameters at setup: %s", sorted(present))
            return

        vanished = self.observed_parameters - present - self.vanished_parameters
        for key in sorted(vanished):
            self.vanished_parameters.add(key)
            LOGGER.warning(
                "%s was present when this panel was set up and is now absent "
                "from its status; its entity is unavailable until it returns",
                key,
            )
        for key in sorted(self.vanished_parameters & present):
            self.vanished_parameters.discard(key)
            LOGGER.info("%s is back in the panel's status", key)
        # Once per *transition*, so a late parameter that goes away again is
        # forgotten and its return is a second line: two appearances is the
        # record that the panel is flapping rather than that it changed once.
        self._appeared_parameters &= present
        appeared = present - self.observed_parameters - self._appeared_parameters
        for key in sorted(appeared):
            self._appeared_parameters.add(key)
            LOGGER.debug(
                "%s appeared after setup; presence is fixed at setup, so it is "
                "picked up on the next reload or restart",
                key,
            )

    def _note_firmware(self, status: PanelStatus) -> None:
        """One ``info`` line per setup when no fixture exists for this firmware.

        An absent ``firmware`` is *unverified*, not an error (§6.3).
        """
        if status.firmware in VERIFIED_FIRMWARES:
            return
        LOGGER.info(
            "this panel reports firmware %s, which no captured status covers; "
            "the verified firmwares are %s. Nothing is disabled — a diagnostics "
            "download from this panel is what admits it",
            status.firmware if status.firmware is not None else "no version at all",
            ", ".join(sorted(VERIFIED_FIRMWARES)),
        )
