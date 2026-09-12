"""The diagnostics download: one entry, one panel, one bug report (§7.3).

``async_get_config_entry_diagnostics`` **only**. One entry is one device
(§4.7), so a device download would repeat this one word for word.

Three scrubs meet here, and the differences between them are the point.
``async_redact_data`` replaces values by dict **key**. That is right for
``entry.data``, where the sensitive thing is the key ``host``. It can do
nothing for the ``raw`` body, a *string* of JSON as the panel sent it. There
the wire-level scrub of §7.1 replaces the four identifiers in place. That is
the same replacement ``scripts/capture_fixtures.py`` writes into a fixture.
So that body is a capture of this panel, one that keeps the fields the parser
does not model. Neither works on a **header**, which names nothing and could
carry anything. So a header value is scrubbed by looking for this panel's own
identifiers in it (:func:`~.api.redact_text`). One field list, three shapes
of text.

So a download from an unverified panel is a fixture candidate. It is one
``name`` replacement short of a committed capture: §8.3's fifth placeholder,
which the capture script alone makes. ``name`` and ``room`` survive every
scrub here. They are human labels, not identifiers, and ``name`` is the
evidence that the charset-less UTF-8 decode is required.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST

from .api import redact_status, redact_status_bytes, redact_text
from .const import VERIFIED_FIRMWARES
from .coordinator import poll_interval

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

    from .api import HeatitClient
    from .coordinator import HeatitWifiPanelConfigEntry

TO_REDACT = {CONF_HOST}
"""The entry's one key, and the user's local address.

The download is meant to be attachable to a public issue, and §7.1 scrubs
``Network.ipAddress`` out of the status for that reason. The same address
reached by another name is no different. The panel needs no credential, so
there is nothing else in ``entry.data`` to hide.
"""


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001  # the platform's signature
    entry: HeatitWifiPanelConfigEntry,
) -> dict[str, Any]:
    """Return what a bug report needs: the panel, the last poll, the raw bytes."""
    coordinator = entry.runtime_data
    status = coordinator.data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        # §7.3 wants the *poll interval* in the download, and ``options`` is
        # empty until the user opens the options flow. The interval in force
        # is a fact about the panel; the stored options are a fact about the
        # entry.
        "poll_interval_seconds": poll_interval(entry).total_seconds(),
        "status": redact_status(status.document),
        "firmware": status.firmware,
        "firmware_verified": status.firmware in VERIFIED_FIRMWARES,
        "observed_parameters": sorted(coordinator.observed_parameters),
        "vanished_parameters": sorted(coordinator.vanished_parameters),
        "last_poll": (asdict(coordinator.last_poll) if coordinator.last_poll else None),
        "raw": _raw_status(coordinator.client, status.document),
    }


def _raw_status(
    client: HeatitClient, document: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Return the last status body and headers as received, scrubbed at the wire.

    The body is the panel's own bytes, with key order, spacing and ``0.00``
    intact, decoded for the JSON download. ``errors="replace"`` cannot fire
    on a body that parsed. It is there so a body that did *not* parse is
    still reported, not raised as an exception inside diagnostics.

    ``document`` is the parsed status the identifiers are read out of,
    because a header carries values with no key to find them by.
    """
    if client.last_raw_body is None:
        return None
    return {
        "body": redact_status_bytes(client.last_raw_body).decode("utf-8", "replace"),
        "headers": {
            name: redact_text(value, document)
            for name, value in (client.last_raw_headers or {}).items()
        },
    }
