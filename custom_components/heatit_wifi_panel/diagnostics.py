"""The diagnostics download: one entry, one panel, one bug report (§7.3).

``async_get_config_entry_diagnostics`` **only** — one entry is one device
(§4.7), so a device download would repeat this one word for word.

Two scrubs meet here, and the difference between them is the point.
``async_redact_data`` replaces values by dict **key**, which is exactly right
for ``entry.data``, where the sensitive thing is the key ``host``. It can do
nothing for the ``raw`` section, which is a *string* of JSON as the panel sent
it: there the shared wire-level scrub of §7.1 substitutes the four identifiers
in place, the same substitution ``scripts/capture_fixtures.py`` writes into a
fixture. So the raw section of a download from an unverified panel **is** a
fixture candidate, byte for byte, and that is what shipping it is for — it
preserves the fields the parser does not model.

``name`` and ``room`` survive both scrubs. They are human labels rather than
identifiers, and ``name`` is the evidence that the charset-less UTF-8 decode is
required; the fixture-only fifth placeholder is the capture script's alone
(§8.3).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST

from .api import redact_status, redact_status_bytes
from .const import VERIFIED_FIRMWARES

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import HeatitClient
    from .coordinator import HeatitWifiPanelConfigEntry

TO_REDACT = {CONF_HOST}
"""The entry's one key, and the user's local address.

The download is meant to be attachable to a public issue, and §7.1 scrubs
``Network.ipAddress`` out of the status for that reason; the same address
reached by another name is no different. The panel needs no credential — there
is nothing else in ``entry.data`` to hide.
"""


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001 - the platform's signature
    entry: HeatitWifiPanelConfigEntry,
) -> dict[str, Any]:
    """Return what a bug report needs: the panel, the last poll, the raw bytes."""
    coordinator = entry.runtime_data
    status = coordinator.data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "status": redact_status(status.document),
        "firmware": status.firmware,
        "firmware_verified": status.firmware in VERIFIED_FIRMWARES,
        "observed_parameters": sorted(coordinator.observed_parameters),
        "vanished_parameters": sorted(coordinator.vanished_parameters),
        "last_poll": (asdict(coordinator.last_poll) if coordinator.last_poll else None),
        "raw": _raw_status(coordinator.client),
    }


def _raw_status(client: HeatitClient) -> dict[str, Any] | None:
    """Return the last status body and headers as received, scrubbed at the wire.

    The body is the panel's own bytes — key order, spacing and ``0.00``
    intact — decoded for the JSON download. ``errors="replace"`` cannot fire
    on a body that parsed, and is there so that a body that did *not* is still
    reportable rather than an exception inside diagnostics.
    """
    if client.last_raw_body is None:
        return None
    return {
        "body": redact_status_bytes(client.last_raw_body).decode("utf-8", "replace"),
        "headers": dict(client.last_raw_headers or {}),
    }
