"""Config flow for the Heatit WiFi Panel integration (§4).

Three steps and an options flow, all host-only. Every one of them validates
by reading a *status* through the client's own parser: 200, decodable and the
*required core* present. That is because the *device id* is the identity and
it lives nowhere else, not in a DHCP packet and not in a form field.

Validation here is stricter than setup on purpose (§6.2): someone typing an
address gets an immediate answer, not a retry loop. ``model`` never
gates anything. It is used for ``DeviceInfo.model``, where its absence costs
nothing.

This module is held at **100 % line coverage** by ``scripts/check.sh``. It is
small, and a missed path here is a user-facing bug.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import HeatitClient, HeatitConnectionError, HeatitError
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    FALLBACK_DEVICE_NAME,
    MIN_POLL_INTERVAL,
    foreign_panel_placeholders,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

    from .api import PanelStatus

HOST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="off")
        )
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
            NumberSelector(
                NumberSelectorConfig(
                    min=MIN_POLL_INTERVAL,
                    step=1,
                    unit_of_measurement=UnitOfTime.SECONDS,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Coerce(int),
        )
    }
)


class HeatitWifiPanelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Heatit WiFi Panel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a panel by its address. Adding is adding: it never repoints."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            status, errors = await self._async_validate(host)
            if status is not None:
                await self.async_set_unique_id(status.device_id)
                # Bare, without ``updates=``: changing an address is the
                # reconfigure step's job, so re-adding a moved panel aborts
                # instead of silently rewriting an existing entry (§4.2).
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=status.name or FALLBACK_DEVICE_NAME,
                    data={CONF_HOST: host},
                )
        return self.async_show_form(
            step_id="user", data_schema=HOST_SCHEMA, errors=errors
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Follow a configured panel to a new address.

        The manifest matches ``registered_devices`` only, so this only fires
        for hardware Home Assistant already knows. The status read is not
        optional. The *device id* is not in the packet, and repointing on the
        packet's MAC alone would skip the check that foreign-panel safety
        rests on (ADR-0003). Any failure is a quiet abort. Home Assistant
        fires this again on the next DHCP event, so a panel still booting
        after a fresh lease is picked up soon after.

        The abort is quiet, not vague: it carries the reason validation
        computed. So a host that answered at the discovered address without
        being a panel does not abort saying nothing answered. Neither string
        reaches anyone. Core awaits a discovery flow and discards its result
        (``helpers/discovery_flow.py``), rendering no card and logging no
        reason. The reason is still the true one, because a string that ships
        is a string that is true.
        """
        status, errors = await self._async_validate(discovery_info.ip)
        if status is None:
            return self.async_abort(reason=errors["base"])
        await self.async_set_unique_id(status.device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        return self.async_abort(reason="not_configured")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point an existing entry at a new address, and never adopt.

        A unit that replaced another is refused, not silently adopted.
        The reconfigure step updates the entry it was opened for or aborts,
        and there is no documented route to adopting a different device.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            status, errors = await self._async_validate(host)
            if status is not None:
                await self.async_set_unique_id(status.device_id)
                self._abort_if_unique_id_mismatch(
                    reason="wrong_panel",
                    description_placeholders=foreign_panel_placeholders(
                        str(entry.unique_id), status.device_id
                    ),
                )
                return self.async_update_reload_and_abort(entry, data={CONF_HOST: host})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(HOST_SCHEMA, entry.data),
            errors=errors,
        )

    async def _async_validate(
        self, host: str
    ) -> tuple[PanelStatus | None, dict[str, str]]:
        """Read a status at ``host``: the panel, or the error to show.

        Must be a ``GET``, because ``HEAD /api/status`` returns 405. It goes
        through the client's real parser, so the *required core* is what
        decides. This client is a separate instance sharing no lock with a
        running entry's, which the device tolerates (§3.2).
        """
        client = HeatitClient(host, session=async_get_clientsession(self.hass))
        try:
            return await client.get_status(), {}
        except HeatitConnectionError:
            return None, {"base": "cannot_connect"}
        except HeatitError:
            return None, {"base": "invalid_response"}

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: ConfigEntry,
    ) -> HeatitWifiPanelOptionsFlow:
        """Return the options flow: the *poll interval*, alone.

        Core passes the entry positionally and ``OptionsFlow.config_entry``
        hands it back, so the argument gets an unused name and is not kept.
        """
        return HeatitWifiPanelOptionsFlow()


class HeatitWifiPanelOptionsFlow(OptionsFlowWithReload):
    """The *poll interval* and nothing else (§4.6).

    Every other user preference is a CONFIG-category entity, and the host is
    connection data. So ``data`` is ``{CONF_HOST}`` and ``options`` is
    ``{poll interval}``. ``OptionsFlowWithReload`` reloads the entry when the
    options change, which is how a new interval is applied. ``update_interval``
    is never retimed in place, and all of the panel's entities go briefly
    unavailable. That is a rare action taken on purpose, and a fair price for
    never shipping a stale-config bug.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the interval, or store it and let the reload apply it."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
