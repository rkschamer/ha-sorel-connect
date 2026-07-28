"""HA-agnostic Sorel Connect HTTP API client."""

import json
from urllib.parse import ParseResult, urlencode, urlparse, urlunparse

import aiohttp
from yarl import URL

from .exceptions import SorelAuthError, SorelConnectionError
from .models import RelayReading, SensorReading, SorelData


def _clean_sensor(raw: str) -> float | None:
    """Convert a sensor string like '42°C' to a float, or None if '--'."""
    raw = raw.strip()
    if raw == "--":
        return None
    return float(raw.rstrip("°C"))


def _clean_relay(raw: str) -> float:
    """Convert a relay string like '0_30%' or '0_Aus' to a percentage float."""
    value = raw.split("_", 1)[1].strip()
    if value == "Aus":
        return 0.0
    return float(value.rstrip("%"))


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

    async def _get_json(self, url: str) -> dict:
        try:
            async with self._session.get(
                url, headers={"X-Requested-With": "XMLHttpRequest"}
            ) as resp:
                resp.raise_for_status()
                text = await resp.text(encoding="utf-8")
        except aiohttp.ClientError as err:
            raise SorelConnectionError(str(err)) from err
        return self._parse_body(text)

    async def login(self) -> None:
        url = self._url(
            "/nabto/hosted_plugin/login/execute",
            {"email": self._email, "password": self._password},
        )
        body = await self._get_json(url)
        if not body.get("session_key"):
            raise SorelAuthError("Login rejected: no session_key in response")
        # The Set-Cookie is scoped to the login path; broaden it to / so it is
        # sent with subsequent data requests.
        cookie = self._session.cookie_jar.filter_cookies(URL(self._url("/"))).get(
            "nabto-session"
        )
        if cookie is not None:
            self._session.cookie_jar.update_cookies({"nabto-session": cookie.value})

    async def get_counts(self) -> tuple[int, int, int]:
        sensors = int(
            (await self._get_json(self._url("sensors.json", {"id": 0})))["val"]
        )
        relays = int(
            (await self._get_json(self._url("relays.json", {"id": 0})))["val"]
        )
        logs = int((await self._get_json(self._url("log.json", {"id": 0})))["val"])
        return sensors, relays, logs

    async def get_all(self) -> SorelData:
        sensor_count, relay_count, log_count = await self.get_counts()

        sensors: dict[int, SensorReading] = {}
        for sid in range(1, sensor_count + 1):
            raw = (await self._get_json(self._url("sensors.json", {"id": sid})))["val"]
            value = _clean_sensor(str(raw))
            if value is not None:
                sensors[sid] = SensorReading(id=sid, value=value)

        relays: dict[int, RelayReading] = {}
        for rid in range(1, relay_count + 1):
            raw = (await self._get_json(self._url("relays.json", {"id": rid})))["val"]
            relays[rid] = RelayReading(id=rid, value=_clean_relay(str(raw)))

        logs: list[str] = []
        for lid in range(1, log_count + 1):
            raw = (await self._get_json(self._url("log.json", {"id": lid})))["val"]
            logs.append(str(raw))

        return SorelData(sensors=sensors, relays=relays, logs=logs)
