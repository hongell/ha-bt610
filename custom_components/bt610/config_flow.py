"""Config flow for BT610: bluetooth discovery + manual selection."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.bluetooth import BluetoothServiceInfo

from .const import DOMAIN, LAIRD_MANUFACTURER_ID
from .parser import Bt610Event, parse


def _validate(info: BluetoothServiceInfo) -> bool:
    payload = info.manufacturer_data.get(LAIRD_MANUFACTURER_ID)
    return payload is not None and isinstance(parse(payload), Bt610Event)


class Bt610ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfo | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> ConfigFlowResult:
        if not _validate(discovery_info):
            return self.async_abort(reason="not_supported")
        # BT510 shares protocol 0x0001: reject devices that advertise a
        # different local name; nameless devices proceed to user confirmation.
        if discovery_info.name and not discovery_info.name.startswith("BT610"):
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or "BT610"}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery_info is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name or "BT610",
                data={CONF_ADDRESS: self._discovery_info.address},
            )
        self._set_confirm_only()
        return self.async_show_form(step_id="bluetooth_confirm")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        candidates = {
            info.address: info
            for info in bluetooth.async_discovered_service_info(
                self.hass, connectable=False)
            if _validate(info)
        }
        if user_input is not None:
            info = candidates.get(user_input[CONF_ADDRESS])
            if info is None:
                return self.async_abort(reason="no_devices_found")
            await self.async_set_unique_id(
                format_mac(info.address), raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=info.name or "BT610", data={CONF_ADDRESS: info.address})
        current = {e.unique_id for e in self._async_current_entries()}
        options = {a: f"{i.name or 'BT610'} ({a})" for a, i in candidates.items()
                   if format_mac(a) not in current}
        if not options:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)}),
        )
