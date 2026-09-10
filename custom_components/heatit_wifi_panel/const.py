"""Constants for the Heatit WiFi Panel integration."""

DOMAIN = "heatit_wifi_panel"

#: The firmware versions a real panel has been captured at. A panel on any other
#: version is unverified, not unsupported. ``scripts/check_conformance.py`` reads
#: this to accept a ``verified fw <v>`` row in the conformance register.
VERIFIED_FIRMWARES = frozenset({"1.21"})
