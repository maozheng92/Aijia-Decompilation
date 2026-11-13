"""Local HTTP key channel on ports 7778 and 7779."""

from __future__ import annotations

import io
import urllib.error


class _Response(io.BytesIO):
    def __init__(self, status: int) -> None:
        super().__init__(b"ok")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()


class _Body(io.BytesIO):
    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()


def test_post_key_to_7778(proto_local_http, monkeypatch) -> None:
    seen: list[tuple[str, str]] = []

    def fake_urlopen(request, timeout=0):
        del timeout
        seen.append((request.full_url, request.get_method()))
        if request.full_url.startswith("http://192.0.2.10:7778/") and request.get_method() == "POST":
            return _Response(200)
        raise urllib.error.URLError("down")

    monkeypatch.setattr(proto_local_http.urllib.request, "urlopen", fake_urlopen)
    status = proto_local_http.send_local_key("192.0.2.10", "KEY_VOLUMEUP", timeout=0.1)
    assert status == 200
    assert seen == [("http://192.0.2.10:7778/KEY_VOLUMEUP..controller", "POST")]


def test_falls_through_to_7779(proto_local_http, monkeypatch) -> None:
    def fake_urlopen(request, timeout=0):
        del timeout
        if ":7779/" in request.full_url and request.get_method() == "POST":
            return _Response(200)
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(proto_local_http.urllib.request, "urlopen", fake_urlopen)
    status = proto_local_http.send_local_key("192.0.2.10", "KEY_OK", timeout=0.1)
    assert status == 200


def test_voice_opens_source(proto_local_http, monkeypatch) -> None:
    seen: list[tuple[str, bytes | None]] = []

    def fake_urlopen(request, timeout=0):
        del timeout
        seen.append((request.full_url, request.data))
        if request.full_url.endswith(":7779/..pushwechatvoice"):
            return _Response(200)
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(proto_local_http.urllib.request, "urlopen", fake_urlopen)
    status = proto_local_http.push_voice("192.0.2.10", "信号源", timeout=0.1)
    assert status == 200
    assert seen[0][0] == "http://192.0.2.10:7779/..pushwechatvoice"
    assert b'"voice":"\xe4\xbf\xa1\xe5\x8f\xb7\xe6\xba\x90"' in seen[0][1]


def test_capture_saves_uploaded_frame(proto_local_http, monkeypatch) -> None:
    jpeg = b"\xff\xd8\xff\xd9"

    def fake_urlopen(request, timeout=0):
        del timeout
        url = request.full_url
        if url.endswith("/..commonstarttvapp"):
            assert b"UPLOAD_CAPTURE" in request.data
            assert b"mobilekey" in request.data
            return _Body(200, b"ok")
        if "imageurl/by/id" in url:
            body = (
                '{"imageURL":"https://img.example/a.jpg?image=https%3A%2F%2Fcdn.example%2Fshot.jpg",'
                '"infoPackage":{"curAppInfo":{"curAppName":"聚好看"},"vodPlayingInfo":"新闻"}}'
            ).encode()
            return _Body(200, body)
        if url == "https://cdn.example/shot.jpg":
            return _Body(200, jpeg)
        raise urllib.error.URLError(url)

    monkeypatch.setattr(proto_local_http.urllib.request, "urlopen", fake_urlopen)
    shot = proto_local_http.capture_screen("192.0.2.10", pause=lambda _seconds: None, retries=2)
    assert shot.image == jpeg
    assert shot.note == "聚好看正在播放新闻"
    assert shot.source_url == "https://cdn.example/shot.jpg"


def test_source_stops_after_voice(proto_client, proto_credentials, monkeypatch) -> None:
    client = proto_client.HisenseTvClient("192.0.2.10", uuid="12:34:56:78:9a:bc")
    client._creds = proto_credentials.generate_dynamic_credentials(
        "12:34:56:78:9a:bc", timestamp=1
    )
    published: list[str] = []

    class FakeMqtt:
        def publish(self, topic, body, qos=0, retain=False):
            published.append(topic)

            class Info:
                rc = proto_client.mqtt.MQTT_ERR_SUCCESS

                def wait_for_publish(self, timeout=None):
                    return None

            return Info()

    client._client = FakeMqtt()
    monkeypatch.setattr(proto_client, "push_voice", lambda host, text, **kwargs: 200)
    client.open_source()
    assert published == []


def test_send_key_stops_after_http_accepts(proto_client, proto_credentials, monkeypatch) -> None:
    client = proto_client.HisenseTvClient("192.0.2.10", uuid="12:34:56:78:9a:bc")
    client._creds = proto_credentials.generate_dynamic_credentials(
        "12:34:56:78:9a:bc", timestamp=1
    )
    published: list[str] = []

    class FakeMqtt:
        def publish(self, topic, body, qos=0, retain=False):
            published.append(topic)

            class Info:
                rc = proto_client.mqtt.MQTT_ERR_SUCCESS

                def wait_for_publish(self, timeout=None):
                    return None

            return Info()

    client._client = FakeMqtt()
    monkeypatch.setattr(proto_client, "send_local_key", lambda host, key, **kwargs: 200)
    client.send_key("home")
    assert published == []
