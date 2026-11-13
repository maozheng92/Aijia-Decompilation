"""Keep the latest TV frame for the Image media source.

The media browser tile named Image lists Home Assistant image entities.
Image upload is a different tile and is not used.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

_JPEG = b"\xff\xd8\xff"
_UPLOAD_RECORD = "last_screenshot.json"
_SCREENSHOT_FILE = "screenshot.jpg"


def image_for_upload(image: bytes) -> tuple[bytes, str]:
    """Return JPEG bytes for the image entity."""
    if image.startswith(_JPEG):
        return image, "image/jpeg"
    return _convert_to_jpeg(image), "image/jpeg"


def _convert_to_jpeg(image: bytes) -> bytes:
    try:
        from PIL import Image
    except ImportError as err:
        raise RuntimeError("截屏不是 jpeg，无法放进 Image 媒体源") from err
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


def screenshot_path(config_path, entry_id: str) -> Path:
    return Path(config_path("hisense_e7n", entry_id, _SCREENSHOT_FILE))


def upload_record_path(config_path, entry_id: str) -> Path:
    return Path(config_path("hisense_e7n", entry_id, _UPLOAD_RECORD))


def write_screenshot(path: Path, image: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".jpg.tmp")
    temporary.write_bytes(image)
    temporary.replace(path)


def read_screenshot(path: Path) -> bytes | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    return data or None


def _read_media_id(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    media_id = data.get("id") if isinstance(data, dict) else None
    return str(media_id) if media_id else None


async def async_remove_uploaded_copy(hass: Any, entry_id: str) -> None:
    """Drop a frame that an older version put in Image upload."""
    path = upload_record_path(hass.config.path, entry_id)
    media_id = await hass.async_add_executor_job(_read_media_id, path)
    if not media_id:
        return
    collection = hass.data.get("image_upload")
    if collection is None:
        return
    if media_id in getattr(collection, "data", {}):
        await collection.async_delete_item(media_id)
    await hass.async_add_executor_job(path.unlink, True)
