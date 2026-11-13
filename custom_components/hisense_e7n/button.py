"""爱家电视遥控页上的实体按键."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import HisenseTvCoordinator
from .entity import HisenseTvEntity
from .keys import AIJIA_REMOTER_BUTTONS, KEY_POWER, RemoterButton


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HisenseTvCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        [HisenseTvRemoterButton(coordinator, entry, spec) for spec in AIJIA_REMOTER_BUTTONS]
    )


class HisenseTvRemoterButton(HisenseTvEntity, ButtonEntity):
    """One 爱家 remoter key as a Home Assistant button."""

    def __init__(
        self,
        coordinator: HisenseTvCoordinator,
        entry: ConfigEntry,
        spec: RemoterButton,
    ) -> None:
        super().__init__(coordinator, entry)
        self._spec = spec
        self._attr_unique_id = f"{entry.entry_id}_{spec.slug}"
        self._attr_translation_key = spec.translation_key
        self._attr_icon = spec.icon

    @property
    def available(self) -> bool:
        if self._spec.kind == "power":
            return super().available
        return self.coordinator.client.state.available

    async def async_press(self) -> None:
        client = self.coordinator.client
        kind = self._spec.kind
        if kind == "power":
            if not client.state.available:
                await self.coordinator.async_turn_on()
            else:
                await client.async_send_key(KEY_POWER)
            return
        if kind == "screenshot":
            await client.async_capture_screenshot()
            return
        if kind == "source":
            await client.async_open_source()
            return
        if kind == "smart_image":
            await client.async_push_smart_image()
            return
        await client.async_send_key(self._spec.payload or self._spec.slug)
