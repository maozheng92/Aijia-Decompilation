"""Hisense BLE remoter: address parsing, HID payloads, sendkey prefers BLE."""

from __future__ import annotations

import asyncio

import pytest


def test_normalize_ble_address(proto_ble) -> None:
    assert proto_ble.normalize_ble_address("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert proto_ble.normalize_ble_address("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
    assert proto_ble.normalize_ble_address("") is None
    assert proto_ble.normalize_ble_address(None) is None
    with pytest.raises(ValueError):
        proto_ble.normalize_ble_address("zz:zz:zz:zz:zz:zz")
    with pytest.raises(ValueError):
        proto_ble.normalize_ble_address("aa:bb")


def test_hid_press_payload_matches_erf6a40(proto_ble, proto_keys) -> None:
    home = proto_ble.hid_usage_for_key("home")
    assert home is not None
    assert proto_ble.hid_press_payload(home) == bytes(
        [home.index, home.page, home.usage & 0xFF, (home.usage >> 8) & 0xFF]
    )
    assert proto_ble.hid_press_payload(home) == b"\x4a\x0c\x23\x02"
    power = proto_ble.hid_usage_for_key(proto_keys.KEY_POWER)
    assert proto_ble.hid_press_payload(power) == b"\x08\x0c\x30\x00"
    ok = proto_ble.hid_usage_for_key("ok")
    assert proto_ble.hogp_press_payload(ok) == bytes([ok.usage & 0xFF, (ok.usage >> 8) & 0xFF])
    assert proto_ble.hid_release_payload() == b"\x00\x00\x00\x00"


def test_aijia_keys_have_hid_usages(proto_ble, proto_keys) -> None:
    mapped = {
        proto_keys.KEY_POWER,
        proto_keys.KEY_VOLUMEUP,
        proto_keys.KEY_VOLUMEDOWN,
        proto_keys.KEY_MUTE,
        proto_keys.KEY_SOURCE,
        proto_keys.KEY_CONTROL_CENTER,
        proto_keys.KEY_UP,
        proto_keys.KEY_DOWN,
        proto_keys.KEY_LEFT,
        proto_keys.KEY_RIGHT,
        proto_keys.KEY_OK,
        proto_keys.KEY_RETURNS,
        proto_keys.KEY_HOME,
        proto_keys.KEY_MENU,
    }
    assert mapped <= set(proto_ble.HID_USAGES)
    assert proto_ble.hid_usage_for_key("screenshot") is None


def test_hisense_advertisement_matches_vendor_uuid(proto_ble) -> None:
    assert proto_ble.is_hisense_ble_advertisement(
        None, [proto_ble.HISENSE_BLE_SERVICE]
    )
    assert proto_ble.is_hisense_ble_advertisement("Hisense TV", [])
    assert proto_ble.is_hisense_ble_advertisement("E7NPro", None)
    assert not proto_ble.is_hisense_ble_advertisement("xiaomi band", [])


def test_send_key_prefers_ble_and_skips_mqtt(proto_client) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    sent: list[str] = []

    class FakeBle:
        connected = True

        async def async_send_key(self, key: str) -> bool:
            sent.append(key)
            return True

    client.ble = FakeBle()

    def boom(_key: str) -> None:
        raise AssertionError("MQTT sendkey should not run when BLE succeeds")

    client.send_key = boom  # type: ignore[method-assign]
    asyncio.run(client.async_send_key("home"))
    assert sent == ["home"]


def test_send_key_falls_back_to_mqtt_when_ble_returns_false(
    proto_client, proto_credentials
) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    payloads: list[str] = []

    class FakeBle:
        connected = True

        async def async_send_key(self, key: str) -> bool:
            return False

    class FakeMqtt:
        def publish(self, topic, body, qos=0, retain=False):
            payloads.append(body)

            class Info:
                rc = proto_client.mqtt.MQTT_ERR_SUCCESS

                def wait_for_publish(self, timeout=None):
                    return None

            return Info()

    client.ble = FakeBle()
    client._creds = proto_credentials.generate_dynamic_credentials(
        "aa:bb:cc:dd:ee:ff", timestamp=1
    )
    client._client = FakeMqtt()
    asyncio.run(client.async_send_key("home"))
    assert "KEY_HOME" in payloads


def test_screenshot_bypasses_ble(proto_client, proto_credentials) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    topics: list[str] = []

    class FakeBle:
        async def async_send_key(self, key: str) -> bool:
            raise AssertionError("screenshot is not a BLE HID key")

    class FakeMqtt:
        def publish(self, topic, body, qos=0, retain=False):
            topics.append(topic)

            class Info:
                rc = proto_client.mqtt.MQTT_ERR_SUCCESS

                def wait_for_publish(self, timeout=None):
                    return None

            return Info()

    client.ble = FakeBle()
    client._creds = proto_credentials.generate_dynamic_credentials(
        "aa:bb:cc:dd:ee:ff", timestamp=1
    )
    client._client = FakeMqtt()
    asyncio.run(client.async_send_key("screenshot"))
    assert any(topic.endswith("/actions/captureTvScreen") for topic in topics)


def test_mqtt_disconnect_keeps_available_when_ble_up(proto_client) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")

    class FakeBle:
        connected = True

    client.ble = FakeBle()
    client.state.available = True
    client.state.power_on = True
    client._on_disconnect(None, None, 0)
    assert client.state.available is True
    assert client.state.power_on is True
