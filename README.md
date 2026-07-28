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
