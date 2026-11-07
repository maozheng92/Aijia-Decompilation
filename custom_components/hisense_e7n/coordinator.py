"""Push-driven coordinator wrapping the VIDAA MQTT client."""

from __future__ import annotations

import logging

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .power import normalize_power_on_entity, power_on_service
from .tv_client import HisenseTvClient, TvState

_LOGGER = logging.getLogger(__name__)


class HisenseTvCoordinator(DataUpdateCoordinator[TvState]):
    """Expose TV state to entities. Updates come from MQTT, not polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HisenseTvClient,
        name: str,
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
        self.device_name = name
        self.power_on_button = normalize_power_on_entity(power_on_button)
        client.add_listener(self._on_client_state)

    @property
    def can_power_on(self) -> bool:
        return bool(self.power_on_button or self.client.tv_mac or self.client.ble)

    @callback
    def _on_client_state(self, state: TvState) -> None:
        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, state)

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
        button = self.power_on_button
        if button:
            domain, service = power_on_service(button)
            _LOGGER.info("Powering on TV by calling %s.%s on %s", domain, service, button)
            try:
                await self.hass.services.async_call(
                    domain,
                    service,
                    {ATTR_ENTITY_ID: button},
                    blocking=True,
                )
            except HomeAssistantError:
                _LOGGER.exception("Power-on entity %s failed", button)
                return
            await self.client.async_wait_for_broker()
            return
        await self.client.async_turn_on()
