"""Base entity for Gree Local."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FIRMWARE, CONF_MAC, DOMAIN, TEMP_SENSOR_OFFSET
from .coordinator import GreeCoordinator


def decode_temperature(raw: int | None) -> int | None:
    """Convert a raw TemSen/OutEnvTem reading to Celsius."""
    if not raw:
        return None  # units without that sensor report 0
    return raw - TEMP_SENSOR_OFFSET if raw > TEMP_SENSOR_OFFSET else raw


class GreeEntity(CoordinatorEntity[GreeCoordinator]):
    """Common device info and state access."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GreeCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._mac = format_mac(entry.data[CONF_MAC])
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            # The MAC connection lets the DHCP "registered_devices" matcher
            # track this unit's IP even if its OUI is not in the manifest.
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            manufacturer="Gree",
            name=entry.title,
            sw_version=entry.data.get(CONF_FIRMWARE),
        )

    def _value(self, param: str) -> int | None:
        value = self.coordinator.data.get(param)
        return value if isinstance(value, int) else None
