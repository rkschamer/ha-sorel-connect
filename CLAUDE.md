# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                        # install dependencies
uv run ruff check .            # lint
uv run ruff format --check .   # format check (CI enforces this too)
uv run ruff format .           # auto-format
uv run pytest                  # run all tests
uv run pytest tests/api/       # run a specific test directory
uv run pytest tests/test_sensor.py::test_name  # run a single test
```

## Architecture

This is a Home Assistant custom integration (`custom_components/sorel_connect`) that polls a Sorel Connect heating controller over HTTP and exposes its data as HA sensor entities.

**Data flow:**

```
SorelConnectClient (api/client.py)
  → SorelCoordinator (coordinator.py)    # HA DataUpdateCoordinator, owns poll interval
    → SorelSensorEntity / SorelRelayEntity / SorelLogEntity (sensor.py)
```

**Key design decisions:**

- `SorelConnectClient` is HA-agnostic and takes an injected `aiohttp.ClientSession`. This is intentional — it makes the client unit-testable without HA infrastructure.
- A **dedicated** `aiohttp.ClientSession` (with a real cookie jar) is created in `async_setup_entry`, not the HA shared session. The HA shared session uses `DummyCookieJar`, which would discard the `nabto-session` cookie set at login.
- The coordinator handles session expiry: if `get_all()` raises `SorelAuthError`, it re-logs in once and retries before raising `ConfigEntryAuthFailed`.
- The Sorel HTTP API returns data one value at a time via `sensors.json?id=N`, `relays.json?id=N`, `log.json?id=N`. `id=0` returns the count. `get_all()` fetches counts first, then all values.
- Sensor strings like `42°C` and relay strings like `0_30%`/`0_Aus`/`0_Ein` are parsed in `_clean_sensor` / `_clean_relay`. Sensors returning `--` are disconnected and excluded from entities.
- Entity count is determined at setup time from the first coordinator poll; no dynamic entity addition after that.

**Test infrastructure:**

- `tests/api/_fake.py` provides `FakeSession`, a lightweight fake for `aiohttp.ClientSession` that maps URLs to response bodies. Used instead of `aioresponses` because that library doesn't support the aiohttp version HA pins.
- `tests/conftest.py` provides `sample_data` and `mock_client` fixtures used across HA-level tests (coordinator, sensor, config flow).
- The `auto_enable_custom_integrations` autouse fixture (from `pytest-homeassistant-custom-component`) is required to load the integration in tests.
