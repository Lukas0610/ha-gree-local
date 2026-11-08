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
from homeassistant.data_entry_flow import section
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .api import CIPHERS, GreeClient, GreeConnectionError, GreeError
from .const import (
    CONF_CIPHER,
    CONF_FAST_POLL_DURATION,
    CONF_FAST_POLL_INTERVAL,
    CONF_FIRMWARE,
    CONF_KEY,
    CONF_MAC,
    DEFAULT_FAST_POLL_DURATION,
    DEFAULT_FAST_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_FAST_POLL_DURATION,
    MAX_FAST_POLL_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_FAST_POLL_INTERVAL,
    MIN_SCAN_INTERVAL,
)

HOST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
        ),
    }
)

SECTION_CONNECTION = "connection"

RECONFIGURE_SCHEMA = HOST_SCHEMA.extend(
    {
        vol.Required(SECTION_CONNECTION): section(
            vol.Schema(
                {
                    vol.Optional(CONF_MAC): TextSelector(),
                    vol.Optional(CONF_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_CIPHER): SelectSelector(
                        SelectSelectorConfig(
                            options=list(CIPHERS),
                            translation_key=CONF_CIPHER,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            {"collapsed": True},
        ),
    }
)


def _number(minimum: int, maximum: int, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): _number(
            MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, UnitOfTime.MILLISECONDS
        ),
        vol.Required(CONF_FAST_POLL_DURATION, default=DEFAULT_FAST_POLL_DURATION): _number(
            0, MAX_FAST_POLL_DURATION, UnitOfTime.SECONDS
        ),
        vol.Required(CONF_FAST_POLL_INTERVAL, default=DEFAULT_FAST_POLL_INTERVAL): _number(
            MIN_FAST_POLL_INTERVAL, MAX_FAST_POLL_INTERVAL, UnitOfTime.MILLISECONDS
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


class InvalidKey(GreeError):
    """The unit is reachable but ignores packets encrypted with the given key."""


class WrongDevice(GreeError):
    """The address belongs to a different unit than the one being reconfigured."""


def _normalize_mac(value: str) -> str | None:
    """Return a MAC in Gree's wire format (12 lowercase hex digits), "" or None if invalid."""
    mac = "".join(ch for ch in value.lower() if ch not in ":-. ")
    if mac and (len(mac) != 12 or any(ch not in "0123456789abcdef" for ch in mac)):
        return None
    return mac


async def _verify(
    host: str, port: int, mac: str, key: str, cipher: str, expected_uid: str | None
) -> dict[str, Any]:
    """Check connection details and return the entry data updates.

    An empty MAC means "use the scanned one", an empty key means "bind for a new one".
    If expected_uid is set, the scanned unit must have that (formatted) MAC.
    """
    client = GreeClient(host, port)
    info = await client.scan()
    assert client.mac is not None
    if expected_uid is not None and format_mac(client.mac) != expected_uid:
        raise WrongDevice
    client.mac = mac or client.mac
    if key:
        client.cipher = CIPHERS[cipher](key.encode())
        try:
            await client.status(["Pow"])
        except GreeConnectionError as err:
            # Scan just worked, so silence here means the key/cipher/MAC is wrong.
            raise InvalidKey from err
    else:
        await client.bind()
    assert client.cipher is not None
    data = {
        CONF_HOST: host,
        CONF_PORT: port,
        CONF_MAC: client.mac,
        CONF_KEY: client.cipher.key.decode(),
        CONF_CIPHER: client.cipher.name,
        CONF_FIRMWARE: info.get("ver"),
    }
    return data


class GreeLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Gree Local."""

    VERSION = 1
    # 1.2: CONF_NAME stored in entry data. 1.3: polling interval option in ms.
    MINOR_VERSION = 3

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
        """View/change address, MAC, key and cipher of an existing unit."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            connection = user_input.get(SECTION_CONNECTION, {})
            mac = _normalize_mac(connection.get(CONF_MAC, ""))
            key = connection.get(CONF_KEY, "").strip()
            if mac is None:
                errors["base"] = "invalid_mac"
            elif key and len(key.encode()) != 16:
                errors["base"] = "invalid_key_format"
            else:
                # Guard against pointing the entry at another unit by accident,
                # unless the user deliberately entered a different MAC.
                mac_edited = bool(mac) and format_mac(mac) != entry.unique_id
                try:
                    data = await _verify(
                        user_input[CONF_HOST].strip(),
                        int(user_input.get(CONF_PORT, DEFAULT_PORT)),
                        mac,
                        key,
                        connection[CONF_CIPHER],
                        expected_uid=None if mac_edited else entry.unique_id,
                    )
                except WrongDevice:
                    return self.async_abort(reason="wrong_device")
                except InvalidKey:
                    errors["base"] = "invalid_key"
                except GreeConnectionError:
                    errors["base"] = "cannot_connect"
                except GreeError:
                    errors["base"] = "cannot_bind"
                else:
                    return self.async_update_reload_and_abort(entry, data_updates=data)

        suggested = user_input or {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
            SECTION_CONNECTION: {
                CONF_MAC: entry.data[CONF_MAC],
                CONF_KEY: entry.data.get(CONF_KEY, ""),
                CONF_CIPHER: entry.data.get(CONF_CIPHER, "ecb"),
            },
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(RECONFIGURE_SCHEMA, suggested),
            errors=errors,
        )


class GreeLocalOptionsFlow(OptionsFlow):
    """Polling interval and fast polling after commands."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # NumberSelector yields floats; store ints.
            return self.async_create_entry(
                data={
                    key: int(user_input[key])
                    for key in (
                        CONF_SCAN_INTERVAL,
                        CONF_FAST_POLL_DURATION,
                        CONF_FAST_POLL_INTERVAL,
                    )
                }
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
