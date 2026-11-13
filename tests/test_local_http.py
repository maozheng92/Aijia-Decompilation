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
