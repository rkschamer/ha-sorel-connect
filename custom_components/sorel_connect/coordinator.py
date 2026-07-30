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
            self._logged_in = False
            raise UpdateFailed(str(err)) from err

    async def _login(self) -> None:
        try:
            await self._client.login()
            self._logged_in = True
        except SorelAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SorelConnectionError as err:
            raise UpdateFailed(str(err)) from err
