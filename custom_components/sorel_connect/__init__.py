"""The Sorel Connect integration."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api.client import SorelConnectClient
from .const import (
    CONF_AREA,
    CONF_EMAIL,
    CONF_NAME,
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
    # The HA shared session uses DummyCookieJar which discards cookies, so the
    # nabto-session cookie set by login() would never be sent to data endpoints.
    # A dedicated session with a real cookie jar is required.
    session = aiohttp.ClientSession()
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
    entry.async_on_unload(session.close)

    # Apply user-supplied device name and area to the device registry entry.
    device_name = entry.data.get(CONF_NAME) or entry.title
    area_id = entry.data.get(CONF_AREA)
    dev_registry = dr.async_get(hass)
    device = dev_registry.async_get_device(identifiers={(DOMAIN, "sorel_connect")})
    if device is not None:
        dev_registry.async_update_device(
            device.id,
            name=device_name,
            area_id=area_id,
        )

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
