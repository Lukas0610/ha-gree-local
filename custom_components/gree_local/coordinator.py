"""Polling coordinator for a Gree unit."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GreeClient, GreeError
from .const import (
    CONF_CIPHER,
    CONF_FAST_POLL_DURATION,
    CONF_FAST_POLL_INTERVAL,
    CONF_KEY,
    DEFAULT_FAST_POLL_DURATION,
    DEFAULT_FAST_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STATUS_COLUMNS,
)

_LOGGER = logging.getLogger(__name__)

type GreeConfigEntry = ConfigEntry[GreeCoordinator]


class GreeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll one unit and push commands to it.

    Polling is scheduled here instead of via update_interval: the base class
    rounds the next refresh time down to whole seconds, which breaks
    sub-second intervals (refreshes would run back-to-back).
    """

    config_entry: GreeConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: GreeConfigEntry, client: GreeClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=None,
        )
        self.client = client
        self._interval = 0.0  # seconds
        self._fast_interval = 0.0  # seconds
        self._fast_duration = 0.0  # seconds
        self._fast_until = 0.0  # loop time
        self._unsub_poll: CALLBACK_TYPE | None = None
        self._polling = False
        self._running = False
        self.apply_options()

    @callback
    def apply_options(self) -> bool:
        """Read the polling options; return True if they changed."""
        options = self.config_entry.options
        new = (
            options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL) / 1000,
            options.get(CONF_FAST_POLL_INTERVAL, DEFAULT_FAST_POLL_INTERVAL) / 1000,
            float(options.get(CONF_FAST_POLL_DURATION, DEFAULT_FAST_POLL_DURATION)),
        )
        old = (self._interval, self._fast_interval, self._fast_duration)
        self._interval, self._fast_interval, self._fast_duration = new
        return new != old

    @property
    def current_interval(self) -> float:
        """Seconds until the next poll: fast right after a command, else normal."""
        if self.hass.loop.time() < self._fast_until:
            return min(self._fast_interval, self._interval)
        return self._interval

    @callback
    def async_start_polling(self) -> None:
        """Start the poll timer (after the first refresh)."""
        self._running = True
        self._async_schedule_poll()

    @callback
    def async_stop_polling(self) -> None:
        """Stop the poll timer."""
        self._running = False
        self._async_cancel_poll()

    @callback
    def async_reschedule(self) -> None:
        """Restart the wait for the next poll with the current interval."""
        if not self._polling:  # a running poll schedules the next one when done
            self._async_schedule_poll()

    @callback
    def _async_cancel_poll(self) -> None:
        if self._unsub_poll is not None:
            self._unsub_poll()
            self._unsub_poll = None

    @callback
    def _async_schedule_poll(self) -> None:
        self._async_cancel_poll()
        if not self._running or self.config_entry.pref_disable_polling:
            return
        self._unsub_poll = async_call_later(
            self.hass, self.current_interval, self._async_handle_poll_timer
        )

    @callback
    def _async_handle_poll_timer(self, _now: datetime) -> None:
        self._unsub_poll = None
        if self.hass.is_stopping:
            return
        self._polling = True
        self.config_entry.async_create_background_task(
            self.hass, self._async_poll(), name=f"{self.name} poll"
        )

    async def _async_poll(self) -> None:
        try:
            await self.async_refresh()
        finally:
            self._polling = False
            self._async_schedule_poll()

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
        """Send a command, optimistically apply it, and enter the fast-poll window."""
        try:
            await self.client.set(params)
        except GreeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"host": self.client.host, "error": str(err)},
            ) from err
        self.async_set_updated_data({**self.data, **params})
        if self._fast_duration > 0:
            self._fast_until = self.hass.loop.time() + self._fast_duration
            self.async_reschedule()
