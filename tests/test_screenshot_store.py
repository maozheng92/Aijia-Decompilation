"""Screenshot bytes for the Image entity, without Home Assistant."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from conftest import load_proto


class _Collection:
    def __init__(self) -> None:
        self.data = {"old-id": {"id": "old-id"}}
        self.deleted: list[str] = []

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


def test_screenshot_file_roundtrip_and_webp_becomes_jpeg(tmp_path) -> None:
    store = load_proto("screenshot_store")
    payload, content_type = store.image_for_upload(_webp())
    assert content_type == "image/jpeg"
    assert payload.startswith(b"\xff\xd8\xff")

    path = store.screenshot_path(_Config(tmp_path).path, "entry-1")
    store.write_screenshot(path, payload)
    assert store.read_screenshot(path) == payload
    jpeg, kind = store.image_for_upload(_jpeg())
    assert kind == "image/jpeg"
    assert jpeg.startswith(b"\xff\xd8\xff")


def test_previous_image_upload_is_removed(tmp_path) -> None:
    store = load_proto("screenshot_store")
    collection = _Collection()
    hass = _Hass(tmp_path, collection)
    record = store.upload_record_path(hass.config.path, "entry-1")
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"id": "old-id"}), encoding="utf-8")

    asyncio.run(store.async_remove_uploaded_copy(hass, "entry-1"))

    assert collection.deleted == ["old-id"]
    assert not record.exists()


def test_screenshot_bytes_stay_on_the_client(proto_client, proto_credentials, monkeypatch) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    jpeg = _jpeg()

    class Shot:
        image = jpeg
        note = "正在使用：聚好看"

    monkeypatch.setattr(proto_client, "capture_screen", lambda host, **kwargs: Shot())
    client._creds = proto_credentials.generate_dynamic_credentials(
        "aa:bb:cc:dd:ee:ff", timestamp=1
    )
    assert client.capture_screenshot() == jpeg
    assert client.state.screenshot_image == jpeg
    assert client.state.screenshot_content_type == "image/jpeg"
    assert client.state.screenshot_note == "正在使用：聚好看"
