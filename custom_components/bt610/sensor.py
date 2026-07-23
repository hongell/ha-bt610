"""Dynamically created sensors for BT610 advertisement events."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Bt610ConfigEntry, Bt610Runtime, signal_new_type, signal_update
from .const import (
    DOMAIN,
    EVENT_BATTERY_BAD,
    EVENT_BATTERY_GOOD,
    EVENT_CURRENT_1,
    EVENT_CURRENT_2,
    EVENT_CURRENT_3,
    EVENT_CURRENT_4,
    EVENT_PRESSURE_1,
    EVENT_PRESSURE_2,
    EVENT_TEMPERATURE,
    EVENT_TEMPERATURE_1,
    EVENT_TEMPERATURE_2,
    EVENT_TEMPERATURE_3,
    EVENT_TEMPERATURE_4,
    EVENT_ULTRASONIC_1,
    EVENT_VOLTAGE_1,
    EVENT_VOLTAGE_2,
    EVENT_VOLTAGE_3,
    EVENT_VOLTAGE_4,
)


@dataclass(frozen=True, kw_only=True)
class Bt610SensorDescription(SensorEntityDescription):
    multiplier: float = 1.0


def _current(n: int) -> Bt610SensorDescription:
    return Bt610SensorDescription(
        key=f"current_{n}", translation_key=f"current_{n}",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2)


def _temperature(key: str) -> Bt610SensorDescription:
    return Bt610SensorDescription(
        key=key, translation_key=key,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1)


def _raw(key: str) -> Bt610SensorDescription:
    # Scaling unverified: raw float, no classes, disabled by default.
    return Bt610SensorDescription(
        key=key, translation_key=key, entity_registry_enabled_default=False)


BATTERY = Bt610SensorDescription(
    key="battery_voltage", translation_key="battery_voltage",
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    suggested_display_precision=3, multiplier=0.001)

RSSI = Bt610SensorDescription(
    key="rssi", translation_key="rssi",
    native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    device_class=SensorDeviceClass.SIGNAL_STRENGTH,
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False)

DESCRIPTIONS: dict[int, Bt610SensorDescription] = {
    EVENT_TEMPERATURE: _temperature("temperature"),
    EVENT_TEMPERATURE_1: _temperature("temperature_1"),
    EVENT_TEMPERATURE_2: _temperature("temperature_2"),
    EVENT_TEMPERATURE_3: _temperature("temperature_3"),
    EVENT_TEMPERATURE_4: _temperature("temperature_4"),
    EVENT_CURRENT_1: _current(1),
    EVENT_CURRENT_2: _current(2),
    EVENT_CURRENT_3: _current(3),
    EVENT_CURRENT_4: _current(4),
    EVENT_BATTERY_GOOD: BATTERY,
    EVENT_BATTERY_BAD: BATTERY,
    EVENT_VOLTAGE_1: _raw("voltage_1_raw"),
    EVENT_VOLTAGE_2: _raw("voltage_2_raw"),
    EVENT_VOLTAGE_3: _raw("voltage_3_raw"),
    EVENT_VOLTAGE_4: _raw("voltage_4_raw"),
    EVENT_ULTRASONIC_1: _raw("ultrasonic_raw"),
    EVENT_PRESSURE_1: _raw("pressure_1_raw"),
    EVENT_PRESSURE_2: _raw("pressure_2_raw"),
}
# record_type -> description; several types may share one key (battery).
KEY_TO_TYPES: dict[str, list[int]] = {}
for _t, _d in DESCRIPTIONS.items():
    KEY_TO_TYPES.setdefault(_d.key, []).append(_t)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Bt610ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    created: set[str] = set()

    def _entities_for(record_types: set[int]) -> list[Bt610Sensor]:
        new: list[Bt610Sensor] = []
        for rt in sorted(record_types):
            desc = DESCRIPTIONS.get(rt)
            if desc is None or desc.key in created:
                continue
            created.add(desc.key)
            new.append(Bt610Sensor(entry, runtime, desc))
        return new

    entities = _entities_for(runtime.seen_types)
    entities.append(Bt610RssiSensor(entry, runtime, RSSI))
    created.add(RSSI.key)
    async_add_entities(entities)

    @callback
    def _async_new_type(record_type: int) -> None:
        async_add_entities(_entities_for({record_type}))

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_new_type(entry), _async_new_type))


class Bt610Sensor(RestoreSensor):
    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: Bt610SensorDescription

    def __init__(self, entry: Bt610ConfigEntry, runtime: Bt610Runtime,
                 description: Bt610SensorDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._runtime = runtime
        mac = format_mac(runtime.address)
        self._attr_unique_id = f"{mac}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_BLUETOOTH, runtime.address)},
            manufacturer="Laird Connectivity (Ezurio)",
            model="Sentrius BT610",
            name=self._entry.title,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (self.native_value is None
                and (last := await self.async_get_last_sensor_data()) is not None):
            self._attr_native_value = last.native_value
        self.async_on_remove(async_dispatcher_connect(
            self.hass, signal_update(self._entry), self._async_updated))
        self._refresh()

    @callback
    def _async_updated(self) -> None:
        self._refresh()
        self.async_write_ha_state()

    def _refresh(self) -> None:
        events = [self._runtime.last_events[t]
                  for t in KEY_TO_TYPES[self.entity_description.key]
                  if t in self._runtime.last_events]
        if events:
            # Reception order, not epoch: epochs can collide (battery good/bad)
            # or jump backwards after a device clock reset.
            latest = max(events,
                         key=lambda e: self._runtime.event_order.get(e.record_type, 0))
            self._attr_native_value = round(
                latest.value * self.entity_description.multiplier, 6)

    @property
    def available(self) -> bool:
        return self._runtime.available


class Bt610RssiSensor(Bt610Sensor):
    def _refresh(self) -> None:
        if self._runtime.last_rssi is not None:
            self._attr_native_value = self._runtime.last_rssi

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self._runtime.last_source:
            return {"source": self._runtime.last_source}
        return None
