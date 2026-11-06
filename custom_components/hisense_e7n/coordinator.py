"""Push-driven coordinator wrapping the VIDAA MQTT client."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .tv_client import HisenseTvClient, TvState


class HisenseTvCoordinator(DataUpdateCoordinator[TvState]):
    """Expose TV state to entities. Updates come from MQTT, not polling."""

    def __init__(self, hass: HomeAssistant, client: HisenseTvClient, name: str) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=f"{DOMAIN}_{name}",
            update_interval=None,
        )
        self.client = client
        self.device_name = name
        client.add_listener(self._on_client_state)

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
