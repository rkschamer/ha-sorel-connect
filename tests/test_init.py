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
