# Laird BT610 for Home Assistant

A Home Assistant custom integration for the [Laird/Ezurio Sentrius BT610](https://www.ezurio.com/) BLE I/O sensor. It passively parses the BT610's Bluetooth Low Energy advertisement frames (protocol `0x0001`) — no pairing, no connection, and no dedicated adapter required. Any Bluetooth proxy or adapter already known to Home Assistant's `bluetooth` integration (ESPHome BT proxy, USB adapter, etc.) is enough to receive data.

## Features

- **Passive advertisement parsing** — reads the BT610's manufacturer-specific BLE advertisements via Home Assistant's Bluetooth stack. No active connection to the device is made or required.
- **Dynamic sensors per configured channel** — entities are created on the fly as the integration observes advertisement record types from the device, so only the channels you have actually configured on the BT610 show up:
  - Current, channels 1–4 (A)
  - Temperature, channels 1–4, plus the base temperature record (°C)
  - Battery voltage (V)
- **Raw sensors (disabled by default)** — voltage, ultrasonic, and pressure channels are exposed as raw, unitless values because their scaling has not yet been verified against real hardware. They can be enabled manually in the entity settings once you've confirmed the conversion for your channel configuration.
- **RSSI diagnostic sensor (disabled by default)** — the received signal strength of the last advertisement, exposed as a diagnostic entity. Can be enabled manually in the entity settings.
- **Bluetooth discovery** — the device is found automatically as soon as a proxy/adapter sees its advertisements; it can also be added manually.
- **Diagnostics** — config entry diagnostics download with the device MAC address and any embedded MACs in captured frames redacted.

## Installation

### Via HACS (recommended)

1. HACS → the three-dot menu → **Custom repositories**.
2. Add `https://github.com/hongell/ha-bt610` as an **Integration**.
3. Find "Laird BT610" in HACS and install it.
4. Restart Home Assistant.
5. The device is discovered automatically once it advertises within range of a Bluetooth proxy or adapter. If it doesn't show up as a discovery, add it manually: **Settings → Devices & Services → Add Integration → Laird BT610**.

### Manual

Copy `custom_components/bt610` into your Home Assistant `custom_components` directory and restart Home Assistant.

## Device configuration

The BT610's channels (input type per channel, read/broadcast interval, etc.) are **not** configured through Home Assistant. Configure them with the official **Sentrius BT610** mobile app (BLE connection to the device), the same way you would set it up standalone.

This has one important consequence: **the BT610 does not send advertisements while the mobile app is connected to it.** Home Assistant will stop receiving updates for as long as the app session is open, and will resume automatically once it disconnects.

Sensors for a given channel only appear in Home Assistant after the integration has seen at least one advertisement carrying that channel's record type — i.e. after the channel has been enabled on the device and it has broadcast at least once.

## Limitations (v1)

- Only advertisement protocol `0x0001` is supported. Protocol `0x0003` and coded PHY (long-range) advertisements are not parsed.
- The BT510 is not supported (different sensor set/behavior), even though it shares the same manufacturer ID and, for some frames, protocol.
- Event/alarm, button, and tamper record types are received but not exposed as entities in v1 — only measurement record types (current, temperature, voltage, ultrasonic, pressure) and battery voltage are turned into sensors.
- Battery status is exposed as a voltage sensor only; the device's own good/bad battery classification is not surfaced as a separate entity.

## Credits and sources

Frame layout and record type numbering were derived from:

- [LairdCP/zephyr_lib](https://github.com/LairdCP/zephyr_lib) — `ble_common/include/lcz_sensor_event.h` (event/record type enum)
- The Laird/Ezurio Sentrius BT610 user manual

## License

[MIT](LICENSE)
