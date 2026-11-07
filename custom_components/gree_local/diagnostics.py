"""Diagnostics download for Gree Local."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_KEY, CONF_MAC
from .coordinator import GreeConfigEntry

TO_REDACT = {CONF_HOST, CONF_KEY, CONF_MAC, "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GreeConfigEntry
) -> dict[str, Any]:
    """Return redacted entry data plus the last raw status from the unit."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "cipher": coordinator.client.cipher.name if coordinator.client.cipher else None,
        "last_update_success": coordinator.last_update_success,
        "status": coordinator.data,
    }
