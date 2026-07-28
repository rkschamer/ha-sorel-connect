# Sorel Connect — Home Assistant Custom Component (HACS)

**Date:** 2026-07-27
**Status:** Approved design, ready for implementation planning

## Goal

Migrate the existing AppDaemon `sorel-connect.py` app into a native Home
Assistant custom component that is installable via HACS. The component polls a
Sorel Connect heating controller over HTTP and exposes its sensors, relays, and
log as native HA entities. Any user should be able to install it from HACS,
configure it through the HA UI, and get entities automatically — with no MQTT
broker and no AppDaemon required.

### Key decisions

- **Native HA integration, no MQTT.** Entities are created directly via HA's
  entity registry using a `DataUpdateCoordinator`. MQTT is dropped entirely,
  removing the broker as a dependency.
- **Credentials via HA config flow**, stored in the config entry (not a
  `secrets.yaml`).
- **Poll interval is configurable** at setup and editable afterwards via an
  options flow.
- **HA-agnostic API client** with an injected `aiohttp.ClientSession`
  (dependency injection — the canonical HA pattern). Production passes HA's
  shared session; tests pass a mocked session.
- **Everything unit-tested.** uv for build/deps, ruff for lint + format,
  GitHub Actions CI.
- **Repo converted in place.** The AppDaemon app is removed (preserved in git
  history) and replaced by the custom component.

## Architecture

Two layers: a pure API client (no HA imports) and the HA integration layer.

```
custom_components/sorel_connect/
  __init__.py          # setup/unload entry; builds client + coordinator
  manifest.json        # HA integration metadata
  config_flow.py       # setup + options + reauth flows
  coordinator.py       # DataUpdateCoordinator, polls the client on interval
  sensor.py            # sensor platform; creates entities from coordinator data
  const.py             # domain, defaults, config keys
  api/                 # HA-AGNOSTIC client library (zero HA imports)
    __init__.py
    client.py          # SorelConnectClient: login, session, fetch counts+values
    models.py          # dataclasses: SorelData, SensorReading, RelayReading
    exceptions.py      # SorelAuthError, SorelConnectionError
```

- **`api/` layer** — pure `aiohttp`. Accepts a `ClientSession` in its
  constructor (never creates or imports HA). Handles login, JSONP/JSON parsing,
  cookie broadening, count discovery, and per-entity value fetching + cleaning.
  Fully unit-testable by mocking HTTP only.
- **HA layer** — `coordinator.py` calls the client on the configured interval;
  `sensor.py` builds entities from parsed data; `config_flow.py` handles
  setup/options/reauth; `__init__.py` wires them together with HA's shared
  session.

**Tooling:** uv (deps/build), ruff (lint + format), pytest (tests),
GitHub Actions (CI running ruff + pytest).

## API Client Layer (`api/`)

Pure Python + `aiohttp`, no HA imports. The `SorelConnectClient` is constructed
with an injected session:

```python
class SorelConnectClient:
    def __init__(
        self, session: aiohttp.ClientSession, base_url: str, email: str, password: str
    ): ...
```

### Methods

- **`async login()`** — GET `/nabto/hosted_plugin/login/execute?email=&password=`.
  Sets header `X-Requested-With: XMLHttpRequest`. Response is JSONP-like
  (`({...})`); extract the `{...}` body and check for a `session_key`. On
  success, broaden the `nabto-session` cookie from the login path to `/` so it
  is sent with subsequent data requests. Raises `SorelAuthError` on failure.
- **`async get_counts()`** — GET `sensors.json?id=0`, `relays.json?id=0`,
  `log.json?id=0`; each returns `{"val": "<count>"}`. Returns the number of
  sensors, relays, and log entries the controller reports (e.g. 13, 7, 3).
- **`async get_all()`** — the coordinator's main call. Fetches counts, then
  per-entity values via `sensors.json?id=N`, `relays.json?id=N`,
  `log.json?id=N`, parses/cleans them, and returns a `SorelData`.

### Response parsing

All data responses are `{"val": ...}` (sometimes with `"dt"`); the login
response is JSONP. A single helper extracts the JSON object between the first
`{` and last `}` (same approach as the current app) and decodes it.

### Parsing & cleaning (in the client, unit-tested)

- **Sensors** — value looks like `"41°C"`. Strip `°C`, parse to float. A value
  of `"--"` means the sensor is not connected → skip it entirely (not included
  in `SorelData`).
- **Relays** — value looks like `"0_0%"`, `"30_30%"`, or `"0_Aus"`. Strip the
  `N_` prefix and the `%`; map `"Aus"` → `0`. Result is a numeric percentage.
- **Logs** — text strings (e.g. `"Sonntag, 26.07.2026 13:44 Starkes Takten"`);
  kept as-is, newest first.

### Models (`models.py`)

```python
@dataclass
class SensorReading:
    id: int
    value: float


@dataclass
class RelayReading:
    id: int
    value: float  # percentage; "Aus" mapped to 0


@dataclass
class SorelData:
    sensors: dict[int, SensorReading]  # only connected sensors
    relays: dict[int, RelayReading]  # only connected relays
    logs: list[str]  # newest first
```

### Exceptions

- **`SorelAuthError`** — login rejected (no `session_key`).
- **`SorelConnectionError`** — network/HTTP failure.

Session expiry is handled by the coordinator re-calling `login()` on auth
failure (see below).

## Coordinator & Entities

### Coordinator (`coordinator.py`)

Subclass of `DataUpdateCoordinator[SorelData]`.

- `update_interval` is set from the config entry's poll interval; editing the
  interval via the options flow reloads the entry so the coordinator picks up
  the new value.
- `_async_update_data()`:
  1. If not logged in / session expired, call `client.login()`.
  2. Call `client.get_all()` and return the `SorelData`.
  3. On `SorelAuthError` → attempt one re-login and retry once. If it still
     fails, raise `ConfigEntryAuthFailed` (triggers HA reauth flow).
  4. On `SorelConnectionError` → raise `UpdateFailed` (HA marks entities
     unavailable and retries next interval).

### Entity discovery (first poll — "create only connected")

Done in `sensor.py`'s `async_setup_entry`: after the coordinator's first
refresh, create entities only for the sensor/relay IDs present in `SorelData`
(the connected ones), plus one log entity. A sensor/relay wired up later is
picked up on a reload.

All entities are `SensorEntity`:

- **Sensor** (per connected sensor): `device_class: temperature`,
  `native_unit_of_measurement: "°C"`, `state_class: measurement`. Name
  `"Sensor {id}"`, `unique_id` `sorel_connect_sensor_{id}`.
- **Relay** (per connected relay): `native_unit_of_measurement: "%"`,
  `state_class: measurement`, no `device_class`. Name `"Relay {id}"`,
  `unique_id` `sorel_connect_relay_{id}`.
- **Log** (one): state = newest entry; attributes `log_1..log_N` = all entries.
  Name `"Log"`, `unique_id` `sorel_connect_log`.

Each entity reads its value from `coordinator.data` by ID. If its ID disappears
from a later poll, it reports `None` (unavailable) rather than being removed.

### Device grouping

All entities share one `DeviceInfo` (identifier `sorel_connect`, manufacturer
`"Sorel"`, model `"SOREL Connect"`), grouping them under a single device — same
as today's MQTT device block.

## Config Flow & Reauth (`config_flow.py`)

### Setup flow (`async_step_user`)

- Form fields: **URL**, **email**, **password**, **poll interval** (seconds,
  default 300).
- On submit, build a client and call `login()`:
  - Success → create the config entry (title from URL host). Store
    URL/email/password + interval in entry data; the interval is also mirrored
    into `options` so it is editable later.
  - `SorelAuthError` → form error `invalid_auth`.
  - `SorelConnectionError` → form error `cannot_connect`.
- **Single-instance guard** via `async_set_unique_id` (based on URL host) to
  prevent adding the same controller twice.

### Options flow

Lets the user change the **poll interval** after setup without re-entering
credentials. On save, reload the entry so the coordinator picks up the new
interval.

### Reauth flow (`async_step_reauth` / `async_step_reauth_confirm`)

Triggered when the coordinator raises `ConfigEntryAuthFailed` (e.g. password
changed on the device). Prompts for a new password, re-validates via `login()`,
and updates the entry.

### Setup / unload (`__init__.py`)

- `async_setup_entry`: build the client with `async_get_clientsession(hass)`,
  create the coordinator, run the first refresh, forward to the `sensor`
  platform, and store the coordinator in `hass.data[DOMAIN][entry_id]`.
- `async_unload_entry`: unload the platform and pop the stored data. (No session
  to close — HA owns the shared session.)
- `async_reload_entry` on options update.

## Testing (pytest — everything covered)

- **Client tests (no HA)** — mock HTTP with `aioresponses`: login
  success/failure, cookie broadening, JSONP vs JSON parsing, count fetching,
  sensor cleaning (`°C` strip, `--` skip), relay cleaning (`N_` prefix, `%`,
  `Aus`→0), log parsing, connection errors → correct exceptions.
- **Coordinator tests** — mock client: successful update → `SorelData`; auth
  failure → one retry → `ConfigEntryAuthFailed`; connection error →
  `UpdateFailed`.
- **Config flow tests** — HA flow test helpers: happy path creates entry;
  `invalid_auth` / `cannot_connect` errors; single-instance abort; options flow
  updates interval; reauth flow.
- **Entity tests** — first-poll discovery creates only connected entities;
  sensor/relay/log attributes, units, device_class, device grouping; value
  disappears → unavailable.

Test dependencies (`pytest`, `pytest-homeassistant-custom-component`,
`aioresponses`) are managed via a uv dev dependency group.

## Tooling & Packaging

- **uv** — `pyproject.toml` for deps/build; dev dependency group for
  test/lint tools.
- **ruff** — lint + format, configured in `pyproject.toml`.
- **HACS metadata** — `hacs.json`; `manifest.json` (domain `sorel_connect`,
  version, `iot_class: local_polling`, dependencies); README with
  install/config instructions.
- **CI** — a `.github/workflows` GitHub Action running ruff + pytest on
  push/PR.

## Repository Migration

Convert this repo in place: remove the AppDaemon app and its config
(`apps/`, `dashboards/`, `appdaemon.yaml`, `secrets.yaml`, and AppDaemon-specific
files), preserved in git history, and replace with the custom component
structure above. The result is a clean single-purpose HACS repository.

## Appendix — v2: Hydraulic Scheme Diagram (deferred)

The Sorel Connect "Main View" renders a live hydraulic scheme. This is out of
scope for v1 but the following is preserved so v2 can implement it as an HA
`image`/`camera` entity.

### Endpoints (Main View)

- **`scheme.json?id=schemeId`** → `{"val": <N>}` — the scheme number. The
  background image is `gfx/sorel/S{N}.png` (observed `S49.png` for scheme 26 —
  note the returned val (26) and the image number (49) differ, so the mapping
  from scheme number to image must be confirmed against `sorel.js` / `config.js`
  during v2).
- **`state.json?id=sensorN`** → `{"val": "41°C"}` — per-sensor value for the
  Main View overlay.
- **`state.json?id=status`** → `{"val": "2026-07-27 15:47:16 OK"}` — controller
  status line.
- **`heat.json?id=0`** → `{"val": "0"}` — heat group data.

### Overlay assets

Pump/valve state is drawn with overlay images composited onto the scheme
background client-side, e.g. `gfx/sorel/pump_on.gif`, `gfx/sorel/ValveOn270.png`.

### Rendering logic

Positions and compositing are computed in `sorel.js` (client-side JavaScript;
~21 KB). The Main View polls scheme + status + heat + the sensor/relay
`state.json` endpoints every ~60s and overlays values/graphics at fixed
coordinates. v2 would replicate this compositing server-side (fetch background +
overlays, position values, produce a single image) and expose it as an
`image`/`camera` entity. The exact coordinate/overlay-selection logic must be
extracted from `sorel.js` when v2 is built.
