from homeassistant.core import HomeAssistant

from custom_components.bt610.diagnostics import async_get_config_entry_diagnostics
from tests.conftest import make_service_info
from tests.test_parser import build_frame
from tests.test_sensor import _setup


async def test_diagnostics_content(hass: HomeAssistant):
    entry, cb, _ = await _setup(hass, {})
    cb(make_service_info(payload=build_frame(record_type=26)), None)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["counters"]["parsed"] == 1
    assert diag["seen_event_types"] == [26]
    assert len(diag["last_frames"]) == 1
    assert diag["address"] == "**REDACTED**"
    # Embedded MAC (reversed: 1fb12468b7d5) must not leak in frames
    assert "1fb12468b7d5" not in diag["last_frames"][0]
