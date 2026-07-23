"""Laird BT610 BLE advertisement integration."""
from __future__ import annotations

import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_SEEN_EVENT_TYPES,
    DOMAIN,
    LAIRD_MANUFACTURER_ID,
    RESET_EVENT_TYPES,
    SENSOR_EVENT_TYPES,
)
from .parser import Bt610Event, ParseFailure, parse

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
DEDUP_TTL = 300.0  # seconds; > a few advertising cycles at any sane interval
DEDUP_MAX = 128


@dataclass
class Bt610Runtime:
    address: str
    available: bool = True
    seen_types: set[int] = field(default_factory=set)
    last_events: dict[int, Bt610Event] = field(default_factory=dict)
    last_rssi: int | None = None
    last_source: str | None = None
    counters: dict[str, int] = field(default_factory=lambda: {
        "parsed": 0, "deduped": 0, "unsupported_protocol": 0,
        "malformed": 0, "unknown_type": 0})
    last_frames: deque[str] = field(default_factory=lambda: deque(maxlen=10))
    dedup: OrderedDict[tuple[int, int, int], float] = field(
        default_factory=OrderedDict)
    event_seq: int = 0                     # reception-order tiebreaker
    event_order: dict[int, int] = field(default_factory=dict)  # record_type -> seq
    last_error_log: float = 0.0            # rate-limit for exception logging


type Bt610ConfigEntry = ConfigEntry[Bt610Runtime]


def signal_new_type(entry: ConfigEntry) -> str:
    return f"{DOMAIN}_{entry.entry_id}_new"


def signal_update(entry: ConfigEntry) -> str:
    return f"{DOMAIN}_{entry.entry_id}_upd"


async def async_setup_entry(hass: HomeAssistant, entry: Bt610ConfigEntry) -> bool:
    runtime = Bt610Runtime(address=entry.data[CONF_ADDRESS])
    runtime.seen_types = set(entry.data.get(CONF_SEEN_EVENT_TYPES, []))
    entry.runtime_data = runtime

    # Sensor platform first so async_add_entities is ready before callbacks fire.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _async_on_advertisement(
        service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        try:
            _handle_advertisement(hass, entry, runtime, service_info)
        except Exception:  # noqa: BLE001 - boundary guard, must never raise into BT stack
            now = time.monotonic()
            if now - runtime.last_error_log > 300:
                runtime.last_error_log = now
                _LOGGER.exception("Unexpected error handling BT610 advertisement")

    @callback
    def _async_unavailable(service_info: BluetoothServiceInfoBleak) -> None:
        runtime.available = False
        async_dispatcher_send(hass, signal_update(entry))

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass, _async_on_advertisement,
            BluetoothCallbackMatcher(address=runtime.address, connectable=False),
            BluetoothScanningMode.PASSIVE,
        )
    )
    entry.async_on_unload(
        bluetooth.async_track_unavailable(
            hass, _async_unavailable, runtime.address, connectable=False)
    )
    return True


@callback
def _handle_advertisement(
    hass: HomeAssistant,
    entry: Bt610ConfigEntry,
    runtime: Bt610Runtime,
    service_info: BluetoothServiceInfoBleak,
) -> None:
    payload = service_info.manufacturer_data.get(LAIRD_MANUFACTURER_ID)
    if payload is None:
        return
    runtime.available = True
    runtime.last_rssi = service_info.rssi
    runtime.last_source = service_info.source
    runtime.last_frames.append(payload.hex())

    result = parse(payload)
    if isinstance(result, ParseFailure):
        key = ("unsupported_protocol"
               if result.reason == "unsupported_protocol" else "malformed")
        runtime.counters[key] += 1
        async_dispatcher_send(hass, signal_update(entry))  # rssi/availability
        return

    if result.embedded_mac != runtime.address:
        _LOGGER.debug("Embedded MAC %s differs from advertiser %s",
                      result.embedded_mac, runtime.address)

    if result.record_type in RESET_EVENT_TYPES:
        runtime.dedup.clear()

    now = time.monotonic()
    key = (result.record_type, result.record_number, result.epoch)
    while runtime.dedup and now - next(iter(runtime.dedup.values())) >= DEDUP_TTL:
        runtime.dedup.popitem(last=False)
    if key in runtime.dedup:
        runtime.counters["deduped"] += 1
        async_dispatcher_send(hass, signal_update(entry))  # rssi/availability recovery
        return
    if len(runtime.dedup) >= DEDUP_MAX:
        runtime.dedup.popitem(last=False)
    runtime.dedup[key] = now
    runtime.counters["parsed"] += 1

    if result.record_type not in SENSOR_EVENT_TYPES:
        runtime.counters["unknown_type"] += 1
        _LOGGER.debug("Unhandled BT610 record type %s: %s",
                      result.record_type, payload.hex())
        async_dispatcher_send(hass, signal_update(entry))
        return

    runtime.event_seq += 1
    runtime.event_order[result.record_type] = runtime.event_seq
    runtime.last_events[result.record_type] = result
    if result.record_type not in runtime.seen_types:
        runtime.seen_types.add(result.record_type)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data,
                         CONF_SEEN_EVENT_TYPES: sorted(runtime.seen_types)})
        async_dispatcher_send(hass, signal_new_type(entry), result.record_type)
    async_dispatcher_send(hass, signal_update(entry))


async def async_unload_entry(hass: HomeAssistant, entry: Bt610ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: Bt610ConfigEntry) -> None:
    """Allow rediscovery after the entry is removed."""
    bluetooth.async_rediscover_address(hass, entry.data[CONF_ADDRESS])
