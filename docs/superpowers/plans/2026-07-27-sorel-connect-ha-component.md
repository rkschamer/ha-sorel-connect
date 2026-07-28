# Sorel Connect HA Custom Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the AppDaemon Sorel Connect app into a native, HACS-installable Home Assistant custom component that polls the controller over HTTP and exposes sensors, relays, and a log as native HA entities.

**Architecture:** Two layers — a pure `aiohttp` API client (`api/`, zero HA imports, injected `ClientSession`) and the HA integration layer (`DataUpdateCoordinator`, config/options/reauth flow, sensor platform). No MQTT. Credentials and poll interval configured via the HA UI.

**Tech Stack:** Python 3.13, Home Assistant, `aiohttp`, uv (build/deps), ruff (lint+format), pytest + `pytest-homeassistant-custom-component` + `aioresponses`, GitHub Actions CI.

## Global Constraints

- Python floor: **3.13** (matches current Home Assistant).
- Integration domain: **`sorel_connect`** (used verbatim in paths, `manifest.json`, `const.py`).
- The `api/` package MUST NOT import Home Assistant. It takes an `aiohttp.ClientSession` via its constructor (dependency injection).
- IoT class: **`local_polling`**. Default poll interval: **300** seconds.
- Device identity: identifier `sorel_connect`, manufacturer `"Sorel"`, model `"SOREL Connect"`.
- Entity naming: sensors `"Sensor {id}"` / `sorel_connect_sensor_{id}`; relays `"Relay {id}"` / `sorel_connect_relay_{id}`; log `"Log"` / `sorel_connect_log`.
- All lint/format via ruff; all tests via pytest. Commit after each task.

---

## File Structure

```
custom_components/sorel_connect/
  __init__.py          # setup/unload/reload entry; builds client + coordinator
  manifest.json        # HA integration metadata
  const.py             # DOMAIN, defaults, config keys
  config_flow.py       # setup + options + reauth flows
  coordinator.py       # DataUpdateCoordinator[SorelData]
  sensor.py            # sensor platform; entity discovery from coordinator data
  strings.json         # UI strings for the flows
  translations/en.json # English translations (mirror of strings.json)
  api/
    __init__.py        # re-exports client, models, exceptions
    client.py          # SorelConnectClient
    models.py          # SorelData, SensorReading, RelayReading
    exceptions.py      # SorelAuthError, SorelConnectionError
hacs.json              # HACS metadata
pyproject.toml         # uv project, ruff + pytest config, deps
README.md              # install/config docs
.github/workflows/ci.yml  # ruff + pytest
tests/
  conftest.py          # fixtures
  api/
    test_parsing.py
    test_login.py
    test_counts.py
    test_get_all.py
  test_coordinator.py
  test_config_flow.py
  test_sensor.py
```

---

### Task 1: Repo migration + uv/ruff project scaffold

Remove the AppDaemon app and replace the project metadata with a uv-managed project configured for ruff and pytest. This produces a clean, empty-but-installable project skeleton.

**Files:**
- Delete: `apps/`, `dashboards/`, `appdaemon.yaml`, `secrets.yaml`, `poetry.lock`, `tests/test_sorel_connect.py`, `tests/conftest.py`, `tests/__init__.py`
- Modify: `pyproject.toml` (full rewrite), `.gitignore`
- Create: `custom_components/sorel_connect/__init__.py` (empty placeholder for now)

**Interfaces:**
- Produces: a `uv`-resolvable project; `uv run ruff check .` and `uv run pytest` both runnable.

- [ ] **Step 1: Remove AppDaemon files**

```bash
git rm -r apps dashboards appdaemon.yaml secrets.yaml poetry.lock \
  tests/test_sorel_connect.py tests/conftest.py tests/__init__.py
```

- [ ] **Step 2: Rewrite `pyproject.toml`**

```toml
[project]
name = "sorel-connect"
version = "0.1.0"
description = "Home Assistant custom component for the Sorel Connect heating controller"
readme = "README.md"
license = { text = "MIT" }
authors = [{ name = "René Kschamer" }]
requires-python = ">=3.13"
dependencies = ["aiohttp>=3.9"]

[dependency-groups]
dev = [
    "homeassistant",
    "pytest>=8.0",
    "pytest-homeassistant-custom-component",
    "pytest-asyncio>=0.23",
    "aioresponses>=0.7",
    "ruff>=0.6",
]

[tool.ruff]
line-length = 88
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "W"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["custom_components/sorel_connect"]
```

- [ ] **Step 3: Rewrite `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
logs/
```

- [ ] **Step 4: Create placeholder package files**

Create `custom_components/sorel_connect/__init__.py`:

```python
"""The Sorel Connect integration."""
```

Create empty `tests/__init__.py` and `tests/api/__init__.py` (empty files).

- [ ] **Step 5: Resolve environment and verify tooling runs**

Run: `uv sync`
Then: `uv run ruff check .`
Expected: ruff runs and reports "All checks passed" (no Python files with errors yet).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: migrate repo to uv/ruff HA custom component scaffold"
```

---

### Task 2: API exceptions and data models

Define the exception types and the dataclasses returned by the client. Pure Python, no dependencies.

**Files:**
- Create: `custom_components/sorel_connect/api/exceptions.py`, `custom_components/sorel_connect/api/models.py`, `custom_components/sorel_connect/api/__init__.py`
- Test: `tests/api/test_get_all.py` (imports only, verifies models construct — expanded in Task 5)

**Interfaces:**
- Produces:
  - `SorelAuthError(Exception)`, `SorelConnectionError(Exception)`
  - `SensorReading(id: int, value: float)`
  - `RelayReading(id: int, value: float)`
  - `SorelData(sensors: dict[int, SensorReading], relays: dict[int, RelayReading], logs: list[str])`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_get_all.py`:

```python
from custom_components.sorel_connect.api.models import (
    RelayReading,
    SensorReading,
    SorelData,
)


def test_models_construct():
    data = SorelData(
        sensors={1: SensorReading(id=1, value=42.0)},
        relays={1: RelayReading(id=1, value=30.0)},
        logs=["newest", "older"],
    )
    assert data.sensors[1].value == 42.0
    assert data.relays[1].value == 30.0
    assert data.logs[0] == "newest"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_get_all.py -v`
Expected: FAIL with `ModuleNotFoundError` for the api package.

- [ ] **Step 3: Write the implementations**

Create `custom_components/sorel_connect/api/exceptions.py`:

```python
"""Exceptions raised by the Sorel Connect API client."""


class SorelAuthError(Exception):
    """Raised when login is rejected by the controller."""


class SorelConnectionError(Exception):
    """Raised on network or HTTP failures talking to the controller."""
```

Create `custom_components/sorel_connect/api/models.py`:

```python
"""Data models returned by the Sorel Connect API client."""

from dataclasses import dataclass


@dataclass
class SensorReading:
    """A single temperature sensor reading in degrees Celsius."""

    id: int
    value: float


@dataclass
class RelayReading:
    """A single relay reading as a percentage (0-100)."""

    id: int
    value: float


@dataclass
class SorelData:
    """A full snapshot of the controller state."""

    sensors: dict[int, SensorReading]
    relays: dict[int, RelayReading]
    logs: list[str]
```

Create `custom_components/sorel_connect/api/__init__.py`:

```python
"""HA-agnostic Sorel Connect API client."""

from .client import SorelConnectClient
from .exceptions import SorelAuthError, SorelConnectionError
from .models import RelayReading, SensorReading, SorelData

__all__ = [
    "SorelConnectClient",
    "SorelAuthError",
    "SorelConnectionError",
    "RelayReading",
    "SensorReading",
    "SorelData",
]
```

Note: `api/__init__.py` imports `SorelConnectClient` from `.client`, which does not exist yet. Create a temporary stub `custom_components/sorel_connect/api/client.py` so the import resolves:

```python
"""Sorel Connect API client (implemented across Tasks 3-5)."""


class SorelConnectClient:
    """Placeholder — real implementation added in Task 3."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_get_all.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/api tests/api/test_get_all.py
git commit -m "feat: add API exceptions and data models"
```

---

### Task 3: API client — response parsing + constructor

Implement the client constructor (injected session, base URL, credentials) and the private response-body parsing helper that extracts the JSON object from both plain-JSON and JSONP responses.

**Files:**
- Modify: `custom_components/sorel_connect/api/client.py`
- Test: `tests/api/test_parsing.py`

**Interfaces:**
- Consumes: `SorelConnectionError` from Task 2.
- Produces:
  - `SorelConnectClient(session: aiohttp.ClientSession, base_url: str, email: str, password: str)`
  - `SorelConnectClient._url(resource: str, query: dict | None = None) -> str`
  - `SorelConnectClient._parse_body(text: str) -> dict` — extracts `{...}` from first `{` to last `}` and JSON-decodes; raises `SorelConnectionError` on malformed input.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_parsing.py`:

```python
import aiohttp
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_parsing.py -v`
Expected: FAIL — placeholder client has no `__init__` params, `_url`, or `_parse_body`.

- [ ] **Step 3: Write the implementation**

Replace `custom_components/sorel_connect/api/client.py`:

```python
"""HA-agnostic Sorel Connect HTTP API client."""

import json
from urllib.parse import ParseResult, urlencode, urlparse, urlunparse

import aiohttp

from .exceptions import SorelAuthError, SorelConnectionError


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_parsing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/api/client.py tests/api/test_parsing.py
git commit -m "feat: add API client constructor and response parsing"
```

---

### Task 4: API client — login and count fetching

Add `login()` (with cookie broadening) and `get_counts()`. Both perform real HTTP GETs against the injected session, mocked in tests with `aioresponses`.

**Files:**
- Modify: `custom_components/sorel_connect/api/client.py`
- Test: `tests/api/test_login.py`, `tests/api/test_counts.py`

**Interfaces:**
- Consumes: `_url`, `_parse_body`, `SorelAuthError`, `SorelConnectionError`.
- Produces:
  - `async login() -> None` — raises `SorelAuthError` if no `session_key`; broadens `nabto-session` cookie to path `/`.
  - `async get_counts() -> tuple[int, int, int]` — returns `(sensor_count, relay_count, log_count)`.
  - Private `async _get_json(url: str) -> dict` — GET + parse; raises `SorelConnectionError` on client errors.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_login.py`:

```python
import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.sorel_connect.api.client import SorelConnectClient
from custom_components.sorel_connect.api.exceptions import (
    SorelAuthError,
    SorelConnectionError,
)

BASE = "https://test.sorel-connect.net"
LOGIN_PATH = "/nabto/hosted_plugin/login/execute"


async def _client(session):
    return SorelConnectClient(session, BASE, "user@test.com", "pw")


async def test_login_success():
    with aioresponses() as m:
        m.get(
            f"{BASE}{LOGIN_PATH}?email=user@test.com&password=pw",
            body='({"session_key": "abc123"})',
        )
        async with aiohttp.ClientSession() as session:
            client = await _client(session)
            await client.login()  # should not raise


async def test_login_rejected_raises_auth_error():
    with aioresponses() as m:
        m.get(
            f"{BASE}{LOGIN_PATH}?email=user@test.com&password=pw",
            body='({"error": "bad credentials"})',
        )
        async with aiohttp.ClientSession() as session:
            client = await _client(session)
            with pytest.raises(SorelAuthError):
                await client.login()


async def test_login_network_error_raises_connection_error():
    with aioresponses() as m:
        m.get(
            f"{BASE}{LOGIN_PATH}?email=user@test.com&password=pw",
            exception=aiohttp.ClientError("boom"),
        )
        async with aiohttp.ClientSession() as session:
            client = await _client(session)
            with pytest.raises(SorelConnectionError):
                await client.login()
```

Create `tests/api/test_counts.py`:

```python
import aiohttp
from aioresponses import aioresponses

from custom_components.sorel_connect.api.client import SorelConnectClient

BASE = "https://test.sorel-connect.net"


async def test_get_counts():
    with aioresponses() as m:
        m.get(f"{BASE}/sensors.json?id=0", body='{"val": "13"}')
        m.get(f"{BASE}/relays.json?id=0", body='{"val": "7"}')
        m.get(f"{BASE}/log.json?id=0", body='{"val": "3"}')
        async with aiohttp.ClientSession() as session:
            client = SorelConnectClient(session, BASE, "u", "p")
            assert await client.get_counts() == (13, 7, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_login.py tests/api/test_counts.py -v`
Expected: FAIL — `login`, `get_counts`, `_get_json` not defined.

- [ ] **Step 3: Write the implementation**

Add to `custom_components/sorel_connect/api/client.py` (imports `aiohttp` already present):

```python
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
        cookie = self._session.cookie_jar.filter_cookies(
            self._url("/")
        ).get("nabto-session")
        if cookie is not None:
            self._session.cookie_jar.update_cookies(
                {"nabto-session": cookie.value}
            )

    async def get_counts(self) -> tuple[int, int, int]:
        sensors = int((await self._get_json(self._url("sensors.json", {"id": 0})))["val"])
        relays = int((await self._get_json(self._url("relays.json", {"id": 0})))["val"])
        logs = int((await self._get_json(self._url("log.json", {"id": 0})))["val"])
        return sensors, relays, logs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_login.py tests/api/test_counts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/api/client.py tests/api/test_login.py tests/api/test_counts.py
git commit -m "feat: add login and count fetching to API client"
```

---

### Task 5: API client — get_all with value cleaning

Add `get_all()`, which fetches counts then per-entity values, cleans them, and returns a `SorelData`. This is where the sensor/relay/log cleaning logic lives.

**Files:**
- Modify: `custom_components/sorel_connect/api/client.py`
- Test: `tests/api/test_get_all.py` (extend the file from Task 2)

**Interfaces:**
- Consumes: `_url`, `_get_json`, `get_counts`, models from Task 2.
- Produces:
  - `async get_all() -> SorelData`
  - Static helpers (module-level functions in `client.py`): `_clean_sensor(raw: str) -> float | None` (returns `None` for `"--"`), `_clean_relay(raw: str) -> float` (`"0_30%"` → 30.0, `"0_Aus"` → 0.0).

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/api/test_get_all.py` with:

```python
import aiohttp
from aioresponses import aioresponses

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


async def test_get_all_skips_unconnected_sensors():
    with aioresponses() as m:
        m.get(f"{BASE}/sensors.json?id=0", body='{"val": "3"}')
        m.get(f"{BASE}/relays.json?id=0", body='{"val": "1"}')
        m.get(f"{BASE}/log.json?id=0", body='{"val": "2"}')
        m.get(f"{BASE}/sensors.json?id=1", body='{"val": "42°C"}')
        m.get(f"{BASE}/sensors.json?id=2", body='{"val": "--"}')
        m.get(f"{BASE}/sensors.json?id=3", body='{"val": "24°C"}')
        m.get(f"{BASE}/relays.json?id=1", body='{"val": "0_30%"}')
        m.get(f"{BASE}/log.json?id=1", body='{"val": "newest"}')
        m.get(f"{BASE}/log.json?id=2", body='{"val": "older"}')
        async with aiohttp.ClientSession() as session:
            client = SorelConnectClient(session, BASE, "u", "p")
            data = await client.get_all()

    assert set(data.sensors) == {1, 3}
    assert data.sensors[1].value == 42.0
    assert data.relays[1].value == 30.0
    assert data.logs == ["newest", "older"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_get_all.py -v`
Expected: FAIL — `_clean_sensor`, `_clean_relay`, `get_all` not defined.

- [ ] **Step 3: Write the implementation**

Add module-level helpers and the method to `custom_components/sorel_connect/api/client.py`. Add these imports at the top: `from .models import RelayReading, SensorReading, SorelData`.

Module-level functions (place above the class):

```python
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
```

Method on the class:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/ -v`
Expected: PASS (all api tests)

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/api/client.py tests/api/test_get_all.py
git commit -m "feat: add get_all with sensor/relay/log cleaning"
```

---

### Task 6: Constants, manifest, and HACS metadata

Add `const.py`, `manifest.json`, and `hacs.json`. No behavior, but required for HA to load the integration and for HACS to install it.

**Files:**
- Create: `custom_components/sorel_connect/const.py`, `custom_components/sorel_connect/manifest.json`, `hacs.json`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces (from `const.py`): `DOMAIN = "sorel_connect"`, `DEFAULT_SCAN_INTERVAL = 300`, `CONF_URL = "url"`, `CONF_EMAIL = "email"`, `CONF_PASSWORD = "password"`, `CONF_SCAN_INTERVAL = "scan_interval"`, `MANUFACTURER = "Sorel"`, `MODEL = "SOREL Connect"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_manifest.py`:

```python
import json
from pathlib import Path

from custom_components.sorel_connect.const import DOMAIN

MANIFEST = Path("custom_components/sorel_connect/manifest.json")


def test_manifest_domain_matches_const():
    data = json.loads(MANIFEST.read_text())
    assert data["domain"] == DOMAIN
    assert data["config_flow"] is True
    assert data["iot_class"] == "local_polling"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: FAIL — `const` module and manifest missing.

- [ ] **Step 3: Write the implementations**

Create `custom_components/sorel_connect/const.py`:

```python
"""Constants for the Sorel Connect integration."""

DOMAIN = "sorel_connect"

DEFAULT_SCAN_INTERVAL = 300

CONF_URL = "url"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

MANUFACTURER = "Sorel"
MODEL = "SOREL Connect"
```

Create `custom_components/sorel_connect/manifest.json`:

```json
{
  "domain": "sorel_connect",
  "name": "Sorel Connect",
  "codeowners": ["@rkschamer"],
  "config_flow": true,
  "documentation": "https://github.com/rkschamer/sorel-connect",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/rkschamer/sorel-connect/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

Create `hacs.json`:

```json
{
  "name": "Sorel Connect",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/const.py custom_components/sorel_connect/manifest.json hacs.json tests/test_manifest.py
git commit -m "feat: add constants, manifest, and HACS metadata"
```

---

### Task 7: DataUpdateCoordinator

Implement the coordinator that polls the client and handles auth-expiry retry. This is the first task that imports HA and uses `pytest-homeassistant-custom-component`.

**Files:**
- Create: `custom_components/sorel_connect/coordinator.py`
- Create: `tests/conftest.py` (shared fixtures)
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `SorelConnectClient`, `SorelData`, `SorelAuthError`, `SorelConnectionError`.
- Produces:
  - `SorelCoordinator(hass, client: SorelConnectClient, scan_interval: int)` subclassing `DataUpdateCoordinator[SorelData]`.
  - `_async_update_data()` behavior: logs in if never logged in; on `SorelAuthError` retries login once then re-fetches; if that fails raises `ConfigEntryAuthFailed`; on `SorelConnectionError` raises `UpdateFailed`.
  - Attribute `_logged_in: bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/conftest.py`:

```python
"""Shared test fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sorel_connect.api.models import (
    RelayReading,
    SensorReading,
    SorelData,
)


@pytest.fixture
def sample_data() -> SorelData:
    return SorelData(
        sensors={1: SensorReading(id=1, value=42.0), 3: SensorReading(id=3, value=24.0)},
        relays={1: RelayReading(id=1, value=30.0)},
        logs=["newest", "middle", "oldest"],
    )


@pytest.fixture
def mock_client(sample_data: SorelData) -> MagicMock:
    client = MagicMock()
    client.login = AsyncMock()
    client.get_all = AsyncMock(return_value=sample_data)
    return client
```

Create `tests/test_coordinator.py`:

```python
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sorel_connect.api.exceptions import (
    SorelAuthError,
    SorelConnectionError,
)
from custom_components.sorel_connect.coordinator import SorelCoordinator


async def test_first_update_logs_in_and_returns_data(hass, mock_client, sample_data):
    coordinator = SorelCoordinator(hass, mock_client, scan_interval=300)
    data = await coordinator._async_update_data()
    mock_client.login.assert_awaited_once()
    assert data is sample_data


async def test_second_update_does_not_relogin(hass, mock_client):
    coordinator = SorelCoordinator(hass, mock_client, scan_interval=300)
    await coordinator._async_update_data()
    await coordinator._async_update_data()
    mock_client.login.assert_awaited_once()


async def test_auth_error_retries_login_once(hass, mock_client, sample_data):
    coordinator = SorelCoordinator(hass, mock_client, scan_interval=300)
    await coordinator._async_update_data()  # logged in
    mock_client.get_all = AsyncMock(side_effect=[SorelAuthError(), sample_data])
    data = await coordinator._async_update_data()
    assert data is sample_data
    assert mock_client.login.await_count == 2


async def test_auth_error_twice_raises_config_entry_auth_failed(hass, mock_client):
    coordinator = SorelCoordinator(hass, mock_client, scan_interval=300)
    await coordinator._async_update_data()
    mock_client.get_all = AsyncMock(side_effect=SorelAuthError())
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_connection_error_raises_update_failed(hass, mock_client):
    coordinator = SorelCoordinator(hass, mock_client, scan_interval=300)
    mock_client.get_all = AsyncMock(side_effect=SorelConnectionError())
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coordinator.py -v`
Expected: FAIL — `coordinator` module missing.

- [ ] **Step 3: Write the implementation**

Create `custom_components/sorel_connect/coordinator.py`:

```python
"""DataUpdateCoordinator for Sorel Connect."""

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.client import SorelConnectClient
from .api.exceptions import SorelAuthError, SorelConnectionError
from .api.models import SorelData
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SorelCoordinator(DataUpdateCoordinator[SorelData]):
    """Polls the Sorel Connect controller on a fixed interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SorelConnectClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._client = client
        self._logged_in = False

    async def _async_update_data(self) -> SorelData:
        if not self._logged_in:
            await self._login()

        try:
            return await self._client.get_all()
        except SorelAuthError:
            # Session likely expired; re-login once and retry.
            try:
                await self._login()
                return await self._client.get_all()
            except (SorelAuthError, SorelConnectionError) as err:
                self._logged_in = False
                raise ConfigEntryAuthFailed("Re-authentication failed") from err
        except SorelConnectionError as err:
            raise UpdateFailed(str(err)) from err

    async def _login(self) -> None:
        try:
            await self._client.login()
            self._logged_in = True
        except SorelAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SorelConnectionError as err:
            raise UpdateFailed(str(err)) from err
```

Note: `test_connection_error_raises_update_failed` expects `login()` to succeed (mock default) then `get_all()` to raise `SorelConnectionError` → `UpdateFailed`. This matches the implementation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_coordinator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/coordinator.py tests/conftest.py tests/test_coordinator.py
git commit -m "feat: add DataUpdateCoordinator with auth-retry handling"
```

---

### Task 8: Config flow (setup, options, reauth) + strings

Implement the config flow with credential validation, the options flow for the poll interval, and the reauth flow. Add `strings.json` and `translations/en.json`.

**Files:**
- Create: `custom_components/sorel_connect/config_flow.py`, `custom_components/sorel_connect/strings.json`, `custom_components/sorel_connect/translations/en.json`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `SorelConnectClient`, `SorelAuthError`, `SorelConnectionError`, all `CONF_*` and `DEFAULT_SCAN_INTERVAL`, `DOMAIN`.
- Produces:
  - `SorelConfigFlow(ConfigFlow, domain=DOMAIN)` with `async_step_user`, `async_step_reauth`, `async_step_reauth_confirm`, and static `async_get_options_flow`.
  - `SorelOptionsFlow(OptionsFlow)` with `async_step_init` editing `CONF_SCAN_INTERVAL`.
  - Helper `async _validate(hass, url, email, password) -> None` raising the API exceptions.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_flow.py`:

```python
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow

from custom_components.sorel_connect.api.exceptions import (
    SorelAuthError,
    SorelConnectionError,
)
from custom_components.sorel_connect.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DOMAIN,
)

USER_INPUT = {
    CONF_URL: "https://db7bb5.sorel-connect.net",
    CONF_EMAIL: "user@test.com",
    CONF_PASSWORD: "pw",
    CONF_SCAN_INTERVAL: 300,
}


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_success_creates_entry(hass):
    result = await _start(hass)
    with patch(
        "custom_components.sorel_connect.config_flow.SorelConnectClient.login",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_URL] == USER_INPUT[CONF_URL]
    assert result["options"][CONF_SCAN_INTERVAL] == 300


async def test_user_flow_invalid_auth(hass):
    result = await _start(hass)
    with patch(
        "custom_components.sorel_connect.config_flow.SorelConnectClient.login",
        new=AsyncMock(side_effect=SorelAuthError()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass):
    result = await _start(hass)
    with patch(
        "custom_components.sorel_connect.config_flow.SorelConnectClient.login",
        new=AsyncMock(side_effect=SorelConnectionError()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_single_instance_aborts(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(
        domain=DOMAIN, unique_id="db7bb5.sorel-connect.net", data=USER_INPUT
    ).add_to_hass(hass)

    result = await _start(hass)
    with patch(
        "custom_components.sorel_connect.config_flow.SorelConnectClient.login",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_interval(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="db7bb5.sorel-connect.net",
        data=USER_INPUT,
        options={CONF_SCAN_INTERVAL: 300},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 600}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SCAN_INTERVAL] == 600
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_flow.py -v`
Expected: FAIL — `config_flow` module missing.

- [ ] **Step 3: Write the implementation**

Create `custom_components/sorel_connect/config_flow.py`:

```python
"""Config, options, and reauth flows for Sorel Connect."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import SorelConnectClient
from .api.exceptions import SorelAuthError, SorelConnectionError
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


async def _validate(
    hass: HomeAssistant, url: str, email: str, password: str
) -> None:
    """Attempt a login; raises SorelAuthError / SorelConnectionError."""
    session = async_get_clientsession(hass)
    client = SorelConnectClient(session, url, email, password)
    await client.login()


class SorelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup and reauth."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = urlparse(user_input[CONF_URL]).netloc
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                await _validate(
                    self.hass,
                    user_input[CONF_URL],
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                )
            except SorelAuthError:
                errors["base"] = "invalid_auth"
            except SorelConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=host,
                    data={
                        CONF_URL: user_input[CONF_URL],
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options={
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        )
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL): str,
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): int,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _validate(
                    self.hass,
                    entry.data[CONF_URL],
                    entry.data[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                )
            except SorelAuthError:
                errors["base"] = "invalid_auth"
            except SorelConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SorelOptionsFlow()


class SorelOptionsFlow(OptionsFlow):
    """Handle editing the poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCAN_INTERVAL, default=current): int}
            ),
        )
```

Create `custom_components/sorel_connect/strings.json`:

```json
{
  "config": {
    "step": {
      "user": {
        "data": {
          "url": "URL",
          "email": "Email",
          "password": "Password",
          "scan_interval": "Poll interval (seconds)"
        }
      },
      "reauth_confirm": {
        "data": { "password": "Password" }
      }
    },
    "error": {
      "invalid_auth": "Invalid credentials",
      "cannot_connect": "Failed to connect"
    },
    "abort": {
      "already_configured": "This controller is already configured",
      "reauth_successful": "Re-authentication was successful"
    }
  },
  "options": {
    "step": {
      "init": {
        "data": { "scan_interval": "Poll interval (seconds)" }
      }
    }
  }
}
```

Create `custom_components/sorel_connect/translations/en.json` with identical content to `strings.json`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config_flow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/config_flow.py custom_components/sorel_connect/strings.json custom_components/sorel_connect/translations tests/test_config_flow.py
git commit -m "feat: add config, options, and reauth flows"
```

---

### Task 9: Integration setup/unload (`__init__.py`)

Wire the config entry to the client, coordinator, and sensor platform. Reload on options update.

**Files:**
- Modify: `custom_components/sorel_connect/__init__.py`
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: `SorelConnectClient`, `SorelCoordinator`, all `CONF_*`, `DEFAULT_SCAN_INTERVAL`, `DOMAIN`.
- Produces:
  - `async_setup_entry(hass, entry) -> bool` — stores `SorelCoordinator` in `hass.data[DOMAIN][entry.entry_id]`, forwards to `["sensor"]`, registers an options-update reload listener.
  - `async_unload_entry(hass, entry) -> bool`.
  - `PLATFORMS = ["sensor"]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_init.py`:

```python
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sorel_connect.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DOMAIN,
)


async def test_setup_and_unload_entry(hass, sample_data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="db7bb5.sorel-connect.net",
        data={
            CONF_URL: "https://db7bb5.sorel-connect.net",
            CONF_EMAIL: "user@test.com",
            CONF_PASSWORD: "pw",
        },
        options={CONF_SCAN_INTERVAL: 300},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.sorel_connect.SorelConnectClient.login", new=AsyncMock()
    ), patch(
        "custom_components.sorel_connect.SorelConnectClient.get_all",
        new=AsyncMock(return_value=sample_data),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.entry_id in hass.data[DOMAIN]

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.entry_id not in hass.data[DOMAIN]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_init.py -v`
Expected: FAIL — `async_setup_entry` not implemented.

- [ ] **Step 3: Write the implementation**

Replace `custom_components/sorel_connect/__init__.py`:

```python
"""The Sorel Connect integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import SorelConnectClient
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import SorelCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sorel Connect from a config entry."""
    session = async_get_clientsession(hass)
    client = SorelConnectClient(
        session,
        entry.data[CONF_URL],
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SorelCoordinator(hass, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_init.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/sorel_connect/__init__.py tests/test_init.py
git commit -m "feat: add integration setup/unload/reload"
```

---

### Task 10: Sensor platform with first-poll discovery

Create the sensor entities. Only connected sensors/relays present in the first poll become entities; plus one log entity. All share one device.

**Files:**
- Create: `custom_components/sorel_connect/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `SorelCoordinator`, `SorelData`, `DOMAIN`, `MANUFACTURER`, `MODEL`.
- Produces:
  - `async_setup_entry(hass, entry, async_add_entities)` — builds `SorelSensorEntity` per `coordinator.data.sensors`, `SorelRelayEntity` per `coordinator.data.relays`, one `SorelLogEntity`.
  - Entity classes with `unique_id`, `native_value`, `device_info`, correct units/device_class; log entity exposes `extra_state_attributes` with `log_1..log_N`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sensor.py`:

```python
from unittest.mock import AsyncMock, patch

from homeassistant.const import UnitOfTemperature
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sorel_connect.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DOMAIN,
)

DATA = {
    CONF_URL: "https://db7bb5.sorel-connect.net",
    CONF_EMAIL: "user@test.com",
    CONF_PASSWORD: "pw",
}


async def _setup(hass, sample_data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="db7bb5.sorel-connect.net",
        data=DATA,
        options={CONF_SCAN_INTERVAL: 300},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.sorel_connect.SorelConnectClient.login", new=AsyncMock()
    ), patch(
        "custom_components.sorel_connect.SorelConnectClient.get_all",
        new=AsyncMock(return_value=sample_data),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_creates_only_connected_sensors(hass, sample_data):
    # sample_data has sensors {1, 3}, relays {1}
    await _setup(hass, sample_data)
    assert hass.states.get("sensor.sensor_1") is not None
    assert hass.states.get("sensor.sensor_3") is not None
    assert hass.states.get("sensor.sensor_2") is None


async def test_sensor_state_and_unit(hass, sample_data):
    await _setup(hass, sample_data)
    state = hass.states.get("sensor.sensor_1")
    assert state.state == "42.0"
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.CELSIUS
    assert state.attributes["device_class"] == "temperature"


async def test_relay_state_and_unit(hass, sample_data):
    await _setup(hass, sample_data)
    state = hass.states.get("sensor.relay_1")
    assert state.state == "30.0"
    assert state.attributes["unit_of_measurement"] == "%"
    assert "device_class" not in state.attributes


async def test_log_entity_state_and_attributes(hass, sample_data):
    await _setup(hass, sample_data)
    state = hass.states.get("sensor.log")
    assert state.state == "newest"
    assert state.attributes["log_1"] == "newest"
    assert state.attributes["log_2"] == "middle"
    assert state.attributes["log_3"] == "oldest"
```

Note: entity_id slugs (`sensor.sensor_1`, `sensor.relay_1`, `sensor.log`) are derived by HA from the entity `name`. The `name` values below produce these slugs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sensor.py -v`
Expected: FAIL — `sensor` module missing.

- [ ] **Step 3: Write the implementation**

Create `custom_components/sorel_connect/sensor.py`:

```python
"""Sensor platform for Sorel Connect."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SorelCoordinator

_DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, "sorel_connect")},
    name="Sorel Connect",
    manufacturer=MANUFACTURER,
    model=MODEL,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities from the first coordinator poll."""
    coordinator: SorelCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    entities.extend(
        SorelSensorEntity(coordinator, sid) for sid in coordinator.data.sensors
    )
    entities.extend(
        SorelRelayEntity(coordinator, rid) for rid in coordinator.data.relays
    )
    entities.append(SorelLogEntity(coordinator))
    async_add_entities(entities)


class SorelSensorEntity(CoordinatorEntity[SorelCoordinator], SensorEntity):
    """A temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_info = _DEVICE_INFO

    def __init__(self, coordinator: SorelCoordinator, sensor_id: int) -> None:
        super().__init__(coordinator)
        self._id = sensor_id
        self._attr_name = f"Sensor {sensor_id}"
        self._attr_unique_id = f"sorel_connect_sensor_{sensor_id}"

    @property
    def native_value(self) -> float | None:
        reading = self.coordinator.data.sensors.get(self._id)
        return reading.value if reading else None


class SorelRelayEntity(CoordinatorEntity[SorelCoordinator], SensorEntity):
    """A relay reported as a percentage."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_info = _DEVICE_INFO

    def __init__(self, coordinator: SorelCoordinator, relay_id: int) -> None:
        super().__init__(coordinator)
        self._id = relay_id
        self._attr_name = f"Relay {relay_id}"
        self._attr_unique_id = f"sorel_connect_relay_{relay_id}"

    @property
    def native_value(self) -> float | None:
        reading = self.coordinator.data.relays.get(self._id)
        return reading.value if reading else None


class SorelLogEntity(CoordinatorEntity[SorelCoordinator], SensorEntity):
    """The controller log; state is the newest entry."""

    _attr_name = "Log"
    _attr_unique_id = "sorel_connect_log"
    _attr_device_info = _DEVICE_INFO

    @property
    def native_value(self) -> str | None:
        logs = self.coordinator.data.logs
        return logs[0] if logs else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            f"log_{i}": entry
            for i, entry in enumerate(self.coordinator.data.logs, start=1)
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sensor.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add custom_components/sorel_connect/sensor.py tests/test_sensor.py
git commit -m "feat: add sensor platform with first-poll entity discovery"
```

---

### Task 11: CI workflow, README, and final lint pass

Add GitHub Actions CI, the README with install/config instructions, and ensure the whole project passes ruff.

**Files:**
- Create: `.github/workflows/ci.yml`, `README.md`
- Modify: any files ruff flags.

**Interfaces:** none (no new code).

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Set up Python
        run: uv python install 3.13
      - name: Sync dependencies
        run: uv sync
      - name: Ruff check
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .
      - name: Pytest
        run: uv run pytest
```

- [ ] **Step 2: Create the README**

Create `README.md`:

````markdown
# Sorel Connect for Home Assistant

A HACS-installable custom component that polls a [Sorel Connect](https://www.sorel.de/)
heating controller over HTTP and exposes its sensors, relays, and log as native
Home Assistant entities. No MQTT broker required.

## Installation (HACS)

1. Add this repository as a custom repository in HACS (category: Integration).
2. Install "Sorel Connect".
3. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Sorel Connect**.
3. Enter:
   - **URL** — your controller URL, e.g. `https://xxxxxx.sorel-connect.net`
   - **Email** / **Password** — your Sorel Connect login
   - **Poll interval** — seconds between updates (default 300)

Credentials are validated during setup. The poll interval can be changed later
via the integration's **Configure** (options) dialog.

## Entities

- **Sensor N** — temperature sensors reported in °C (only connected sensors appear).
- **Relay N** — relay output as a percentage (0–100; `Aus`/off is reported as 0).
- **Log** — the newest log entry as state, with all entries as `log_1..log_N` attributes.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```
````

- [ ] **Step 3: Run the full lint + format + test gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest`
Expected: all pass. If `ruff format --check` reports files, run `uv run ruff format .` and re-run.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "chore: add CI workflow and README"
```

---

## Self-Review Notes

- **Spec coverage:** native integration (Tasks 7–10), no MQTT (nothing added), credentials via config flow (Task 8), configurable interval + options (Task 8), HA-agnostic injected-session client (Tasks 3–5), create-only-connected discovery (Task 10), relay-as-percent with `Aus`→0 (Task 5), single log entity with attributes (Task 10), reauth (Task 8), uv + ruff + pytest (Tasks 1, 11), CI (Task 11), repo migration in place (Task 1), v2 diagram preserved in the design doc appendix (not implemented, by design).
- **Placeholders:** the only intentional stub is the Task 2 `client.py` placeholder, replaced fully in Task 3 — noted explicitly.
- **Type consistency:** `SorelData.sensors`/`relays` are `dict[int, ...]`; `get_all` populates them by int id; entities look up by `self._id` (int). `_clean_sensor` returns `float | None`; `get_all` skips `None`. Coordinator `_logged_in` flag consistent across tasks.
