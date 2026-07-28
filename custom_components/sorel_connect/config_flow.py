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


async def _validate(hass: HomeAssistant, url: str, email: str, password: str) -> None:
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
