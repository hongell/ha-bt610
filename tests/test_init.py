from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.bt610.const import CONF_SEEN_EVENT_TYPES, DOMAIN
from tests.conftest import ADDRESS, make_service_info
from tests.test_parser import build_frame


def _entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, unique_id="d5:b7:68:24:b1:1f",
                           data={"address": ADDRESS})


async def _setup(hass: HomeAssistant, entry: MockConfigEntry):
    """Set up the entry with bluetooth APIs patched; return the ad callback."""
    entry.add_to_hass(hass)
    with patch("custom_components.bt610.bluetooth.async_register_callback",
               return_value=MagicMock()) as reg, \
         patch("custom_components.bt610.bluetooth.async_track_unavailable",
               return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return reg.call_args[0][1]  # the advertisement callback


async def test_setup_and_unload(hass: HomeAssistant):
    entry = _entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_event_updates_runtime_and_persists_type(hass: HomeAssistant):
    entry = _entry()
    cb = await _setup(hass, entry)
    cb(make_service_info(payload=build_frame(record_type=26, record_number=10)), None)
    await hass.async_block_till_done()
    rt = entry.runtime_data
    assert 26 in rt.seen_types
    assert rt.last_events[26].record_number == 10
    assert entry.data[CONF_SEEN_EVENT_TYPES] == [26]
    assert rt.counters["parsed"] == 1


async def test_dedup_two_proxies_interleaved(hass: HomeAssistant):
    entry = _entry()
    cb = await _setup(hass, entry)
    a = build_frame(record_type=26, record_number=1)
    b = build_frame(record_type=26, record_number=2)
    for frame in (a, b, a):  # A(proxy1), B(proxy1), A(proxy2)
        cb(make_service_info(payload=frame), None)
    await hass.async_block_till_done()
    rt = entry.runtime_data
    assert rt.counters["parsed"] == 2
    assert rt.counters["deduped"] == 1
    assert rt.last_events[26].record_number == 2


async def test_reset_event_clears_dedup(hass: HomeAssistant):
    entry = _entry()
    cb = await _setup(hass, entry)
    frame = build_frame(record_type=26, record_number=1)
    cb(make_service_info(payload=frame), None)
    cb(make_service_info(payload=build_frame(record_type=37, record_number=99)), None)
    cb(make_service_info(payload=frame), None)  # same rec after reset: accepted
    await hass.async_block_till_done()
    assert entry.runtime_data.counters["parsed"] == 3


async def test_unsupported_protocol_counted(hass: HomeAssistant):
    entry = _entry()
    cb = await _setup(hass, entry)
    cb(make_service_info(payload=build_frame(proto=0x0003)), None)
    await hass.async_block_till_done()
    rt = entry.runtime_data
    assert rt.counters["unsupported_protocol"] == 1
    assert not rt.last_events
