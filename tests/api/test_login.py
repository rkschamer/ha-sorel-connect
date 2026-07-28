import aiohttp
import pytest

from custom_components.sorel_connect.api.client import SorelConnectClient
from custom_components.sorel_connect.api.exceptions import (
    SorelAuthError,
    SorelConnectionError,
)

from ._fake import FakeSession

BASE = "https://test.sorel-connect.net"
LOGIN_URL = (
    f"{BASE}/nabto/hosted_plugin/login/execute?email=user%40test.com&password=pw"
)


def _client(session) -> SorelConnectClient:
    return SorelConnectClient(session, BASE, "user@test.com", "pw")


async def test_login_success():
    session = FakeSession({LOGIN_URL: '({"session_key": "abc123"})'})
    client = _client(session)
    await client.login()  # should not raise


async def test_login_rejected_raises_auth_error():
    session = FakeSession({LOGIN_URL: '({"error": "bad credentials"})'})
    client = _client(session)
    with pytest.raises(SorelAuthError):
        await client.login()


async def test_login_network_error_raises_connection_error():
    session = FakeSession({LOGIN_URL: aiohttp.ClientError("boom")})
    client = _client(session)
    with pytest.raises(SorelConnectionError):
        await client.login()
