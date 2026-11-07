"""Base entity for Gree Local."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BOARD_VERSION,
    CONF_FIRMWARE,
    CONF_HID,
    CONF_MAC,
    CONF_MID,
    DOMAIN,
    TEMP_SENSOR_OFFSET,
)
from .coordinator import GreeCoordinator


def decode_temperature(raw: int | None) -> int | None:
    """Convert a raw TemSen/OutEnvTem reading to Celsius."""
    if not raw:
        return None  # units without that sensor report 0
    return raw - TEMP_SENSOR_OFFSET if raw > TEMP_SENSOR_OFFSET else raw


def firmware_version(data: Mapping[str, Any]) -> str | None:
    """Device page "Firmware" line, e.g. "V1.21 (Board 1.0.4, MID 10001, HID 3620...V1.0.4.bin)"."""
    details = [
        f"{label} {data[conf]}"
        for label, conf in (
            ("Board", CONF_BOARD_VERSION),
            ("MID", CONF_MID),
            ("HID", CONF_HID),
        )
        if data.get(conf)
    ]
    version = data.get(CONF_FIRMWARE)
    if not details:
        return version
    return f"{version or '?'} ({', '.join(details)})"


class GreeEntity(CoordinatorEntity[GreeCoordinator]):
    """Common device info and state access."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GreeCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        # Identity comes from the entry's unique_id (the MAC at setup time), so
        # editing the MAC in the reconfigure flow doesn't orphan the device.
        assert entry.unique_id is not None
        self._uid = entry.unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._uid)},
            # The MAC connection lets the DHCP "registered_devices" matcher
            # track this unit's IP even if its OUI is not in the manifest.
            connections={(CONNECTION_NETWORK_MAC, format_mac(entry.data[CONF_MAC]))},
            manufacturer="Gree",
            name=entry.data[CONF_NAME],
            sw_version=firmware_version(entry.data),
        )

    def _value(self, param: str) -> int | None:
        value = self.coordinator.data.get(param)
        return value if isinstance(value, int) else None
