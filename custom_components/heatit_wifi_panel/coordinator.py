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

The two resets are here on the same terms, and the *energy counter* one brings
its own judgement with it: a reset has no echo to compare against, so the only
check available is whether the counter fell, and the poll is what can see that
(§5.5).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from typing import TYPE_CHECKING, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    TOTAL_CONSUMPTION,
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
    RESET_VERIFY_DELAY,
    VERIFIED_FIRMWARES,
    foreign_panel_placeholders,
)
from .registry import PARAMETERS, SETPOINT_MAXIMUM, SETPOINT_MINIMUM

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

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
class _PendingReset:
    """An *energy counter* reset the panel acknowledged, awaiting its verdict.

    Only a reset with something to verify is ever recorded: a pre-reset reading
    of zero has nowhere to fall, so §5.5 clears the record instead of keeping
    one that could only ever read as a failure.
    """

    pre_reset: float
    """What the counter read when the button was pressed."""

    judge_after: float
    """The ``monotonic()`` reading from which a poll may judge this reset.

    :data:`RESET_VERIFY_DELAY` after the acknowledgement, and the same question
    :attr:`_PendingEcho.judge_after` answers for a write: which reading is late
    enough to settle it. The delay is longer here because the evidence is
    weaker — a write has an echo to compare against and a reset has nothing
    but the counter falling.
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


@contextmanager
def _device_errors() -> Iterator[None]:
    """Re-raise whatever the client raises as §6.4's ``HomeAssistantError``.

    One table, one place: a write and a reset fail in the same ways and the
    user reads the same translated messages either way, with the device's
    ``reason`` passed through verbatim and never parsed. Only
    :class:`HeatitParameterRejected` is particular to a write — a reset carries
    no parameter, and the device's ``400`` on one reaches us as a plain
    response error.

    A ``400`` is deliberately **not** a user error: Home Assistant's own layers
    and the registry have both bounded the value already, so one that still
    reaches the device means our bounds and the device's disagree.
    """
    try:
        yield
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
        self._warned_anomalies: set[str] = set()
        """What §7.2's one warning has already been spent on, by anomaly.

        A *silent undo* is counted per parameter (§6.5) and an unverified
        energy reset once per entry lifetime (§5.5), which is why the keys are
        namespaced strings rather than parameter names alone.
        """
        self._pending_reset: _PendingReset | None = None
        """The *energy counter* reset awaiting the poll that judges it (§5.5)."""

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

    def numeric(self, key: str) -> float | None:
        """One parameter as a float; ``None`` when absent or not a number.

        :meth:`parameter` answers in the registry's declared type, which for
        three parameters is a boolean and for two an enumerated integer. Every
        caller that wants a temperature, a wattage or a percentage wants one
        float and wants anything else to read as no reading at all, so the
        coercion lives here rather than once per platform.
        """
        value = self.parameter(key)
        return None if value is None or isinstance(value, bool) else float(value)

    @property
    def minimum_temperature(self) -> float:
        """The *minimum temperature limit*, or the panel's own floor below it.

        Both limits are optional parameters under §5.4's presence-gating, so a
        firmware returning neither still has a thermostat and two setpoints.
        What bounds them then is what bounds them on the device — the registry's
        own bounds on a *setpoint bank*, which every setpoint write is already
        validated against.

        Every platform that needs the limits needs them on exactly these terms,
        so the fallback is written once here rather than per platform.
        """
        return self._limit("minimumTemperatureLimit", SETPOINT_MINIMUM)

    @property
    def maximum_temperature(self) -> float:
        """The *maximum temperature limit*, or the panel's own ceiling above it."""
        return self._limit("maximumTemperatureLimit", SETPOINT_MAXIMUM)

    def _limit(self, key: str, absolute: float) -> float:
        limit = self.numeric(key)
        return absolute if limit is None else limit

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
            with _device_errors():
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
        else:
            self._echoes[key] = _PendingEcho(
                value=applied, judge_after=monotonic() + POST_WRITE_REFRESH_DELAY
            )
            self.async_update_listeners()
        finally:
            # Ordered deliberately: the echo is recorded before the refresh is
            # asked for, so no ordering of the two can show a stale value.
            await self.async_request_refresh()

    async def async_reset_energy(self) -> None:
        """Zero the *energy counter*, and record what it read on the way (§5.5).

        A reset is a write with no *write echo*: the panel acknowledges it and
        the only question left is whether the counter fell. So the reading at
        the moment of the press is kept, timestamped, and handed to the first
        poll late enough to settle it — :meth:`_judge_reset`.

        A press made at ``0.00`` still sends the request: the last reading may
        be a whole *poll interval* stale and the request is harmless. What it
        does not do is leave a record, because a zero cannot fall below itself.

        The record is written **after** the acknowledgement, so a press the
        panel never answered replaces nothing: §5.5's "a second press replaces
        the pending record" is about a second *ack*, and a request that failed
        leaves an earlier one still waiting for its verdict — which it should,
        because that earlier reset may well have taken.
        """
        pre_reset = self.data.get_float(TOTAL_CONSUMPTION)
        await self._async_reset(self.client.reset_kwh)
        self._pending_reset = (
            _PendingReset(
                pre_reset=pre_reset, judge_after=monotonic() + RESET_VERIFY_DELAY
            )
            if pre_reset
            else None
        )

    async def async_reset_settings(self) -> None:
        """Put every setting back to its default; nothing here is verified.

        The panel applies this **staggered over about 5 s**, so the refresh at
        :data:`POST_WRITE_REFRESH_DELAY` reports a partial reset and the next
        poll completes it. There is nothing to retry and nothing to fix: every
        entity shows whatever the panel says at the moment it is asked.
        """
        await self._async_reset(self.client.reset_settings)

    async def _async_reset(self, reset: Callable[[], Awaitable[None]]) -> None:
        """Send one reset, translate its failure, and schedule the refresh.

        Never retried (§3.6), and availability is never touched: the reset
        raises to whoever pressed the button and the next poll decides whether
        the panel is there (§6). The refresh is scheduled either way, for the
        same reason a failed write schedules one — the panel commits in
        milliseconds, so a lost *response* says nothing about what it did.
        """
        try:
            with _device_errors():
                await reset()
        finally:
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
        self._judge_reset(status)
        return status

    def _log_anomaly(self, spent: str, message: str, *args: object) -> None:
        """Report one device anomaly at §7.2's cadence: warning once, then debug.

        Both anomalies a poll can turn up — a *silent undo*, and a reset the
        *energy counter* did not follow — are told this way: loud the first
        time, and debug from then on, so a panel misbehaving on every poll
        cannot bury the log in its own noise. ``spent`` is what the one warning
        is spent on, which is per parameter for one of them and once per entry
        lifetime for the other; the cadence is the same either way and lives
        here.
        """
        first = spent not in self._warned_anomalies
        self._warned_anomalies.add(spent)
        LOGGER.log(logging.WARNING if first else logging.DEBUG, message, *args)

    def _judge_reset(self, status: PanelStatus) -> None:
        """Say once when a reset the panel acknowledged left the counter alone.

        The **first** poll completing :data:`RESET_VERIFY_DELAY` or later after
        the acknowledgement judges it, and any refresh completing earlier —
        scheduled or write-triggered — is ignored: the counter reads ``0.00``
        within 5 s of the ack (Q45), so an earlier reading proves nothing. A
        ``warning`` once per entry lifetime, ``debug`` after that (§7.2).

        **A counter drop Home Assistant did not cause is never mentioned.**
        Only a pending record is ever judged, so a reset from the MyHeatit app
        — a legitimate act the statistics engine already reads as a new meter
        cycle — passes in silence.

        A counter the panel has stopped returning ends the record with no
        verdict, and says so at ``debug``. The *energy counter* is not a
        *parameter*: it has no registry descriptor, so :meth:`_note_presence`
        never sweeps it and the absence is already reported the way §6.3
        reports one — the energy sensor goes unavailable. What would be wrong
        is blaming the panel for a reset that cannot be checked, so the line
        records that the check was abandoned and nothing more.
        """
        pending = self._pending_reset
        if pending is None or monotonic() < pending.judge_after:
            return
        self._pending_reset = None
        current = status.get_float(TOTAL_CONSUMPTION)
        if current is None:
            LOGGER.debug(
                "the energy counter is absent from the panel's status, so the "
                "reset acknowledged at %s kWh cannot be verified",
                pending.pre_reset,
            )
            return
        if current < pending.pre_reset:
            return
        self._log_anomaly(
            "energy-reset",
            "the panel acknowledged an energy counter reset at %s kWh and its "
            "status now reads %s kWh; the counter was not zeroed",
            pending.pre_reset,
            current,
        )

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
            self._log_anomaly(
                f"silent-undo:{key}",
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
