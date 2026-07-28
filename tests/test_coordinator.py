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
