"""Screenshot as an image entity, shown in the media browser's Image source."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import HisenseTvCoordinator
from .entity import HisenseTvEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HisenseTvCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([HisenseScreenshotImage(coordinator, entry)])


class HisenseScreenshotImage(HisenseTvEntity, ImageEntity):
    """Latest TV frame. The Image media source lists this entity."""

    _attr_content_type = "image/jpeg"
    _attr_icon = "mdi:monitor-screenshot"
    _attr_name = None
    _attr_translation_key = "screenshot"

    def __init__(self, coordinator: HisenseTvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_unique_id = f"{entry.entry_id}_screenshot"
        self._shown: bytes | None = None

    @property
    def available(self) -> bool:
        if self.coordinator.client.state.screenshot_image:
            return True
        return super().available

    async def async_image(self) -> bytes | None:
        return self.coordinator.client.state.screenshot_image

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._mark_current()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._mark_current()
        super()._handle_coordinator_update()

    def _mark_current(self) -> None:
        state = self.coordinator.data or self.coordinator.client.state
        image = state.screenshot_image
        if image is None or image is self._shown:
            return
        self._shown = image
        self._attr_content_type = state.screenshot_content_type or "image/jpeg"
        self._attr_image_last_updated = dt_util.utcnow()
        self.__dict__.pop("content_type", None)
        self.__dict__.pop("image_last_updated", None)
        self._cached_image = None
        update_token = getattr(self, "async_update_token", None)
        if update_token is not None:
            update_token()
