"""Diagnostics for BT610."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import Bt610ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Bt610ConfigEntry
) -> dict[str, Any]:
    rt = entry.runtime_data
    return {
        "address": "**REDACTED**",
        "available": rt.available,
        "seen_event_types": sorted(rt.seen_types),
        "counters": dict(rt.counters),
        "last_rssi": rt.last_rssi,
        # Redact the embedded MAC (bytes 6-11 = hex chars 12-23).
        "last_frames": [f[:12] + "x" * 12 + f[24:] for f in rt.last_frames],
        "last_events": {
            str(t): {"record_number": e.record_number, "epoch": e.epoch,
                     "value": e.value}
            for t, e in rt.last_events.items()
        },
    }
