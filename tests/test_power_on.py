"""Power-on goes through an HA button device, not Aijia KEY_POWER."""

from __future__ import annotations

import asyncio

import pytest


def test_button_maps_to_press(proto_power) -> None:
    assert proto_power.power_on_service("button.ir_tv_power") == ("button", "press")
    assert proto_power.power_on_service("input_button.tv_on") == (
        "input_button",
        "press",
    )


def test_switch_and_script_map_to_turn_on(proto_power) -> None:
    assert proto_power.power_on_service("switch.tv_plug") == ("switch", "turn_on")
    assert proto_power.power_on_service("script.hisense_e7n_power_on") == (
        "script",
        "turn_on",
    )


def test_normalize_rejects_empty(proto_power) -> None:
    assert proto_power.normalize_power_on_entity(None) is None
    assert proto_power.normalize_power_on_entity("  ") is None
    assert proto_power.normalize_power_on_entity("not-an-entity") is None
    assert proto_power.normalize_power_on_entity("button.ir_tv_power") == (
        "button.ir_tv_power"
    )


def test_button_is_the_primary_power_on_domain(proto_power) -> None:
    assert "button" in proto_power.POWER_ON_DOMAINS
    assert "input_button" in proto_power.POWER_ON_DOMAINS


def test_unsupported_domain_raises(proto_power) -> None:
    with pytest.raises(ValueError, match="unsupported power-on domain"):
        proto_power.power_on_service("media_player.tv")


def test_wait_for_broker_retries_until_connect(proto_client, monkeypatch) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    attempts = {"n": 0}

    async def fake_connect() -> None:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ConnectionError("mqtt_rc_98")

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(client, "async_connect", fake_connect)
    monkeypatch.setattr(proto_client.asyncio, "sleep", no_sleep)
    assert asyncio.run(client.async_wait_for_broker()) is True
    assert attempts["n"] == 2


def test_wol_turn_on_skipped_when_already_available(proto_client, monkeypatch) -> None:
    client = proto_client.HisenseTvClient(
        "127.0.0.1", uuid="aa:bb:cc:dd:ee:ff", tv_mac="aa:bb:cc:dd:ee:ff"
    )
    client.state.available = True
    called = {"wol": False}

    def fake_wol(mac: str) -> None:
        called["wol"] = True

    monkeypatch.setattr(proto_client, "send_wol", fake_wol)
    asyncio.run(client.async_turn_on())
    assert called["wol"] is False
