"""Gree Local: control Gree HVAC units by IP, without UDP broadcast."""

from __future__ import annotations

import logging

from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .api import GreeClient, GreeError
from .const import (
    CONF_BOARD_VERSION,
    CONF_CIPHER,
    CONF_FIRMWARE,
    CONF_HID,
    CONF_KEY,
    CONF_MAC,
    CONF_MID,
    DEFAULT_PORT,
    MIN_SCAN_INTERVAL,
)
from .coordinator import GreeConfigEntry, GreeCoordinator

_LOGGER = logging.getLogger(__name__)

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
    # Before the platforms: entities build their device info from entry data.
    await _async_refresh_firmware(hass, entry, client)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_polling()
    entry.async_on_unload(coordinator.async_stop_polling)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(
        hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            _async_device_renamed_listener(hass, entry),
            event_filter=_is_device_rename,
        )
    )
    return True


async def _async_refresh_firmware(
    hass: HomeAssistant, entry: GreeConfigEntry, client: GreeClient
) -> None:
    """Store the unit's current firmware details (they change with OTA updates)."""
    try:
        fw = await client.firmware()
    except GreeError as err:
        _LOGGER.debug("Keeping stored firmware details for %s: %s", client.host, err)
        return
    updates = {
        conf: fw.get(field)
        for field, conf in (
            ("ver", CONF_FIRMWARE),
            ("mid", CONF_MID),
            ("hid", CONF_HID),
            ("board_version", CONF_BOARD_VERSION),
        )
    }
    if any(entry.data.get(conf) != value for conf, value in updates.items()):
        hass.config_entries.async_update_entry(entry, data={**entry.data, **updates})


async def async_migrate_entry(hass: HomeAssistant, entry: GreeConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version > 1:
        return False  # downgrade from a future major version
    if entry.minor_version < 2:
        # 1.2: the device name is stored separately so the title can follow renames.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_NAME: entry.title}, minor_version=2
        )
    if entry.minor_version < 3:
        # 1.3: the polling interval is stored in milliseconds. Old values were
        # seconds (1-300); anything below the new 500 ms minimum must be seconds.
        options = dict(entry.options)
        interval = options.get(CONF_SCAN_INTERVAL)
        if interval is not None and interval < MIN_SCAN_INTERVAL:
            options[CONF_SCAN_INTERVAL] = max(int(interval * 1000), MIN_SCAN_INTERVAL)
        hass.config_entries.async_update_entry(entry, options=options, minor_version=3)
    _LOGGER.debug("Migrated %s to version %s.%s", entry.title, entry.version, entry.minor_version)
    return True


@callback
def _is_device_rename(event_data: dr.EventDeviceRegistryUpdatedData) -> bool:
    return event_data["action"] == "update" and "name_by_user" in event_data["changes"]


def _async_device_renamed_listener(hass: HomeAssistant, entry: GreeConfigEntry):
    """Keep the config entry title in sync with the device's user-given name."""

    @callback
    def _async_device_renamed(event: Event[dr.EventDeviceRegistryUpdatedData]) -> None:
        device = dr.async_get(hass).async_get(event.data["device_id"])
        if device is None or entry.entry_id not in device.config_entries:
            return
        # Clearing the custom name reverts the title to the original device name.
        title = device.name_by_user or entry.data[CONF_NAME]
        if title != entry.title:
            hass.config_entries.async_update_entry(entry, title=title)

    return _async_device_renamed


async def _async_options_updated(hass: HomeAssistant, entry: GreeConfigEntry) -> None:
    """Apply new polling options. Also fires on key/title changes, so never reload."""
    coordinator = entry.runtime_data
    if coordinator.apply_options():
        coordinator.async_reschedule()


async def async_unload_entry(hass: HomeAssistant, entry: GreeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
