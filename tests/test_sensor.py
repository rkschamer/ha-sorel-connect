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
    with (
        patch(
            "custom_components.sorel_connect.SorelConnectClient.login", new=AsyncMock()
        ),
        patch(
            "custom_components.sorel_connect.SorelConnectClient.get_all",
            new=AsyncMock(return_value=sample_data),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_creates_only_connected_sensors(hass, sample_data):
    # sample_data has sensors {1, 3}, relays {1}
    entry = await _setup(hass, sample_data)
    slug = entry.title.lower().replace(" ", "_")
    assert hass.states.get(f"sensor.{slug}_sensor_1") is not None
    assert hass.states.get(f"sensor.{slug}_sensor_3") is not None
    assert hass.states.get(f"sensor.{slug}_sensor_2") is None


async def test_sensor_state_and_unit(hass, sample_data):
    entry = await _setup(hass, sample_data)
    slug = entry.title.lower().replace(" ", "_")
    state = hass.states.get(f"sensor.{slug}_sensor_1")
    assert state.state == "42.0"
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.CELSIUS
    assert state.attributes["device_class"] == "temperature"


async def test_relay_state_and_unit(hass, sample_data):
    entry = await _setup(hass, sample_data)
    slug = entry.title.lower().replace(" ", "_")
    state = hass.states.get(f"sensor.{slug}_relay_1")
    assert state.state == "30.0"
    assert state.attributes["unit_of_measurement"] == "%"
    assert "device_class" not in state.attributes


async def test_log_entity_state_and_attributes(hass, sample_data):
    entry = await _setup(hass, sample_data)
    slug = entry.title.lower().replace(" ", "_")
    state = hass.states.get(f"sensor.{slug}_log")
    assert state.state == "newest"
    assert state.attributes["log_1"] == "newest"
    assert state.attributes["log_2"] == "middle"
    assert state.attributes["log_3"] == "oldest"
