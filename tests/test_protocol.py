"""Topic builders, key aliases, and MQTT payload parsing."""

from __future__ import annotations


def test_key_aliases_match_aijia(proto_keys) -> None:
    assert proto_keys.normalize_key("power") == proto_keys.KEY_POWER
    assert proto_keys.normalize_key("KEY_HOME") == proto_keys.KEY_HOME
    assert proto_keys.normalize_key("ok") == "KEY_OK"
    assert proto_keys.normalize_key("jubao") == "KEY_JUBAO"
    assert proto_keys.normalize_key("returns") == "KEY_RETURNS"
    assert proto_keys.normalize_key("settings") == proto_keys.KEY_CONTROL_CENTER
    assert proto_keys.normalize_key("screenshot") == "screenshot"


def test_aijia_remoter_has_screenshot_keys(proto_keys) -> None:
    slugs = [item.slug for item in proto_keys.AIJIA_REMOTER_BUTTONS]
    assert slugs == [
        "power",
        "volume_down",
        "mute",
        "volume_up",
        "screenshot",
        "source",
        "smart_image",
        "settings",
        "up",
        "left",
        "ok",
        "right",
        "down",
        "back",
        "home",
        "menu",
    ]
    commands = proto_keys.aijia_send_commands()
    assert "KEY_HOME" in commands
    assert "KEY_CONTROL_CENTER" in commands
    assert "screenshot" in commands
    assert "smart_image" in commands


def test_sendkey_topic_uses_client_id(proto_credentials, proto_topics) -> None:
    creds = proto_credentials.generate_dynamic_credentials(
        "56:b8:88:4e:f7:19", timestamp=1766974704
    )
    topic = proto_topics.sendkey(creds)
    assert topic.startswith("/remoteapp/tv/remote_service/")
    assert topic.endswith("/actions/sendkey")
    assert creds.client_id in topic
    assert "HomeAssistant" not in topic


def test_sendkey_fanout_includes_tv_mac_identities(proto_credentials, proto_topics) -> None:
    creds = proto_credentials.generate_dynamic_credentials(
        "12:34:56:78:9a:bc", timestamp=1766974704
    )
    topics = proto_topics.action_topics(
        creds, "remote_service", "sendkey", tv_mac="aa:bb:cc:dd:ee:ff"
    )
    assert any(
        item.endswith("/aa:bb:cc:dd:ee:ff$vidaa_common/actions/sendkey") for item in topics
    )
    assert any(item.endswith("/aa:bb:cc:dd:ee:ff$normal/actions/sendkey") for item in topics)
    assert any(item.endswith("/AA:BB:CC:DD:EE:FF$normal/actions/sendkey") for item in topics)
    assert any("/12:34:56:78:9a:bc$vidaa_common/actions/sendkey" in item for item in topics)
    assert creds.client_id in topics[0]


def test_pair_topic_and_subscriptions_are_concrete(proto_credentials, proto_topics) -> None:
    creds = proto_credentials.generate_dynamic_credentials(
        "56:b8:88:4e:f7:19", timestamp=1766974704
    )
    assert proto_topics.vidaa_app_connect(creds).endswith("/actions/vidaa_app_connect")
    subs = proto_topics.subscription_topics(creds)
    assert not any(item.endswith("#") or "/+" in item for item in subs)
    assert "/remoteapp/mobile/broadcast/ui_service/state" in subs


def test_volume_and_source_parsing(proto_client) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    client._apply_volume({"volume_value": 24, "mute": 1})
    assert client.state.volume == 24
    assert client.state.muted is True
    client._apply_volume("40")
    assert client.state.volume == 40
    client._apply_sources(
        [{"sourceid": "3", "sourcename": "HDMI1"}, {"sourceid": "0", "sourcename": "TV"}]
    )
    assert client.state.sources[0]["name"] == "HDMI1"
    client._apply_state({"statetype": "remote_launcher", "sourcename": "HDMI1"})
    assert client.state.power_on is True
    assert client.state.statetype == "remote_launcher"


def test_send_key_publishes_raw_and_json_on_mac_topics(proto_client, proto_credentials) -> None:
    client = proto_client.HisenseTvClient(
        "127.0.0.1",
        uuid="12:34:56:78:9a:bc",
        tv_mac="aa:bb:cc:dd:ee:ff",
    )
    client._creds = proto_credentials.generate_dynamic_credentials(
        "12:34:56:78:9a:bc", timestamp=1
    )
    published: list[tuple[str, str]] = []

    class FakeMqtt:
        def publish(self, topic, body, qos=0, retain=False):
            published.append((topic, body))

            class Info:
                rc = proto_client.mqtt.MQTT_ERR_SUCCESS

                def wait_for_publish(self, timeout=None):
                    return None

            return Info()

    client._client = FakeMqtt()
    client.send_key("home")
    topics = [topic for topic, _ in published]
    payloads = [payload for _, payload in published]
    assert any(
        topic.endswith("/aa:bb:cc:dd:ee:ff$vidaa_common/actions/sendkey") for topic in topics
    )
    assert any(topic.endswith("/aa:bb:cc:dd:ee:ff$normal/actions/sendkey") for topic in topics)
    assert "KEY_HOME" in payloads
    assert '{"key":"KEY_HOME"}' in payloads
    published.clear()
    client.send_key("screenshot")
    shot_topics = [topic for topic, _ in published]
    assert any(topic.endswith("/actions/captureTvScreen") for topic in shot_topics)
    assert any(topic.endswith("/actions/getTvScreenInfo") for topic in shot_topics)


def test_wol_packet_shape(proto_client, monkeypatch) -> None:
    sent: list[tuple[bytes, tuple]] = []

    class FakeSock:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def setsockopt(self, *args):
            return None

        def sendto(self, packet, addr):
            sent.append((packet, addr))

    monkeypatch.setattr(proto_client.socket, "socket", lambda *a, **k: FakeSock())
    proto_client.send_wol("aa:bb:cc:dd:ee:ff")
    packet, addr = sent[0]
    assert packet.startswith(b"\xff" * 6)
    assert packet.count(bytes.fromhex("aabbccddeeff")) == 16
    assert addr[1] == 9
