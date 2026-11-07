"""Config flow for Gree Local: manual IP, DHCP discovery and reconfigure."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    UnitOfTime,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .api import GreeClient, GreeConnectionError, GreeError
from .const import (
    CONF_CIPHER,
    CONF_FIRMWARE,
    CONF_KEY,
    CONF_MAC,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

HOST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=10,
                max=300,
                step=5,
                unit_of_measurement=UnitOfTime.SECONDS,
                mode=NumberSelectorMode.SLIDER,
            )
        ),
    }
)


async def _probe(host: str, port: int) -> tuple[dict[str, Any], str]:
    """Scan and bind the unit at host; return (entry data, title)."""
    client = GreeClient(host, port)
    info = await client.scan()
    cipher = await client.bind()
    assert client.mac is not None
    data = {
        CONF_HOST: host,
        CONF_PORT: port,
        CONF_MAC: client.mac,
        CONF_KEY: cipher.key.decode(),
        CONF_CIPHER: cipher.name,
        CONF_FIRMWARE: info.get("ver"),
    }
    title = info.get("name") or f"Gree {client.mac[-6:]}"
    # Original device name; the entry title follows user renames of the device.
    data[CONF_NAME] = title
    return data, title


class GreeLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Gree Local."""

    VERSION = 1
    MINOR_VERSION = 2  # 1.2: CONF_NAME stored in entry data

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GreeLocalOptionsFlow:
        """Return the options flow."""
        return GreeLocalOptionsFlow()

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = ""

    async def _async_try_probe(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> bool:
        try:
            # NumberSelector yields floats; the port must be an int.
            self._data, self._title = await _probe(
                user_input[CONF_HOST].strip(), int(user_input.get(CONF_PORT, DEFAULT_PORT))
            )
        except GreeConnectionError:
            errors["base"] = "cannot_connect"
        except GreeError:
            errors["base"] = "cannot_bind"
        else:
            return True
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a unit by IP address."""
        errors: dict[str, str] = {}
        if user_input is not None and await self._async_try_probe(user_input, errors):
            await self.async_set_unique_id(format_mac(self._data[CONF_MAC]))
            self._abort_if_unique_id_configured(
                updates={CONF_HOST: self._data[CONF_HOST], CONF_PORT: self._data[CONF_PORT]}
            )
            return self.async_create_entry(title=self._title, data=self._data)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(HOST_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """A Gree MAC got an IP: offer setup, or update a known unit's IP."""
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        # Known unit with a new IP: store it and reload - no user action needed.
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})

        try:
            self._data, self._title = await _probe(discovery_info.ip, DEFAULT_PORT)
        except GreeError:
            return self.async_abort(reason="not_gree")

        # The protocol MAC is canonical; re-check in case it differs from DHCP's.
        await self.async_set_unique_id(
            format_mac(self._data[CONF_MAC]), raise_on_progress=False
        )
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        self.context["title_placeholders"] = {"name": self._title}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered unit."""
        if user_input is not None:
            return self.async_create_entry(title=self._title, data=self._data)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"name": self._title, "host": self._data[CONF_HOST]},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the IP/port of an existing unit."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None and await self._async_try_probe(user_input, errors):
            await self.async_set_unique_id(format_mac(self._data[CONF_MAC]))
            self._abort_if_unique_id_mismatch(reason="wrong_device")
            return self.async_update_reload_and_abort(entry, data_updates=self._data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                HOST_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


class GreeLocalOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
