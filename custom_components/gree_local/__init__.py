"""Gree Local: control Gree HVAC units by IP, without UDP broadcast."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant

from .api import GreeClient
from .const import CONF_CIPHER, CONF_KEY, CONF_MAC, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL
from .coordinator import GreeConfigEntry, GreeCoordinator

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: GreeConfigEntry) -> bool:
    """Set up a Gree unit from a config entry."""
    client = GreeClient(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        mac=entry.data[CONF_MAC],
        key=entry.data.get(CONF_KEY),
        cipher=entry.data.get(CONF_CIPHER, "ecb"),
    )
    coordinator = GreeCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: GreeConfigEntry) -> None:
    """Apply a new polling interval from the options flow."""
    entry.runtime_data.update_interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )


async def async_unload_entry(hass: HomeAssistant, entry: GreeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
