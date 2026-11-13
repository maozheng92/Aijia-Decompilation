"""Local key channel used by 海信爱家 on the TV itself.

The app probes TCP 7778 and 7779 and posts the key name to
``http://<tv>:<port>/<KEY>..controller``. That request does not use the
MQTT session, so it still works when the TV never shows a pairing code.

信号源 and 识图 are voice texts on ``/..pushwechatvoice``. 截屏 starts
``com.android.wechathci`` via ``/..commonstarttvapp``; the picture is then
fetched from the TV's upload and saved by the integration.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

LOCAL_KEY_PORTS = (7778, 7779)
VOICE_PORTS = (7779, 7778)
SCREENSHOT_PORTS = (7779, 7778)
IMAGE_LOOKUP = "https://qrimageurl.hismarttv.com/v5/image/imageurl/by/id"
# Published by the official web remote as remoteMonitorCommander.
CAPTURE_PACKAGE = "com.android.wechathci"
CAPTURE_COMMAND = {
    "commandtype": "1",
    "action": "com.hisense.smartimages.UPLOAD_CAPTURE",
    "packagename": CAPTURE_PACKAGE,
    "uuid": "c49fbb20-df56-11f1-82d6-6d4823deee47",
    "packagenamesign": "bkot+cANu2aHQxujxER8Wg==",
}
_MAX_IMAGE = 12 * 1024 * 1024


def send_local_key(
    host: str,
    key: str,
    *,
    ports: tuple[int, ...] = LOCAL_KEY_PORTS,
    timeout: float = 2.0,
) -> int | None:
    """POST the key. Return the HTTP status, or None if no port answered."""
    name = key.strip()
    if not name or any(ch in name for ch in "/?#"):
        raise ValueError(f"invalid key: {key}")
    answered: int | None = None
    for port in ports:
        url = f"http://{host}:{port}/{name}..controller"
        for method in ("POST", "GET"):
            status = _request(url, method, timeout)
            if status is None:
                break
            answered = status
            if 200 <= status < 300:
                _LOGGER.info("TV accepted %s on port %s", name, port)
                return status
        # This port is not the key service. Try the other one.
    return answered


@dataclass(frozen=True)
class ScreenCapture:
    """One picture returned by the TV after UPLOAD_CAPTURE."""

    image: bytes
    note: str
    source_url: str


def push_voice(
    host: str,
    text: str,
    *,
    ports: tuple[int, ...] = VOICE_PORTS,
    timeout: float = 2.0,
) -> int | None:
    """Send a spoken command such as 信号源 or 识图. Return the HTTP status."""
    phrase = text.strip()
    if not phrase:
        raise ValueError("empty voice command")
    body = {"voice": phrase, "msgchannel": 1, "msgresource": 4, "msgtype": 6}
    answered: int | None = None
    for port in ports:
        url = f"http://{host}:{port}/..pushwechatvoice"
        result = _exchange(url, body, timeout)
        if result is None:
            continue
        answered = result[0]
        if 200 <= answered < 300:
            _LOGGER.info("TV accepted voice %s on port %s", phrase, port)
            return answered
    return answered


def capture_screen(
    host: str,
    *,
    ports: tuple[int, ...] = SCREENSHOT_PORTS,
    timeout: float = 2.0,
    retries: int = 12,
    first_delay: float = 0.5,
    interval: float = 1.0,
    pause: Callable[[float], None] = time.sleep,
) -> ScreenCapture:
    """Ask the TV to upload the current frame and download that picture."""
    session = f"voice_remote{time.strftime('%Y%m%d%H%M%S')}{random.randint(0, 999999):06d}"
    payload = dict(CAPTURE_COMMAND)
    payload["pushdata"] = json.dumps(
        {"mobilekey": session, "packagename": CAPTURE_PACKAGE},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    accepted = False
    for port in ports:
        result = _exchange(f"http://{host}:{port}/..commonstarttvapp", payload, timeout)
        if result is not None and 200 <= result[0] < 300:
            accepted = True
            break
    if not accepted:
        raise RuntimeError("电视没有接受截屏")
    pause(first_delay)
    for attempt in range(retries):
        if attempt:
            pause(interval)
        info = _lookup_capture(session, timeout)
        image_url = _image_url(info)
        if not image_url:
            continue
        image = _download(image_url, timeout)
        return ScreenCapture(image=image, note=_capture_note(info), source_url=image_url)
    raise RuntimeError("电视没有把画面传回来")


def _request(url: str, method: str, timeout: float) -> int | None:
    result = _exchange(url, {} if method == "POST" else None, timeout, method=method)
    return None if result is None else result[0]


def _exchange(
    url: str,
    payload: dict | None,
    timeout: float,
    *,
    method: str = "POST",
) -> tuple[int, bytes] | None:
    data = None
    headers = {"Connection": "close"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(_MAX_IMAGE + 1)
    except urllib.error.HTTPError as err:
        try:
            body = err.read(_MAX_IMAGE + 1)
        except Exception:  # noqa: BLE001
            body = b""
        return err.code, body
    except (TimeoutError, OSError, urllib.error.URLError):
        return None


def _lookup_capture(session: str, timeout: float) -> dict | None:
    query = urllib.parse.urlencode(
        {"sessionID": session, "_": f"{random.randint(0, 999999):06d}"}
    )
    result = _exchange(f"{IMAGE_LOOKUP}?{query}", None, timeout, method="GET")
    if result is None or not 200 <= result[0] < 300:
        return None
    try:
        payload = json.loads(result[1].decode("utf-8", "replace"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    nested = payload.get("data")
    if isinstance(nested, dict) and nested.get("imageURL"):
        return nested
    return payload


def _image_url(info: dict | None) -> str:
    if not info:
        return ""
    raw = str(info.get("imageURL") or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    inner = urllib.parse.parse_qs(parsed.query).get("image", [""])[0]
    chosen = urllib.parse.unquote(inner) if inner else raw
    if urllib.parse.urlparse(chosen).scheme not in {"http", "https"}:
        return ""
    return chosen


def _capture_note(info: dict | None) -> str:
    if not info:
        return ""
    package = info.get("infoPackage") if isinstance(info.get("infoPackage"), dict) else {}
    app_info = package.get("curAppInfo") if isinstance(package.get("curAppInfo"), dict) else {}
    app = str(app_info.get("curAppName") or "").strip()
    playing = package.get("vodPlayingInfo") or ""
    if isinstance(playing, dict):
        playing = playing.get("name") or playing.get("title") or ""
    title = str(playing).strip()
    if title:
        return f"{app}正在播放{title}"
    if app:
        return f"正在使用：{app}"
    return ""


def _download(url: str, timeout: float) -> bytes:
    result = _exchange(url, None, max(timeout, 5.0), method="GET")
    if result is None or not 200 <= result[0] < 300:
        raise RuntimeError("截屏图片下载失败")
    image = result[1]
    if len(image) > _MAX_IMAGE or not _looks_like_image(image):
        raise RuntimeError("截屏返回的不是图片")
    return image


def _looks_like_image(image: bytes) -> bool:
    return (
        image.startswith(b"\xff\xd8\xff")
        or image.startswith(b"\x89PNG\r\n\x1a\n")
        or (image.startswith(b"RIFF") and image[8:12] == b"WEBP")
    )
