"""Sensor platform for Sorel Connect."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SorelCoordinator

_DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, "sorel_connect")},
    name="Sorel Connect",
    manufacturer=MANUFACTURER,
    model=MODEL,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities from the first coordinator poll."""
    coordinator: SorelCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    entities.extend(
        SorelSensorEntity(coordinator, sid) for sid in coordinator.data.sensors
    )
    entities.extend(
        SorelRelayEntity(coordinator, rid) for rid in coordinator.data.relays
    )
    entities.append(SorelLogEntity(coordinator))
    async_add_entities(entities)


class SorelSensorEntity(CoordinatorEntity[SorelCoordinator], SensorEntity):
    """A temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_info = _DEVICE_INFO

    def __init__(self, coordinator: SorelCoordinator, sensor_id: int) -> None:
        super().__init__(coordinator)
        self._id = sensor_id
        self._attr_name = f"Sensor {sensor_id}"
        self._attr_unique_id = f"sorel_connect_sensor_{sensor_id}"

    @property
    def native_value(self) -> float | None:
        reading = self.coordinator.data.sensors.get(self._id)
        return reading.value if reading else None


class SorelRelayEntity(CoordinatorEntity[SorelCoordinator], SensorEntity):
    """A relay reported as a percentage."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_info = _DEVICE_INFO

    def __init__(self, coordinator: SorelCoordinator, relay_id: int) -> None:
        super().__init__(coordinator)
        self._id = relay_id
        self._attr_name = f"Relay {relay_id}"
        self._attr_unique_id = f"sorel_connect_relay_{relay_id}"

    @property
    def native_value(self) -> float | None:
        reading = self.coordinator.data.relays.get(self._id)
        return reading.value if reading else None


class SorelLogEntity(CoordinatorEntity[SorelCoordinator], SensorEntity):
    """The controller log; state is the newest entry."""

    _attr_name = "Log"
    _attr_unique_id = "sorel_connect_log"
    _attr_device_info = _DEVICE_INFO

    def __init__(self, coordinator: SorelCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def native_value(self) -> str | None:
        logs = self.coordinator.data.logs
        return logs[0] if logs else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            f"log_{i}": entry
            for i, entry in enumerate(self.coordinator.data.logs, start=1)
        }
