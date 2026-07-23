from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.bt610.const import DOMAIN
from tests.conftest import ADDRESS, make_service_info
from tests.test_parser import build_frame


async def test_bluetooth_discovery_creates_entry(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    with patch("custom_components.bt610.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"address": ADDRESS}
    assert result["result"].unique_id == "d5:b7:68:24:b1:1f"


async def test_bluetooth_discovery_rejects_bad_protocol(hass: HomeAssistant):
    info = make_service_info(payload=build_frame(proto=0x0003))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_rejects_missing_payload(hass: HomeAssistant):
    info = make_service_info()
    info.manufacturer_data = {76: b"\x00"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info)
    assert result["type"] is FlowResultType.ABORT


async def test_duplicate_discovery_aborts(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    MockConfigEntry(domain=DOMAIN, unique_id="d5:b7:68:24:b1:1f",
                    data={"address": ADDRESS}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_no_devices(hass: HomeAssistant):
    with patch("custom_components.bt610.config_flow."
               "bluetooth.async_discovered_service_info", return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_lists_and_creates(hass: HomeAssistant):
    with patch("custom_components.bt610.config_flow."
               "bluetooth.async_discovered_service_info",
               return_value=[make_service_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        with patch("custom_components.bt610.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={"address": ADDRESS})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"address": ADDRESS}
