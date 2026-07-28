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


async def test_user_flow_success_creates_entry(hass, sample_data):
    result = await _start(hass)
    with (
        patch(
            "custom_components.sorel_connect.config_flow.SorelConnectClient.login",
            new=AsyncMock(),
        ),
        patch("custom_components.sorel_connect.aiohttp.ClientSession"),
        patch(
            "custom_components.sorel_connect.SorelConnectClient.login",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.sorel_connect.SorelConnectClient.get_all",
            new=AsyncMock(return_value=sample_data),
        ),
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
