from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.bt610.const import CONF_SEEN_EVENT_TYPES, DOMAIN
from tests.conftest import ADDRESS, make_service_info
from tests.test_parser import build_frame


async def _setup(hass: HomeAssistant, entry_data: dict):
    # title="BT610" -> deterministiset entity_id:t (sensor.bt610_current_1).
    # Jos naming silti eroaa ajetussa HA-versiossa, hae entity_id registrystä
    # unique_id:llä äläkä kovakoodaa.
    entry = MockConfigEntry(domain=DOMAIN, unique_id="d5:b7:68:24:b1:1f",
                            title="BT610",
                            data={"address": ADDRESS, **entry_data})
    entry.add_to_hass(hass)
    with patch("custom_components.bt610.bluetooth.async_register_callback",
               return_value=MagicMock()) as reg, \
         patch("custom_components.bt610.bluetooth.async_track_unavailable",
               return_value=MagicMock()) as unav:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, reg.call_args[0][1], unav.call_args[0][1]


async def test_entity_created_on_first_event(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {})
    assert hass.states.get("sensor.bt610_current_1") is None
    cb(make_service_info(payload=build_frame(record_type=26, value=13.2)), None)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.bt610_current_1")
    assert state is not None
    assert float(state.state) == pytest.approx(13.2, abs=0.01)
    assert state.attributes["unit_of_measurement"] == "A"
    assert state.attributes["device_class"] == "current"


async def test_no_duplicate_entities_on_repeat(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {})
    for n in (1, 2, 3):
        cb(make_service_info(payload=build_frame(record_type=26, record_number=n)), None)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    ids = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id
           and e.unique_id.endswith("-current_1")]
    assert len(ids) == 1


async def test_battery_scaled_to_volts(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {})
    cb(make_service_info(payload=build_frame(record_type=12, value=3600.0)), None)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.bt610_battery_voltage")
    assert float(state.state) == pytest.approx(3.6)


async def test_battery_good_and_bad_share_entity(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {})
    cb(make_service_info(payload=build_frame(record_type=16, value=3200.0)), None)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.bt610_battery_voltage")
    assert float(state.state) == pytest.approx(3.2)
    cb(make_service_info(payload=build_frame(
        record_type=12, record_number=2, value=3600.0)), None)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.bt610_battery_voltage")
    assert float(state.state) == pytest.approx(3.6)
    registry = er.async_get(hass)
    ids = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id
           and e.unique_id.endswith("-battery_voltage")]
    assert len(ids) == 1


async def test_persisted_types_restored_at_setup(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {CONF_SEEN_EVENT_TYPES: [26, 27]})
    assert hass.states.get("sensor.bt610_current_1") is not None
    assert hass.states.get("sensor.bt610_current_2") is not None
    # No events yet -> unknown, but the entity exists
    assert hass.states.get("sensor.bt610_current_1").state in ("unknown", "unavailable")


async def test_unavailable_and_recovery(hass: HomeAssistant):
    entry, cb, unav_cb = await _setup(hass, {})
    frame = build_frame(record_type=26, record_number=1)
    cb(make_service_info(payload=frame), None)
    await hass.async_block_till_done()
    unav_cb(make_service_info(payload=frame))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bt610_current_1").state == "unavailable"
    cb(make_service_info(payload=build_frame(record_type=26, record_number=2)), None)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bt610_current_1").state != "unavailable"


async def test_reload_keeps_entities(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {})
    cb(make_service_info(payload=build_frame(record_type=26, value=1.0)), None)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    with patch("custom_components.bt610.bluetooth.async_register_callback",
               return_value=MagicMock()), \
         patch("custom_components.bt610.bluetooth.async_track_unavailable",
               return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # Persisted seen_event_types recreates the entity without new events
    assert hass.states.get("sensor.bt610_current_1") is not None


async def test_raw_sensor_disabled_by_default(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {})
    cb(make_service_info(payload=build_frame(record_type=22, value=1.5)), None)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    ent = next(e for e in registry.entities.values()
               if e.unique_id.endswith("-voltage_1_raw"))
    assert ent.disabled_by is er.RegistryEntryDisabler.INTEGRATION
