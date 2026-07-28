"""HA-agnostic Sorel Connect HTTP API client."""

import json
from urllib.parse import ParseResult, urlencode, urlparse, urlunparse

import aiohttp

from .exceptions import SorelConnectionError


class SorelConnectClient:
    """Talks to a Sorel Connect controller over HTTP.

    The aiohttp session is injected so this class never owns HA state and
    can be unit-tested by mocking HTTP.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        email: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = urlparse(base_url)
        self._email = email
        self._password = password

    def _url(self, resource: str, query: dict | None = None) -> str:
        return urlunparse(
            ParseResult(
                scheme=self._base.scheme,
                netloc=self._base.netloc,
                path=resource,
                params="",
                query=urlencode(query or {}),
                fragment="",
            )
        )

    def _parse_body(self, text: str) -> dict:
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise SorelConnectionError(f"Malformed response body: {text!r}")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as err:
            raise SorelConnectionError(f"Invalid JSON in response: {text!r}") from err
