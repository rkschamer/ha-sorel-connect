from custom_components.sorel_connect.api.client import SorelConnectClient

from ._fake import FakeSession

BASE = "https://test.sorel-connect.net"


async def test_get_counts():
    session = FakeSession(
        {
            f"{BASE}/sensors.json?id=0": '{"val": "13"}',
            f"{BASE}/relays.json?id=0": '{"val": "7"}',
            f"{BASE}/log.json?id=0": '{"val": "3"}',
        }
    )
    client = SorelConnectClient(session, BASE, "u", "p")
    assert await client.get_counts() == (13, 7, 3)
