"""Save a TV frame into Home Assistant's Image media source."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

IMAGE_UPLOAD_DOMAIN = "image_upload"
_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"


def image_for_upload(image: bytes) -> tuple[bytes, str]:
    """Return bytes the Image source accepts, plus a content type."""
    if image.startswith(_JPEG):
        return image, "image/jpeg"
    if image.startswith(_PNG):
        return image, "image/png"
    if image.startswith((b"GIF87a", b"GIF89a")):
        return image, "image/gif"
    return _convert_to_jpeg(image), "image/jpeg"


def _convert_to_jpeg(image: bytes) -> bytes:
    try:
        from PIL import Image
    except ImportError as err:
        raise RuntimeError("截屏不是 jpeg/png/gif，无法放进 Image 媒体源") from err
    try:
        with Image.open(BytesIO(image)) as img:
            out = BytesIO()
            img.convert("RGB").save(out, format="JPEG")
    except Exception as err:
        raise RuntimeError("截屏图片无法识别") from err
    payload = out.getvalue()
    if not payload.startswith(_JPEG):
        raise RuntimeError("截屏图片无法识别")
    return payload


def _file_field(name: str, filename: str, file: BytesIO, content_type: str, headers: dict):
    from aiohttp.web_request import FileField

    return FileField(name, filename, file, content_type, headers)


def _record_path(hass: Any, entry_id: str) -> Path:
    return Path(hass.config.path("hisense_e7n", entry_id, "last_screenshot.json"))


def _read_media_id(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    media_id = data.get("id") if isinstance(data, dict) else None
    return str(media_id) if media_id else None


def _write_media_id(path: Path, media_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": media_id}), encoding="utf-8")


async def async_save_screenshot(
    hass: Any,
    entry_id: str,
    image: bytes,
    filename: str,
) -> str:
    """Register one JPEG/PNG/GIF in the Image media source and return its id.

    The previous screenshot for this config entry is removed, so the Image
    source keeps the latest frame.
    """
    collection = hass.data.get(IMAGE_UPLOAD_DOMAIN)
    if collection is None:
        raise RuntimeError(
            "Home Assistant 没有启用 Image 媒体源。请保留 default_config，或在配置里加上 image_upload。"
        )
    payload, content_type = image_for_upload(image)
    record = _record_path(hass, entry_id)
    previous = await hass.async_add_executor_job(_read_media_id, record)
    field = _file_field("file", filename, BytesIO(payload), content_type, {})
    item = await collection.async_create_item({"file": field})
    media_id = item.get("id") if isinstance(item, dict) else None
    if not media_id:
        raise RuntimeError("Image 媒体源没有返回图片 id")
    media_id = str(media_id)
    await hass.async_add_executor_job(_write_media_id, record, media_id)
    stored = getattr(collection, "data", {})
    if previous and previous != media_id and previous in stored:
        await collection.async_delete_item(previous)
    return media_id
