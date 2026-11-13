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

from .certs_util import resolve_cert_candidates
from .const import (
    AUTH_MODES,
    CONF_AUTH_MODE,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_CLIENT_UUID,
    CONF_CUSTOM_SOURCES,
    CONF_CUSTOM_SOURCES_TEXT,
    CONF_POWER_ON_BUTTON,
    CONF_POWER_ON_COMMAND,
    CONF_POWER_ON_DEVICE,
    CONF_POWER_ON_MODE,
    CONF_POWER_ON_REMOTE,
    CONF_SOURCE_KEY_DELAY,
    CONF_USE_SSL,
    DEFAULT_AUTH_MODE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_POWER_ON_COMMAND,
    DEFAULT_SOURCE_KEY_DELAY,
    DOMAIN,
    POWER_ON_MODE_BUTTON,
)
from .credentials import random_client_uuid
from .custom_sources import (
    normalize_custom_sources,
    serialize_custom_sources,
)
from .power import (
    POWER_ON_DOMAINS,
    POWER_ON_MODES,
    clean_power_on_fields,
    infer_power_on_mode,
    normalize_power_on_entity,
    power_on_form_errors,
)
from .tv_client import HisenseTvClient, classify_connect_error

POWER_ON_BUTTON_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=list(POWER_ON_DOMAINS), multiple=False)
)
POWER_ON_REMOTE_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["remote"], multiple=False)
)
POWER_ON_MODE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=list(POWER_ON_MODES),
        mode=SelectSelectorMode.DROPDOWN,
        translation_key="power_on_mode",
    )
)

def _power_on_fields() -> dict[Any, Any]:
    """Fresh markers. The same vol.Optional object must not be reused across schemas."""
    return {
        vol.Optional(CONF_POWER_ON_MODE, default=POWER_ON_MODE_BUTTON): POWER_ON_MODE_SELECTOR,
        vol.Optional(CONF_POWER_ON_BUTTON): POWER_ON_BUTTON_SELECTOR,
        vol.Optional(CONF_POWER_ON_REMOTE): POWER_ON_REMOTE_SELECTOR,
        vol.Optional(CONF_POWER_ON_COMMAND, default=DEFAULT_POWER_ON_COMMAND): TextSelector(
            TextSelectorConfig(type="text")
        ),
        vol.Optional(CONF_POWER_ON_DEVICE): TextSelector(TextSelectorConfig(type="text")),
    }


def _user_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST): TextSelector(TextSelectorConfig(type="text")),
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            **_power_on_fields(),
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            form_errors = power_on_form_errors(user_input)
            if form_errors:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self.add_suggested_values_to_schema(_user_schema(), user_input),
                    errors=form_errors,
                )
            user_input = clean_power_on_fields(user_input)
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            uuid = random_client_uuid()
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
            mqtt_ok = False
            try:
                await client.async_connect()
                mqtt_ok = True
            except ConnectionError as err:
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
                    CONF_POWER_ON_MODE: user_input.get(CONF_POWER_ON_MODE, POWER_ON_MODE_BUTTON),
                    CONF_POWER_ON_BUTTON: user_input.get(CONF_POWER_ON_BUTTON) or "",
                    CONF_POWER_ON_REMOTE: user_input.get(CONF_POWER_ON_REMOTE) or "",
                    CONF_POWER_ON_COMMAND: user_input.get(CONF_POWER_ON_COMMAND)
                    or DEFAULT_POWER_ON_COMMAND,
                    CONF_POWER_ON_DEVICE: user_input.get(CONF_POWER_ON_DEVICE) or "",
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

        schema = _user_schema()
        if user_input:
            schema = self.add_suggested_values_to_schema(schema, user_input)
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
    """Tune host, power-on method, and MAC without re-pairing."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        if config_entry is not None:
            self._config_entry = config_entry

    def _entry(self) -> config_entries.ConfigEntry:
        return getattr(self, "_config_entry", None) or self.config_entry

    def _options_schema(self, data: dict[str, Any]) -> vol.Schema:
        delay = data.get(CONF_SOURCE_KEY_DELAY, DEFAULT_SOURCE_KEY_DELAY)
        try:
            delay_default = float(delay)
        except (TypeError, ValueError):
            delay_default = DEFAULT_SOURCE_KEY_DELAY
        sources_text = data.get(CONF_CUSTOM_SOURCES_TEXT)
        if sources_text is None:
            try:
                sources_text = serialize_custom_sources(
                    normalize_custom_sources(data.get(CONF_CUSTOM_SOURCES))
                )
            except ValueError:
                sources_text = ""
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                **_power_on_fields(),
                vol.Optional(CONF_MAC, default=data.get(CONF_MAC, "")): str,
                vol.Optional(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Optional(
                    CONF_CUSTOM_SOURCES_TEXT, default=sources_text or ""
                ): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Optional(
                    CONF_SOURCE_KEY_DELAY, default=delay_default
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=5)),
            }
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        data = {**self._entry().data, **self._entry().options}
        if user_input is not None:
            merged = {**data, **user_input}
            form_errors = power_on_form_errors(merged)
            try:
                custom_sources = normalize_custom_sources(
                    merged.get(CONF_CUSTOM_SOURCES_TEXT)
                )
            except ValueError:
                form_errors[CONF_CUSTOM_SOURCES_TEXT] = "invalid_custom_sources"
            if form_errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self.add_suggested_values_to_schema(
                        self._options_schema(data), merged
                    ),
                    errors=form_errors,
                )
            cleaned = clean_power_on_fields(merged)
            try:
                delay = float(
                    cleaned.get(CONF_SOURCE_KEY_DELAY, DEFAULT_SOURCE_KEY_DELAY)
                )
            except (TypeError, ValueError):
                delay = DEFAULT_SOURCE_KEY_DELAY
            delay = max(0.0, min(5.0, delay))
            return self.async_create_entry(
                title="",
                data={
                    CONF_HOST: str(cleaned.get(CONF_HOST, "")).strip(),
                    CONF_PORT: int(cleaned.get(CONF_PORT, DEFAULT_PORT)),
                    CONF_MAC: (cleaned.get(CONF_MAC) or "").strip(),
                    CONF_NAME: cleaned.get(CONF_NAME) or DEFAULT_NAME,
                    CONF_POWER_ON_MODE: cleaned[CONF_POWER_ON_MODE],
                    CONF_POWER_ON_BUTTON: cleaned.get(CONF_POWER_ON_BUTTON) or "",
                    CONF_POWER_ON_REMOTE: cleaned.get(CONF_POWER_ON_REMOTE) or "",
                    CONF_POWER_ON_COMMAND: cleaned.get(CONF_POWER_ON_COMMAND)
                    or DEFAULT_POWER_ON_COMMAND,
                    CONF_POWER_ON_DEVICE: cleaned.get(CONF_POWER_ON_DEVICE) or "",
                    CONF_CUSTOM_SOURCES: custom_sources,
                    CONF_SOURCE_KEY_DELAY: delay,
                },
            )

        schema = self._options_schema(data)
        suggested = dict(data)
        if user_input:
            suggested.update(user_input)
        if not normalize_power_on_entity(suggested.get(CONF_POWER_ON_BUTTON)):
            suggested.pop(CONF_POWER_ON_BUTTON, None)
        if not normalize_power_on_entity(suggested.get(CONF_POWER_ON_REMOTE)):
            suggested.pop(CONF_POWER_ON_REMOTE, None)
        suggested[CONF_POWER_ON_MODE] = infer_power_on_mode(
            suggested.get(CONF_POWER_ON_MODE),
            suggested.get(CONF_POWER_ON_BUTTON),
            suggested.get(CONF_POWER_ON_REMOTE),
            suggested.get(CONF_MAC),
        )
        try:
            suggested[CONF_CUSTOM_SOURCES_TEXT] = serialize_custom_sources(
                normalize_custom_sources(suggested.get(CONF_CUSTOM_SOURCES))
            )
        except ValueError:
            suggested[CONF_CUSTOM_SOURCES_TEXT] = str(
                suggested.get(CONF_CUSTOM_SOURCES_TEXT) or ""
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )
