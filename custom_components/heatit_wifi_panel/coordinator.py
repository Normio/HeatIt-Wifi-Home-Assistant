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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from typing import TYPE_CHECKING, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    HeatitConnectionError,
    HeatitMissingFieldError,
    HeatitProtocolError,
    HeatitResponseError,
    PanelStatus,
)
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LOGGER,
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
        return status

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
