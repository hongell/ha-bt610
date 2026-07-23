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
    # A(proxy1), B(proxy1), A(proxy2) - same frame A relayed by a second proxy
    cb(make_service_info(payload=a, source="AA:BB:CC:DD:EE:FF"), None)
    cb(make_service_info(payload=b, source="AA:BB:CC:DD:EE:FF"), None)
    cb(make_service_info(payload=a, source="11:22:33:44:55:66"), None)
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


async def test_dedup_expires_after_ttl(hass: HomeAssistant):
    entry = _entry()
    cb = await _setup(hass, entry)
    frame = build_frame(record_type=26, record_number=1)
    start = 1_000_000.0

    with patch("custom_components.bt610.time.monotonic", return_value=start):
        cb(make_service_info(payload=frame), None)
        await hass.async_block_till_done()

    # Advance past the 300s TTL: the stale dedup entry is evicted before
    # the lookup, so the same frame is accepted (parsed) again, not deduped.
    with patch("custom_components.bt610.time.monotonic", return_value=start + 301.0):
        cb(make_service_info(payload=frame), None)
        await hass.async_block_till_done()

    rt = entry.runtime_data
    assert rt.counters["parsed"] == 2
    assert rt.counters["deduped"] == 0


async def test_dedup_max_size_eviction(hass: HomeAssistant):
    entry = _entry()
    cb = await _setup(hass, entry)
    with patch("custom_components.bt610.time.monotonic", return_value=1000.0):
        for record_number in range(1, 129):  # fill dedup cache to DEDUP_MAX (128)
            cb(make_service_info(
                payload=build_frame(record_type=26, record_number=record_number)), None)
        await hass.async_block_till_done()

        # 129th distinct frame evicts the oldest entry (record_number=1).
        cb(make_service_info(
            payload=build_frame(record_type=26, record_number=129)), None)
        await hass.async_block_till_done()

        # record_number=1 was evicted, so it is accepted again, not deduped.
        cb(make_service_info(
            payload=build_frame(record_type=26, record_number=1)), None)
        await hass.async_block_till_done()

    rt = entry.runtime_data
    assert rt.counters["parsed"] == 130
    assert rt.counters["deduped"] == 0


async def test_remove_entry_rediscovers(hass: HomeAssistant):
    entry = _entry()
    await _setup(hass, entry)
    with patch("custom_components.bt610.bluetooth.async_register_callback",
               return_value=MagicMock()), \
         patch("custom_components.bt610.bluetooth.async_track_unavailable",
               return_value=MagicMock()), \
         patch("custom_components.bt610.bluetooth.async_rediscover_address") as rediscover:
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
    rediscover.assert_called_once_with(hass, ADDRESS)
