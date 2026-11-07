"""Temperature sensors for Gree Local (history graphs, statistics)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GreeConfigEntry, GreeCoordinator
from .entity import GreeEntity, decode_temperature


@dataclass(frozen=True, kw_only=True)
class GreeSensorDescription(SensorEntityDescription):
    """Describes a temperature reading from a Gree parameter."""

    param: str


SENSORS = (
    # No translation_key: HA names it "Temperature" from the device class.
    GreeSensorDescription(
        key="room_temperature",
        param="TemSen",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    # Only some units report this; enable it from the device page if yours does.
    GreeSensorDescription(
        key="outdoor_temperature",
        translation_key="outdoor_temperature",
        param="OutEnvTem",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GreeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(GreeSensor(coordinator, description) for description in SENSORS)


class GreeSensor(GreeEntity, SensorEntity):
    """A Gree temperature sensor."""

    entity_description: GreeSensorDescription

    def __init__(self, coordinator: GreeCoordinator, description: GreeSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._mac}_{description.key}"

    @property
    def native_value(self) -> int | None:
        return decode_temperature(self._value(self.entity_description.param))
