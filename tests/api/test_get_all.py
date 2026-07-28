from custom_components.sorel_connect.api.client import (
    SorelConnectClient,
    _clean_relay,
    _clean_sensor,
)
from custom_components.sorel_connect.api.models import (
    RelayReading,
    SensorReading,
    SorelData,
)

from ._fake import FakeSession

BASE = "https://test.sorel-connect.net"


def test_models_construct():
    data = SorelData(
        sensors={1: SensorReading(id=1, value=42.0)},
        relays={1: RelayReading(id=1, value=30.0)},
        logs=["newest", "older"],
    )
    assert data.sensors[1].value == 42.0
    assert data.relays[1].value == 30.0
    assert data.logs[0] == "newest"


def test_clean_sensor_strips_unit():
    assert _clean_sensor("42°C") == 42.0


def test_clean_sensor_decimal():
    assert _clean_sensor("23.5°C") == 23.5


def test_clean_sensor_double_dash_is_none():
    assert _clean_sensor("--") is None


def test_clean_relay_percent():
    assert _clean_relay("30_30%") == 30.0


def test_clean_relay_zero_percent():
    assert _clean_relay("0_0%") == 0.0


def test_clean_relay_aus_is_zero():
    assert _clean_relay("0_Aus") == 0.0


def test_clean_relay_ein_is_hundred():
    assert _clean_relay("0_Ein") == 100.0


async def test_get_all_skips_unconnected_sensors():
    session = FakeSession(
        {
            f"{BASE}/sensors.json?id=0": '{"val": "3"}',
            f"{BASE}/relays.json?id=0": '{"val": "1"}',
            f"{BASE}/log.json?id=0": '{"val": "2"}',
            f"{BASE}/sensors.json?id=1": '{"val": "42°C"}',
            f"{BASE}/sensors.json?id=2": '{"val": "--"}',
            f"{BASE}/sensors.json?id=3": '{"val": "24°C"}',
            f"{BASE}/relays.json?id=1": '{"val": "0_30%"}',
            f"{BASE}/log.json?id=1": '{"val": "newest"}',
            f"{BASE}/log.json?id=2": '{"val": "older"}',
        }
    )
    client = SorelConnectClient(session, BASE, "u", "p")
    data = await client.get_all()

    assert set(data.sensors) == {1, 3}
    assert data.sensors[1].value == 42.0
    assert data.relays[1].value == 30.0
    assert data.logs == ["newest", "older"]
