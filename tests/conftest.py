import pytest

# HUOM: varmista import-polku asennettua HA-versiota vasten ennen kirjoitusta:
#   .venv/bin/python -c "from homeassistant.helpers.service_info.bluetooth import BluetoothServiceInfo"
# Tämä on nykyinen (2025+) sijainti; jos pinnattu versio eroaa, käytä
# home_assistant_bluetooth.BluetoothServiceInfo tai components.bluetooth-polkua.
from homeassistant.helpers.service_info.bluetooth import BluetoothServiceInfo

from tests.test_parser import GOLDEN, build_frame

ADDRESS = "D5:B7:68:24:B1:1F"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


# NOT in the brief: manifest.json's `dependencies: ["bluetooth_adapters"]`
# (required, matches core BLE integrations like govee_ble/sensorpush) makes
# HA actually set up the real `bluetooth` component whenever our config flow
# is exercised. Without mocking, that component tries to open a real
# AF_BLUETOOTH/HCI socket via habluetooth's BlueZ management controller,
# which pytest-socket blocks (and which would touch real hardware otherwise).
# pytest-homeassistant-custom-component ships a `mock_bluetooth` fixture
# (bundles mock_bleak_scanner_start + mock_bluetooth_adapters) for exactly
# this; HA core's own BLE-integration test suites apply it via an autouse
# fixture in their conftest.py. Doing the same here; no application code
# is affected.
@pytest.fixture(autouse=True)
def auto_mock_bluetooth(mock_bluetooth):
    yield


def make_service_info(payload: bytes = GOLDEN, address: str = ADDRESS,
                      name: str = "BT610", rssi: int = -67) -> BluetoothServiceInfo:
    return BluetoothServiceInfo(
        name=name, address=address, rssi=rssi,
        manufacturer_data={119: payload}, service_data={}, service_uuids=[],
        source="AA:BB:CC:DD:EE:FF",
    )
