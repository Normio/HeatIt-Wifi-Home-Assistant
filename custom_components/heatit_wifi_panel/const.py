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
unsupported.
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
