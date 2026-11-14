"""Push-driven coordinator wrapping the VIDAA MQTT client."""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CONTROL_USERNAME,
    CONF_REFRESH_TOKEN,
    DEFAULT_POWER_ON_COMMAND,
    DEFAULT_SOURCE_KEY_DELAY,
    DOMAIN,
    POWER_ON_MODE_WOL,
)
from .custom_sources import normalize_custom_sources
from .power import infer_power_on_mode, normalize_power_on_entity, power_on_call
from .tv_client import HisenseTvClient, TvState

_LOGGER = logging.getLogger(__name__)


class HisenseTvCoordinator(DataUpdateCoordinator[TvState]):
    """Expose TV state to entities. Updates come from MQTT, not polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HisenseTvClient,
        name: str,
        entry: ConfigEntry | None = None,
        *,
        power_on_button: str | None = None,
    ) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=f"{DOMAIN}_{name}",
            update_interval=None,
        )
        self.client = client
        self.config_entry = entry
        self.device_name = name
        self.power_on_button = normalize_power_on_entity(power_on_button)
        self.power_on_mode = POWER_ON_MODE_WOL
        self.power_on_remote: str | None = None
        self.power_on_command = DEFAULT_POWER_ON_COMMAND
        self.power_on_device = ""
        self.custom_sources: list[dict] = []
        self.source_key_delay = DEFAULT_SOURCE_KEY_DELAY
        self._pin_notified = False
        client.add_listener(self._on_client_state)

    def configure_power_on(
        self,
        *,
        mode: str | None,
        button: str | None,
        remote: str | None,
        command: str | None,
        device: str | None,
        mac: str | None,
    ) -> None:
        """Store this TV's wake method. Each config entry has its own."""
        self.power_on_button = normalize_power_on_entity(button)
        self.power_on_remote = normalize_power_on_entity(remote)
        self.power_on_command = (command or "").strip() or DEFAULT_POWER_ON_COMMAND
        self.power_on_device = (device or "").strip()
        self.power_on_mode = infer_power_on_mode(mode, button, remote, mac)

    def configure_custom_sources(
        self,
        sources: object | None,
        *,
        delay: float | None = None,
    ) -> None:
        """Store user-defined inputs and the pause between remoter keys."""
        try:
            self.custom_sources = normalize_custom_sources(sources)
        except ValueError:
            _LOGGER.warning("Ignoring invalid custom sources", exc_info=True)
            self.custom_sources = []
        try:
            wait = DEFAULT_SOURCE_KEY_DELAY if delay is None else float(delay)
        except (TypeError, ValueError):
            wait = DEFAULT_SOURCE_KEY_DELAY
        self.source_key_delay = max(0.0, min(5.0, wait))

    @property
    def can_power_on(self) -> bool:
        if self.power_on_mode == POWER_ON_MODE_WOL:
            return bool(self.client.tv_mac)
        return power_on_call(
            self.power_on_mode,
            self.power_on_button,
            self.power_on_remote,
            self.power_on_command,
            self.power_on_device,
            self.client.tv_mac,
        ) is not None or bool(self.client.tv_mac)

    @callback
    def _on_client_state(self, state: TvState) -> None:
        self.hass.loop.call_soon_threadsafe(self._deliver_state, state)

    def _store_control_password(self, state: TvState) -> None:
        """Persist the access token and reload so the next login uses it."""
        entry = self.config_entry
        token = (state.access_token or "").strip()
        if entry is None or not token or entry.data.get(CONF_ACCESS_TOKEN) == token:
            return
        refresh = (state.refresh_token or "").strip() or entry.data.get(CONF_REFRESH_TOKEN, "")
        username = entry.data.get(CONF_CONTROL_USERNAME, "")
        creds = self.client.creds
        if creds is not None and creds.mode != "access_token" and creds.username:
            username = creds.username
        _LOGGER.info("TV issued a control password; reconnecting with it")
        self.hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: token,
                CONF_REFRESH_TOKEN: refresh,
                CONF_CONTROL_USERNAME: username,
            },
        )

    @callback
    def _deliver_state(self, state: TvState) -> None:
        self.async_set_updated_data(state)
        self._store_control_password(state)
        notification_id = f"{DOMAIN}_pair_{self.device_name}"
        if state.already_paired and not state.needs_pin:
            self._pin_notified = False
            persistent_notification.async_dismiss(self.hass, notification_id)
            return
        if (state.needs_pin or state.pin_requested) and not self._pin_notified:
            self._pin_notified = True
            persistent_notification.async_create(
                self.hass,
                (
                    "请马上看电视机画面，数字出现在画面上方或中间，大约一分钟后消失。"
                    "看到 4 位数字后，在开发者工具里调用 "
                    f"`{DOMAIN}.submit_code`，目标选这台电视的 Remote，"
                    "把数字填进 code。没有数字时，只按一次「请求授权码」按钮，"
                    "同时盯着电视。连按会把刚出现的数字换成新的。"
                ),
                title="海信电视需要授权",
                notification_id=notification_id,
            )

    async def _async_update_data(self) -> TvState:
        if self.client.state.available:
            try:
                await self.hass.async_add_executor_job(self.client.refresh_status)
            except Exception:  # noqa: BLE001
                self.logger.debug("Manual status refresh failed", exc_info=True)
        return self.client.state

    async def async_turn_on(self) -> None:
        """Power on via the configured button device, then wait for MQTT.

        Aijia cannot start a fully off E7N Pro: KEY_POWER needs the TV broker.
        Press (or turn on) the chosen HA entity instead, then reconnect.
        """
        if self.client.state.available:
            return
        if self.power_on_mode == POWER_ON_MODE_WOL:
            await self.client.async_turn_on()
            return
        call = power_on_call(
            self.power_on_mode,
            self.power_on_button,
            self.power_on_remote,
            self.power_on_command,
            self.power_on_device,
            self.client.tv_mac,
        )
        if call is None:
            await self.client.async_turn_on()
            return
        _LOGGER.info(
            "Powering on TV by calling %s.%s with %s",
            call.domain,
            call.service,
            call.data.get(ATTR_ENTITY_ID),
        )
        try:
            await self.hass.services.async_call(
                call.domain,
                call.service,
                call.data,
                blocking=True,
            )
        except HomeAssistantError:
            _LOGGER.exception("Power-on call %s.%s failed", call.domain, call.service)
            return
        await self.client.async_wait_for_broker()
