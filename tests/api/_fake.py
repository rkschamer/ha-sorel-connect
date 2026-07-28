"""A lightweight fake aiohttp session for API client tests.

aioresponses does not support the aiohttp version Home Assistant pins, so we
exploit the client's injected-session design and pass a fake instead. The fake
maps request URLs to either a response body (str) or an exception to raise.
"""

from __future__ import annotations

import aiohttp


class _FakeResponse:
    def __init__(self, body: str | None, exc: Exception | None) -> None:
        self._body = body
        self._exc = exc
        self.cookies: dict = {}

    async def __aenter__(self) -> _FakeResponse:
        if self._exc is not None:
            raise self._exc
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    async def text(self, encoding: str = "utf-8") -> str | None:
        return self._body


class FakeSession:
    """Maps full request URLs to response bodies or exceptions."""

    def __init__(self, mapping: dict[str, object]) -> None:
        self._mapping = mapping
        self.cookie_jar = aiohttp.CookieJar()

    def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
        if url not in self._mapping:
            raise AssertionError(f"Unexpected request URL: {url}")
        value = self._mapping[url]
        if isinstance(value, Exception):
            return _FakeResponse(None, value)
        return _FakeResponse(str(value), None)
