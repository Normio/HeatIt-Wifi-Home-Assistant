"""Constants for the Heatit WiFi Panel integration.

Imported by ``api.py``, so this module imports nothing from ``homeassistant``.
"""

import logging

DOMAIN = "heatit_wifi_panel"

LOGGER = logging.getLogger(__package__)

VERIFIED_FIRMWARES: frozenset[str] = frozenset({"1.21"})
"""Every firmware a captured status from a real panel exists for.

Mirrors ``tests/fixtures/observed/fw-*/`` and the README table, and a test
asserts the three agree. A panel on any other version is *unverified*, not
unsupported. ``scripts/check_conformance.py`` reads this to accept a
``verified fw <v>`` row in the conformance register.
"""

STATUS_TIMEOUT_SECONDS = 5.0
"""Per attempt for ``GET /api/status``; a read completes in 30-210 ms (Q43)."""

WRITE_TIMEOUT_SECONDS = 10.0
"""One attempt for a parameter write or a reset, never retried (§3.6)."""

CONNECT_TIMEOUT_SECONDS = 3.0
"""The TCP connect share of either budget: covers WiFi loss, not device speed."""

STATUS_ATTEMPTS = 2
"""A status read is retried once on a connection failure; nothing else is."""

POLL_BUDGET = STATUS_TIMEOUT_SECONDS * STATUS_ATTEMPTS
"""The longest a single status read may take, retry included: 10 s."""

POST_WRITE_REFRESH_DELAY = 1.5
"""Seconds between a write and the refresh that judges it.

The *write echo* is shown at once and this refresh is the authority: a write
reaches ``/api/status`` in 305-632 ms (Q31), so 1.5 s is roughly three times
the longest lag observed, and the delay is a debounce — a burst of writes costs
one refresh, not one each.
"""

MANUFACTURER = "Heatit"
"""``DeviceInfo.manufacturer``; the model comes from the device (§3.5)."""

FALLBACK_DEVICE_NAME = "Heatit WiFi Panel"
"""Entry title and device name when the panel returns no ``name``.

``name`` is free text the MyHeatit app writes and is *not* part of the
*required core*, so a panel that never had a name set still needs a title.
"""

CONF_POLL_INTERVAL = "poll_interval"
"""The only option key: ``ConfigEntry.options`` holds the *poll interval* alone."""

DEFAULT_POLL_INTERVAL = 60
"""Seconds. Every write schedules its own refresh, so the interval governs only
how fast Home Assistant notices *external* changes (§4.6)."""

MIN_POLL_INTERVAL = 30
"""Seconds: three times the *poll budget*."""


def foreign_panel_placeholders(expected_id: str, actual_id: str) -> dict[str, str]:
    """Name both sides of a *foreign panel*, for one message or the other.

    The same two ids reach the user twice — ``config.abort.wrong_panel`` when a
    reconfigure refuses to adopt a replacement, and ``exceptions.foreign_panel``
    when a poll or a setup meets one. Built here so the two call sites and the
    two translated strings cannot drift on the placeholder names; a test asserts
    both strings carry exactly these keys.
    """
    return {"expected_id": expected_id, "actual_id": actual_id}
