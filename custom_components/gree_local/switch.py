"""Feature toggles (panel light, X-Fan, ...) for Gree Local."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GreeConfigEntry, GreeCoordinator
from .entity import GreeEntity


@dataclass(frozen=True, kw_only=True)
class GreeSwitchDescription(SwitchEntityDescription):
    """Describes a switch backed by a single on/off Gree parameter."""

    param: str


SWITCHES = (
    GreeSwitchDescription(key="light", translation_key="light", param="Lig"),
    GreeSwitchDescription(key="xfan", translation_key="xfan", param="Blo"),
    GreeSwitchDescription(key="health", translation_key="health", param="Health"),
    GreeSwitchDescription(key="fresh_air", translation_key="fresh_air", param="Air"),
    GreeSwitchDescription(key="quiet", translation_key="quiet", param="Quiet"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GreeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    async_add_entities(GreeSwitch(coordinator, description) for description in SWITCHES)


class GreeSwitch(GreeEntity, SwitchEntity):
    """A Gree on/off feature."""

    entity_description: GreeSwitchDescription

    def __init__(self, coordinator: GreeCoordinator, description: GreeSwitchDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._uid}_{description.key}"

    @property
    def is_on(self) -> bool:
        return bool(self._value(self.entity_description.param))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_send({self.entity_description.param: 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_send({self.entity_description.param: 0})
