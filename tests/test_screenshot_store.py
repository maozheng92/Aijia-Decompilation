"""Image media-source registration, without Home Assistant."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from conftest import load_proto


class _Field:
    def __init__(self, name, filename, file, content_type, headers):
        self.name = name
        self.filename = filename
        self.file = file
        self.content_type = content_type
        self.headers = headers


class _Collection:
    def __init__(self) -> None:
        self.data: dict[str, dict] = {}
        self.deleted: list[str] = []
        self._n = 0

    async def async_create_item(self, data: dict) -> dict:
        self._n += 1
        field = data["file"]
        item_id = f"img{self._n}"
        item = {
            "id": item_id,
            "name": field.filename,
            "content_type": field.content_type,
            "bytes": field.file.read(),
        }
        self.data[item_id] = item
        return item

    async def async_delete_item(self, item_id: str) -> None:
        self.deleted.append(item_id)
        self.data.pop(item_id, None)


class _Config:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, *parts: str) -> str:
        return str(self.root.joinpath(*parts))


class _Hass:
    def __init__(self, root: Path, collection: _Collection | None) -> None:
        self.config = _Config(root)
        self.data = {}
        if collection is not None:
            self.data["image_upload"] = collection

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _jpeg() -> bytes:
    out = BytesIO()
    Image.new("RGB", (2, 2), "red").save(out, format="JPEG")
    return out.getvalue()


def _webp() -> bytes:
    out = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(out, format="WEBP")
    return out.getvalue()


def test_image_upload_keeps_only_the_latest_frame(tmp_path, monkeypatch) -> None:
    store = load_proto("screenshot_store")
    monkeypatch.setattr(store, "_file_field", _Field)
    collection = _Collection()
    hass = _Hass(tmp_path, collection)

    first = asyncio.run(
        store.async_save_screenshot(hass, "entry-1", _jpeg(), "客厅 截屏.jpg")
    )
    second = asyncio.run(
        store.async_save_screenshot(hass, "entry-1", _webp(), "客厅 截屏.jpg")
    )

    assert first == "img1"
    assert second == "img2"
    assert collection.deleted == ["img1"]
    assert set(collection.data) == {"img2"}
    saved = collection.data["img2"]
    assert saved["name"] == "客厅 截屏.jpg"
    assert saved["content_type"] == "image/jpeg"
    assert saved["bytes"].startswith(b"\xff\xd8\xff")
    record = json.loads(
        (tmp_path / "hisense_e7n" / "entry-1" / "last_screenshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert record == {"id": "img2"}


def test_missing_image_source_is_reported(tmp_path) -> None:
    store = load_proto("screenshot_store")
    hass = _Hass(tmp_path, None)
    try:
        asyncio.run(store.async_save_screenshot(hass, "entry-1", _jpeg(), "截屏.jpg"))
    except RuntimeError as err:
        assert "Image" in str(err)
    else:
        raise AssertionError("expected a missing Image source error")
