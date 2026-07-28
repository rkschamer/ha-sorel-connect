import pytest

from custom_components.sorel_connect.api.client import SorelConnectClient
from custom_components.sorel_connect.api.exceptions import SorelConnectionError


def _make_client() -> SorelConnectClient:
    return SorelConnectClient(
        session=None,  # not used by parsing/url tests
        base_url="https://test.sorel-connect.net",
        email="user@test.com",
        password="pw",
    )


def test_parse_plain_json():
    client = _make_client()
    assert client._parse_body('{"val": "42°C"}') == {"val": "42°C"}


def test_parse_jsonp_wrapped():
    client = _make_client()
    assert client._parse_body('({"session_key": "abc"});') == {"session_key": "abc"}


def test_parse_with_surrounding_whitespace():
    client = _make_client()
    assert client._parse_body('\n  {"val": "0"}  \n') == {"val": "0"}


def test_parse_malformed_raises():
    client = _make_client()
    with pytest.raises(SorelConnectionError):
        client._parse_body("no json here")


def test_url_with_query():
    client = _make_client()
    assert (
        client._url("sensors.json", {"id": 1})
        == "https://test.sorel-connect.net/sensors.json?id=1"
    )


def test_url_without_query():
    client = _make_client()
    assert (
        client._url("sensors.json")
        == "https://test.sorel-connect.net/sensors.json"
    )
