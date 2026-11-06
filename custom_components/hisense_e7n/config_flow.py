"""Config flow for Hisense E7N Pro."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PORT
from homeassistant.core import callback

try:
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # pragma: no cover - HA < 2024.4
    from homeassistant.data_entry_flow import FlowResult as ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .certs_util import ensure_cert_pair
from .const import (
    AUTH_MODES,
    CONF_AUTH_MODE,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_CLIENT_UUID,
    DEFAULT_AUTH_MODE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)
from .credentials import random_client_uuid
from .tv_client import HisenseTvClient

STEP_USER_DATA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(TextSelectorConfig(type="text")),
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_MAC): TextSelector(TextSelectorConfig(type="text")),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_AUTH_MODE, default=DEFAULT_AUTH_MODE): SelectSelector(
            SelectSelectorConfig(
                options=AUTH_MODES,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_CLIENT_CERT): str,
        vol.Optional(CONF_CLIENT_KEY): str,
    }
)


class HisenseE7NConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hisense E7N Pro."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: HisenseTvClient | None = None
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            uuid = random_client_uuid()
            certfile = (user_input.get(CONF_CLIENT_CERT) or "").strip() or None
            keyfile = (user_input.get(CONF_CLIENT_KEY) or "").strip() or None
            if not certfile or not keyfile:
                cert_dir = Path(self.hass.config.config_dir) / "hisense_e7n" / "setup"
                certfile, keyfile = await self.hass.async_add_executor_job(
                    ensure_cert_pair, cert_dir
                )

            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()

            client = HisenseTvClient(
                host,
                port=port,
                uuid=uuid,
                tv_mac=(user_input.get(CONF_MAC) or "").strip() or None,
                auth_mode=user_input.get(CONF_AUTH_MODE, DEFAULT_AUTH_MODE),
                certfile=certfile,
                keyfile=keyfile,
                loop=self.hass.loop,
            )
            try:
                await client.async_connect()
            except ConnectionError:
                errors["base"] = "cannot_connect"
            else:
                self._client = client
                self._data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_MAC: (user_input.get(CONF_MAC) or "").strip(),
                    CONF_NAME: user_input.get(CONF_NAME) or DEFAULT_NAME,
                    CONF_AUTH_MODE: user_input.get(CONF_AUTH_MODE, DEFAULT_AUTH_MODE),
                    CONF_CLIENT_UUID: uuid,
                    CONF_CLIENT_CERT: certfile,
                    CONF_CLIENT_KEY: keyfile,
                }
                await client.async_pair()
                return await self.async_step_pin()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA,
            errors=errors,
        )

    async def async_step_pin(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        client = self._client
        if client is None:
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            pin = (user_input.get("pin") or "").strip()
            if pin:
                try:
                    await client.async_submit_pin(pin)
                except TimeoutError:
                    errors["base"] = "invalid_pin"
            if not errors:
                await client.async_disconnect()
                return self.async_create_entry(
                    title=self._data.get(CONF_NAME) or DEFAULT_NAME,
                    data=self._data,
                )

        already = client.state.already_paired and not client.state.needs_pin
        hint = (
            "No PIN dialog was reported; submit with an empty PIN if the TV did not pop up a code."
            if already
            else "Enter the 4-digit code shown on the TV."
        )
        return self.async_show_form(
            step_id="pin",
            data_schema=vol.Schema({vol.Optional("pin"): str}),
            errors=errors,
            description_placeholders={"hint": hint},
        )

    def async_remove(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            client.disconnect_blocking()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        return HisenseE7NOptionsFlow(config_entry)


class HisenseE7NOptionsFlow(config_entries.OptionsFlow):
    """Tune host / MAC / port without re-pairing."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        if config_entry is not None:
            self._config_entry = config_entry

    def _entry(self) -> config_entries.ConfigEntry:
        return getattr(self, "_config_entry", None) or self.config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = {**self._entry().data, **self._entry().options}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_MAC, default=data.get(CONF_MAC, "")): str,
                vol.Optional(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
