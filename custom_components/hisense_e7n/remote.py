"""Remote entity that sends VIDAA / 爱家 KEY_* codes."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import voluptuous as vol

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import HisenseTvCoordinator
from .entity import HisenseTvEntity
from .keys import KEY_POWER, aijia_send_commands, normalize_key


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HisenseTvCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([HisenseTvRemote(coordinator, entry)])
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "send_key",
        {vol.Required("key"): cv.string},
        "async_send_key_service",
    )


class HisenseTvRemote(HisenseTvEntity, RemoteEntity):
    """Send individual remote keys (works with Universal Remote Card)."""

    _attr_name = "Remote"
    _attr_icon = "mdi:remote"
    _attr_translation_key = "remote"

    def __init__(self, coordinator: HisenseTvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_remote"

    @property
    def is_on(self) -> bool:
        return (self.coordinator.data or self.coordinator.client.state).available

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_turn_off()

    async def async_send_key_service(self, key: str) -> None:
        await self.coordinator.client.async_send_key(normalize_key(key))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"commands": aijia_send_commands()}

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        repeats = int(kwargs.get("num_repeats") or 1)
        delay = float(kwargs.get("delay_secs") or 0.12)
        for raw in command:
            key = normalize_key(str(raw))
            for _ in range(max(1, repeats)):
                if key == KEY_POWER and not self.coordinator.client.state.available:
                    await self.coordinator.async_turn_on()
                else:
                    await self.coordinator.client.async_send_key(key)
                if delay:
                    await asyncio.sleep(delay)
