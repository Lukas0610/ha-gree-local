"""Polling coordinator for a Gree unit."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GreeClient, GreeError
from .const import CONF_CIPHER, CONF_KEY, DEFAULT_SCAN_INTERVAL, DOMAIN, STATUS_COLUMNS

_LOGGER = logging.getLogger(__name__)

type GreeConfigEntry = ConfigEntry[GreeCoordinator]


class GreeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll one unit and push commands to it."""

    config_entry: GreeConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: GreeConfigEntry, client: GreeClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.status(STATUS_COLUMNS)
        except GreeError as err:
            _LOGGER.debug("Status failed (%s), rebinding %s", err, self.client.host)

        # A stale key (unit reset or re-paired in the app) makes the unit drop
        # our packets, so one rebind attempt recovers without user action.
        try:
            cipher = await self.client.bind()
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_KEY: cipher.key.decode(),
                    CONF_CIPHER: cipher.name,
                },
            )
            return await self.client.status(STATUS_COLUMNS)
        except GreeError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"host": self.client.host, "error": str(err)},
            ) from err

    async def async_send(self, params: dict[str, int]) -> None:
        """Send a command and optimistically apply it to the cached state."""
        try:
            await self.client.set(params)
        except GreeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"host": self.client.host, "error": str(err)},
            ) from err
        self.async_set_updated_data({**self.data, **params})
