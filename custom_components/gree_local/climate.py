"""Climate entity for Gree Local."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    PRESET_SLEEP,
    SWING_OFF,
    SWING_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GreeConfigEntry
from .entity import GreeEntity, decode_temperature

HVAC_TO_GREE = {
    HVACMode.AUTO: 0,
    HVACMode.COOL: 1,
    HVACMode.DRY: 2,
    HVACMode.FAN_ONLY: 3,
    HVACMode.HEAT: 4,
}
GREE_TO_HVAC = {v: k for k, v in HVAC_TO_GREE.items()}

FAN_MEDIUM_LOW = "medium_low"
FAN_MEDIUM_HIGH = "medium_high"
FAN_TO_GREE = {
    FAN_AUTO: 0,
    FAN_LOW: 1,
    FAN_MEDIUM_LOW: 2,
    FAN_MEDIUM: 3,
    FAN_MEDIUM_HIGH: 4,
    FAN_HIGH: 5,
}
GREE_TO_FAN = {v: k for k, v in FAN_TO_GREE.items()}

# Presets are mutually exclusive flags on the unit.
PRESET_TO_PARAM = {
    PRESET_ECO: "SvSt",
    PRESET_BOOST: "Tur",
    PRESET_SLEEP: "SwhSlp",
    PRESET_AWAY: "StHt",  # 8 C frost protection; only honored in heat mode
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GreeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity."""
    async_add_entities([GreeClimate(entry.runtime_data)])


class GreeClimate(GreeEntity, ClimateEntity):
    """A Gree air conditioner / heat pump."""

    _attr_name = None
    _attr_translation_key = "gree"
    # SetTem is always Celsius on the wire; HA converts for Fahrenheit users.
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_hvac_modes = [HVACMode.OFF, *HVAC_TO_GREE]
    _attr_fan_modes = list(FAN_TO_GREE)
    _attr_swing_modes = [SWING_OFF, SWING_ON]
    _attr_swing_horizontal_modes = [SWING_OFF, SWING_ON]
    _attr_preset_modes = [PRESET_NONE, *PRESET_TO_PARAM]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.SWING_HORIZONTAL_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = self._uid

    # -- state -------------------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode | None:
        if not self._value("Pow"):
            return HVACMode.OFF
        return GREE_TO_HVAC.get(self._value("Mod"))

    @property
    def current_temperature(self) -> float | None:
        return decode_temperature(self._value("TemSen"))

    @property
    def target_temperature(self) -> float | None:
        return self._value("SetTem")

    @property
    def fan_mode(self) -> str | None:
        return GREE_TO_FAN.get(self._value("WdSpd"))

    @property
    def swing_mode(self) -> str:
        # 1 = full swing, 7-11 = partial swing ranges, 2-6 = fixed positions.
        vertical = self._value("SwUpDn") or 0
        return SWING_ON if vertical == 1 or vertical >= 7 else SWING_OFF

    @property
    def swing_horizontal_mode(self) -> str:
        return SWING_ON if self._value("SwingLfRt") == 1 else SWING_OFF

    @property
    def preset_mode(self) -> str:
        for preset, param in PRESET_TO_PARAM.items():
            if self._value(param):
                return preset
        return PRESET_NONE

    # -- commands ----------------------------------------------------------

    @staticmethod
    def _hvac_params(hvac_mode: HVACMode) -> dict[str, int]:
        if hvac_mode == HVACMode.OFF:
            return {"Pow": 0}
        return {"Pow": 1, "Mod": HVAC_TO_GREE[hvac_mode]}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.async_send(self._hvac_params(hvac_mode))

    async def async_turn_on(self) -> None:
        await self.coordinator.async_send({"Pow": 1})

    async def async_turn_off(self) -> None:
        await self.coordinator.async_send({"Pow": 0})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        params: dict[str, int] = {}
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            params.update(self._hvac_params(hvac_mode))
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            params.update(SetTem=round(temperature), TemRec=0)
        if params:
            await self.coordinator.async_send(params)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.async_send({"WdSpd": FAN_TO_GREE[fan_mode]})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self.coordinator.async_send({"SwUpDn": int(swing_mode == SWING_ON)})

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        await self.coordinator.async_send(
            {"SwingLfRt": int(swing_horizontal_mode == SWING_ON)}
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        params = {param: 0 for param in PRESET_TO_PARAM.values()}
        params["SlpMod"] = 0
        if preset_mode != PRESET_NONE:
            params[PRESET_TO_PARAM[preset_mode]] = 1
        if preset_mode == PRESET_SLEEP:
            params["SlpMod"] = 1
        await self.coordinator.async_send(params)
