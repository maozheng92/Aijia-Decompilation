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
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .ble_hid import discovered_ble_addresses, normalize_ble_address
from .certs_util import resolve_cert_candidates
from .const import (
    AUTH_MODES,
    CONF_AUTH_MODE,
    CONF_BLE_ADDRESS,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_CLIENT_UUID,
    CONF_POWER_ON_BUTTON,
    CONF_USE_SSL,
    DEFAULT_AUTH_MODE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)
from .credentials import prefer_tv_mac_uuid
from .power import POWER_ON_DOMAINS, normalize_power_on_entity
from .tv_client import HisenseTvClient, classify_connect_error

POWER_ON_BUTTON_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=list(POWER_ON_DOMAINS), multiple=False)
)

STEP_USER_DATA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(TextSelectorConfig(type="text")),
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_POWER_ON_BUTTON): POWER_ON_BUTTON_SELECTOR,
        vol.Optional(CONF_MAC): TextSelector(TextSelectorConfig(type="text")),
        vol.Optional(CONF_BLE_ADDRESS): TextSelector(TextSelectorConfig(type="text")),
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            uuid = prefer_tv_mac_uuid(None, user_input.get(CONF_MAC))
            certfile = (user_input.get(CONF_CLIENT_CERT) or "").strip() or None
            keyfile = (user_input.get(CONF_CLIENT_KEY) or "").strip() or None
            cert_dir = Path(self.hass.config.config_dir) / "hisense_e7n" / "setup"
            search_roots = [
                Path(self.hass.config.config_dir),
                Path(__file__).resolve().parents[2],
            ]
            cert_pairs = await self.hass.async_add_executor_job(
                resolve_cert_candidates,
                cert_dir,
                certfile,
                keyfile,
                search_roots,
            )
            primary_cert, primary_key = cert_pairs[0] if cert_pairs else (certfile, keyfile)

            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()

            client = HisenseTvClient(
                host,
                port=port,
                uuid=uuid,
                tv_mac=(user_input.get(CONF_MAC) or "").strip() or None,
                auth_mode=user_input.get(CONF_AUTH_MODE, DEFAULT_AUTH_MODE),
                certfile=primary_cert,
                keyfile=primary_key,
                cert_pairs=cert_pairs,
                loop=self.hass.loop,
            )
            self._client = client
            ble_address = None
            raw_ble = (user_input.get(CONF_BLE_ADDRESS) or "").strip()
            if raw_ble:
                try:
                    ble_address = normalize_ble_address(raw_ble)
                except ValueError:
                    errors[CONF_BLE_ADDRESS] = "cannot_connect_ble"
            ble_ok = False
            if ble_address and CONF_BLE_ADDRESS not in errors:
                try:
                    await client.async_connect_ble(self.hass, ble_address)
                    ble_ok = True
                except Exception:  # noqa: BLE001
                    errors[CONF_BLE_ADDRESS] = "cannot_connect_ble"
            mqtt_ok = False
            try:
                await client.async_connect()
                mqtt_ok = True
            except ConnectionError as err:
                if not ble_ok:
                    errors["base"] = classify_connect_error(str(err))
            if mqtt_ok:
                try:
                    await client.async_pair()
                except Exception:  # noqa: BLE001 — announce is best-effort; MQTT already succeeded
                    pass
            if not errors:
                data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_MAC: (user_input.get(CONF_MAC) or "").strip(),
                    CONF_BLE_ADDRESS: ble_address or "",
                    CONF_POWER_ON_BUTTON: normalize_power_on_entity(
                        user_input.get(CONF_POWER_ON_BUTTON)
                    )
                    or "",
                    CONF_NAME: user_input.get(CONF_NAME) or DEFAULT_NAME,
                    CONF_AUTH_MODE: user_input.get(CONF_AUTH_MODE, DEFAULT_AUTH_MODE),
                    CONF_CLIENT_UUID: uuid,
                    CONF_CLIENT_CERT: client.certfile or primary_cert,
                    CONF_CLIENT_KEY: client.keyfile or primary_key,
                    CONF_USE_SSL: True if client.use_ssl is None else client.use_ssl,
                }
                await client.async_disconnect()
                self._client = None
                return self.async_create_entry(
                    title=data.get(CONF_NAME) or DEFAULT_NAME,
                    data=data,
                )
            await client.async_disconnect()
            self._client = None

        suggested: dict[str, Any] = dict(user_input or {})
        found = discovered_ble_addresses(self.hass)
        if found and not (suggested.get(CONF_BLE_ADDRESS) or "").strip():
            suggested[CONF_BLE_ADDRESS] = found[0]
        schema = STEP_USER_DATA
        if suggested:
            schema = self.add_suggested_values_to_schema(STEP_USER_DATA, suggested)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
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
    """Tune host, BLE address, power-on button, and MAC without re-pairing."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        if config_entry is not None:
            self._config_entry = config_entry

    def _entry(self) -> config_entries.ConfigEntry:
        return getattr(self, "_config_entry", None) or self.config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        data = {**self._entry().data, **self._entry().options}
        errors: dict[str, str] = {}
        if user_input is not None:
            if CONF_POWER_ON_BUTTON in user_input:
                user_input[CONF_POWER_ON_BUTTON] = (
                    normalize_power_on_entity(user_input.get(CONF_POWER_ON_BUTTON)) or ""
                )
            else:
                user_input[CONF_POWER_ON_BUTTON] = (
                    normalize_power_on_entity(data.get(CONF_POWER_ON_BUTTON)) or ""
                )
            raw_ble = (user_input.get(CONF_BLE_ADDRESS) or "").strip()
            if raw_ble:
                try:
                    user_input[CONF_BLE_ADDRESS] = normalize_ble_address(raw_ble)
                except ValueError:
                    errors[CONF_BLE_ADDRESS] = "cannot_connect_ble"
            else:
                user_input[CONF_BLE_ADDRESS] = ""
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_POWER_ON_BUTTON): POWER_ON_BUTTON_SELECTOR,
                vol.Optional(CONF_MAC, default=data.get(CONF_MAC, "")): str,
                vol.Optional(CONF_BLE_ADDRESS, default=data.get(CONF_BLE_ADDRESS, "")): str,
                vol.Optional(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): str,
            }
        )
        suggested = dict(data)
        if user_input:
            suggested.update(user_input)
        if not normalize_power_on_entity(suggested.get(CONF_POWER_ON_BUTTON)):
            suggested.pop(CONF_POWER_ON_BUTTON, None)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )
