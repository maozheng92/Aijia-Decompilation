"""TV media player for Hisense E7N Pro."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import HisenseTvCoordinator
from .entity import HisenseTvEntity
from .keys import (
    KEY_CHANNELDOWN,
    KEY_CHANNELUP,
    KEY_PAUSE,
    KEY_PLAY,
    KEY_STOP,
    KEY_VOLUMEDOWN,
    KEY_VOLUMEUP,
)

SUPPORT = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.BROWSE_MEDIA
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HisenseTvCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([HisenseTvMediaPlayer(coordinator, entry)])
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "launch_app",
        {
            vol.Required("name"): cv.string,
            vol.Optional("url"): cv.string,
        },
        "async_launch_app_service",
    )


class HisenseTvMediaPlayer(HisenseTvEntity, MediaPlayerEntity):
    """One E7N Pro as a Home Assistant TV."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_name = None
    _attr_icon = "mdi:television"
    _attr_supported_features = SUPPORT
    _attr_translation_key = "tv"

    def __init__(self, coordinator: HisenseTvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_media_player"

    @property
    def state(self) -> MediaPlayerState:
        tv = self.coordinator.data or self.coordinator.client.state
        if not tv.available or not tv.power_on:
            return MediaPlayerState.OFF
        kind = (tv.statetype or "").lower()
        if "pause" in kind:
            return MediaPlayerState.PAUSED
        if kind in {"app", "video", "livetv", "play"}:
            return MediaPlayerState.PLAYING
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        volume = (self.coordinator.data or self.coordinator.client.state).volume
        if volume is None:
            return None
        return max(0.0, min(1.0, volume / 100.0))

    @property
    def is_volume_muted(self) -> bool:
        return (self.coordinator.data or self.coordinator.client.state).muted

    @property
    def media_title(self) -> str | None:
        return self.source

    @property
    def source(self) -> str | None:
        tv = self.coordinator.data or self.coordinator.client.state
        return tv.source_name

    @property
    def source_list(self) -> list[str] | None:
        tv = self.coordinator.data or self.coordinator.client.state
        names = [item["name"] for item in tv.sources if item.get("name")]
        for app in tv.apps:
            name = app.get("name") or app.get("appName")
            if name and name not in names:
                names.append(str(name))
        return names or None

    async def async_turn_on(self) -> None:
        await self.coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        await self.coordinator.client.async_turn_off()

    async def async_volume_up(self) -> None:
        await self.coordinator.client.async_send_key(KEY_VOLUMEUP)

    async def async_volume_down(self) -> None:
        await self.coordinator.client.async_send_key(KEY_VOLUMEDOWN)

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.client.async_set_volume(int(round(volume * 100)))

    async def async_mute_volume(self, mute: bool) -> None:
        tv = self.coordinator.client.state
        if tv.muted != mute:
            await self.coordinator.client.async_toggle_mute()

    async def async_media_play(self) -> None:
        await self.coordinator.client.async_send_key(KEY_PLAY)

    async def async_media_pause(self) -> None:
        await self.coordinator.client.async_send_key(KEY_PAUSE)

    async def async_media_stop(self) -> None:
        await self.coordinator.client.async_send_key(KEY_STOP)

    async def async_media_next_track(self) -> None:
        await self.coordinator.client.async_send_key(KEY_CHANNELUP)

    async def async_media_previous_track(self) -> None:
        await self.coordinator.client.async_send_key(KEY_CHANNELDOWN)

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        if media_content_id in (None, "root", "apps"):
            await self.coordinator.client.async_refresh_apps()
        tv = self.coordinator.data or self.coordinator.client.state
        if media_content_id in (None, "root"):
            return BrowseMedia(
                title=self.coordinator.device_name,
                media_class=MediaClass.DIRECTORY,
                media_content_id="root",
                media_content_type="root",
                can_play=False,
                can_expand=True,
                children=[
                    _folder("Sources", "sources"),
                    _folder("我的应用", "apps"),
                ],
            )
        if media_content_id == "sources":
            children = [
                BrowseMedia(
                    title=str(item.get("name") or item.get("id")),
                    media_class=MediaClass.CHANNEL,
                    media_content_id=f"source:{item.get('id')}",
                    media_content_type=MediaType.CHANNEL,
                    can_play=True,
                    can_expand=False,
                )
                for item in tv.sources
                if item.get("name") or item.get("id")
            ]
            return _folder("Sources", "sources", children)
        children = []
        for app in tv.apps:
            name = app.get("name")
            url = app.get("url") or app.get("app_id") or name
            if not name:
                continue
            children.append(
                BrowseMedia(
                    title=str(name),
                    media_class=MediaClass.APP,
                    media_content_id=f"app:{url}",
                    media_content_type=MediaType.APP,
                    can_play=True,
                    can_expand=False,
                    thumbnail=str(app["icon"]) if app.get("icon") else None,
                )
            )
        return _folder("我的应用", "apps", children)

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        tv = self.coordinator.client.state
        if media_type == MediaType.APP and not str(media_id).startswith("app:"):
            await self.coordinator.client.async_launch_app(media_id, kwargs.get("url"))
            return
        if media_type in {MediaType.CHANNEL, "channel"} and not str(media_id).startswith(
            ("source:", "app:")
        ):
            await self.coordinator.client.async_change_channel(media_id)
            return
        if media_id.startswith("source:"):
            source_id = media_id.split(":", 1)[1]
            for item in tv.sources:
                if str(item.get("id")) == source_id:
                    await self.coordinator.client.async_change_source(
                        item["id"], str(item.get("name") or source_id)
                    )
                    return
        if media_id.startswith("app:"):
            url = media_id.split(":", 1)[1]
            for app in tv.apps:
                app_url = app.get("url") or app.get("app_id") or ""
                name = app.get("name") or url
                if str(app_url) == url or str(name) == url or str(app.get("app_id") or "") == url:
                    await self.coordinator.client.async_launch_app(
                        str(name),
                        str(app_url) if app_url else None,
                        int(app.get("url_type") or 37),
                        int(app.get("store_type") or 0),
                    )
                    return
            await self.coordinator.client.async_launch_app(url, url)
            return
        await self.async_select_source(media_id)

    async def async_select_source(self, source: str) -> None:
        tv = self.coordinator.client.state
        for item in tv.sources:
            if item.get("name") == source:
                await self.coordinator.client.async_change_source(item["id"], source)
                return
        for app in tv.apps:
            name = app.get("name")
            if name == source:
                url = app.get("url") or app.get("app_id")
                await self.coordinator.client.async_launch_app(
                    str(name),
                    str(url) if url else None,
                    int(app.get("url_type") or 37),
                    int(app.get("store_type") or 0),
                )
                return
        await self.coordinator.client.async_launch_app(source)

    async def async_launch_app_service(self, name: str, url: str | None = None) -> None:
        await self.coordinator.client.async_launch_app(name, url)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tv = self.coordinator.client.state
        return {
            "statetype": tv.statetype,
            "auth_mode": tv.auth_mode,
            "source_id": tv.source_id,
            "power_on_mode": self.coordinator.power_on_mode,
            "apps": [str(app["name"]) for app in tv.apps if app.get("name")],
        }


def _folder(title: str, content_id: str, children: list[BrowseMedia] | None = None) -> BrowseMedia:
    return BrowseMedia(
        title=title,
        media_class=MediaClass.DIRECTORY,
        media_content_id=content_id,
        media_content_type=content_id,
        can_play=False,
        can_expand=True,
        children=children or [],
    )
