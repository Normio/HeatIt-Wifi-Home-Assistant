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
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
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


@dataclass(frozen=True, slots=True)
class _PendingEcho:
    """A *write echo* shown to the user, waiting for the refresh that judges it."""

    value: object
    """What the panel said it applied, in user units."""

    judge_after: float
    """The ``monotonic()`` reading from which a status may judge this echo.

    A status read *earlier* than this may still be showing the value the panel
    held before the write — it commits in 305-632 ms (Q31) — so judging one
    would report a *silent undo* that did not happen. This is §5.5's rule for
    the energy reset, applied to the same question: which reading is late
    enough to settle a write.
    """


@dataclass(frozen=True, slots=True)
class PollRecord:
    """What the last poll did, for the diagnostics download alone (§7.3).

    Nothing branches on it and no entity reads it: it exists so that a user
    who reports "it goes unavailable sometimes" attaches the answer.
    """

    outcome: str
    """``ok``, or the poll's own translation key — ``cannot_connect``,
    ``missing_field``, ``invalid_response``, ``foreign_panel``.

    ``unknown`` covers what carries no key at all: a cancelled refresh, or a
    failure that is a bug rather than a panel being a panel.
    """

    duration_seconds: float
    """Wall-clock seconds for the whole poll, the status read's retry included."""

    retried: bool
    """Whether that status read used its one retry (§3.6)."""


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
        self.last_poll: PollRecord | None = None
        """The last poll, good or bad; ``None`` until the first one returns."""
        self._appeared_parameters: set[str] = set()
        self._presence_recorded = False
        self._echoes: dict[str, _PendingEcho] = {}
        """The *write echo* of each write awaiting its refresh, by wire name."""
        self._undone_parameters: set[str] = set()
        """Those a *silent undo* has already been warned about (§6.5)."""

    def parameter(self, key: str) -> int | float | bool | None:
        """One parameter's value in user units, a pending *write echo* winning.

        The echo is what the panel says it *applied*, so it is what an entity
        shows until the refresh at :data:`POST_WRITE_REFRESH_DELAY` replaces it
        with what the panel actually reports (§5.4).

        ``None`` when this firmware does not return the parameter at all — the
        entity is then unavailable rather than guessing — and for anything the
        registry's declared type cannot absorb, which is the same answer
        :meth:`ParameterDescriptor.decode` gives and for the same reason.
        """
        pending = self._echoes.get(key)
        value = (
            pending.value if pending is not None else PARAMETERS[key].read(self.data)
        )
        return value if isinstance(value, int | float | bool) else None

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
        except ValueError as err:
            # The registry refused it before a request existed, so the panel
            # never saw it. Core checks a service call against ``min_temp`` and
            # ``max_temp`` but never against ``target_temperature_step``, so an
            # off-grid value does reach here, and §6.4 wants every write error
            # translated rather than raised raw at whoever called the service.
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
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
        else:
            self._echoes[key] = _PendingEcho(
                value=applied, judge_after=monotonic() + POST_WRITE_REFRESH_DELAY
            )
            self.async_update_listeners()
        finally:
            # Ordered deliberately: the echo is recorded before the refresh is
            # asked for, so no ordering of the two can show a stale value.
            await self.async_request_refresh()

    @override
    async def _async_update_data(self) -> PanelStatus:
        """Time one poll and record what it did, then let it stand or fail.

        The record is written on the way out of either path, so the download
        of §7.3 describes the poll that actually just happened rather than the
        last one that happened to succeed.
        """
        started = monotonic()
        outcome = "unknown"
        try:
            status = await self._poll()
        except HomeAssistantError as err:
            outcome = err.translation_key or "unknown"
            raise
        else:
            outcome = "ok"
            return status
        finally:
            self.last_poll = PollRecord(
                outcome=outcome,
                duration_seconds=round(monotonic() - started, 3),
                retried=self.client.last_status_retried,
            )

    async def _poll(self) -> PanelStatus:
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
        """Compare each *write echo* this status is late enough to judge.

        A mismatch is a *silent undo*: a write the panel acknowledged and then
        did not apply. Client-side quantisation has already removed the snap
        case, so what remains is a genuine refusal disguised as success — a
        ``warning`` once per parameter per entry lifetime, ``debug`` after that
        (§6.5, §7.2). A parameter that has *vanished* reads as ``None`` and is
        not judged: :meth:`_note_presence` has already said so, and one absence
        is not two anomalies.

        An echo the panel has not had :data:`POST_WRITE_REFRESH_DELAY` to
        commit stays pending, and the entity goes on showing it. That is the
        scheduled poll that lands inside the window — core cancels the
        debounced refresh when one does, so without this the poll would both
        report a *silent undo* that never happened and drop the user's value
        back for a whole *poll interval*.
        """
        now = monotonic()
        for key, pending in list(self._echoes.items()):
            if now < pending.judge_after:
                continue
            del self._echoes[key]
            applied = PARAMETERS[key].read(status)
            if applied is None or applied == pending.value:
                continue
            first = key not in self._undone_parameters
            self._undone_parameters.add(key)
            LOGGER.log(
                logging.WARNING if first else logging.DEBUG,
                "the panel acknowledged %s=%r and its status now reads %r; the "
                "write was accepted and not applied",
                key,
                pending.value,
                applied,
            )

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
