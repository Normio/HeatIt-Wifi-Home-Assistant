"""Config flow for the Heatit WiFi Panel integration.

The file exists from the scaffold because hassfest errors when a manifest
declares ``config_flow: true`` and no ``config_flow.py`` is present. The steps
themselves arrive with the config flow ticket.
"""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class HeatitWifiPanelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Heatit WiFi Panel."""
