"""Custom TV inputs are remoter key macros."""

from __future__ import annotations

import pytest


def test_parse_source_right_ok(proto_custom_sources) -> None:
    sources = proto_custom_sources.parse_custom_sources_text(
        "HDMI1: KEY_SOURCE, KEY_RIGHT, KEY_OK\n"
        "HDMI2: source, right, right, ok\n"
        "# comment\n"
    )
    assert sources == [
        {"name": "HDMI1", "keys": ["KEY_SOURCE", "KEY_RIGHT", "KEY_OK"]},
        {"name": "HDMI2", "keys": ["KEY_SOURCE", "KEY_RIGHT", "KEY_RIGHT", "KEY_OK"]},
    ]


def test_parse_accepts_chinese_separators(proto_custom_sources) -> None:
    sources = proto_custom_sources.parse_custom_sources_text(
        "机顶盒：source、right、ok"
    )
    assert sources == [
        {"name": "机顶盒", "keys": ["KEY_SOURCE", "KEY_RIGHT", "KEY_OK"]},
    ]


def test_serialize_roundtrip(proto_custom_sources) -> None:
    text = "HDMI1: KEY_SOURCE, KEY_RIGHT, KEY_OK"
    sources = proto_custom_sources.parse_custom_sources_text(text)
    assert proto_custom_sources.serialize_custom_sources(sources) == text


def test_normalize_dict_and_list(proto_custom_sources) -> None:
    assert proto_custom_sources.normalize_custom_sources(
        {"AV": "source, down, ok"}
    ) == [{"name": "AV", "keys": ["KEY_SOURCE", "KEY_DOWN", "KEY_OK"]}]
    assert proto_custom_sources.normalize_custom_sources(
        [{"name": "USB", "keys": ["KEY_SOURCE", "KEY_OK"]}]
    ) == [{"name": "USB", "keys": ["KEY_SOURCE", "KEY_OK"]}]


def test_rejects_bad_lines(proto_custom_sources) -> None:
    with pytest.raises(ValueError):
        proto_custom_sources.parse_custom_sources_text("only-name")
    with pytest.raises(ValueError):
        proto_custom_sources.parse_custom_sources_text("A: KEY_OK\nA: KEY_HOME")


def test_slug_is_stable(proto_custom_sources) -> None:
    first = proto_custom_sources.custom_source_slug("HDMI1")
    second = proto_custom_sources.custom_source_slug("HDMI1")
    assert first == second
    assert "hdmi1" in first


def test_format_and_summarize_sequences(proto_custom_sources) -> None:
    assert (
        proto_custom_sources.format_key_sequence(
            ["KEY_SOURCE", "KEY_RIGHT", "KEY_OK"]
        )
        == "source → right → ok"
    )
    summary = proto_custom_sources.summarize_custom_sources(
        [
            {"name": "HDMI1", "keys": ["KEY_SOURCE", "KEY_RIGHT", "KEY_OK"]},
            {"name": "HDMI2", "keys": ["KEY_SOURCE", "KEY_RIGHT", "KEY_RIGHT", "KEY_OK"]},
        ]
    )
    assert "HDMI1: source → right → ok" in summary
    assert "HDMI2: source → right → right → ok" in summary
    assert "KEY_SOURCE" in proto_custom_sources.SEQUENCE_BUTTON_KEYS
    assert "KEY_RIGHT" in proto_custom_sources.SEQUENCE_BUTTON_KEYS


def test_run_key_sequence_pauses_between_keys(proto_client) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    sent: list[str] = []
    waits: list[float] = []

    def fake_send(key: str) -> None:
        sent.append(key)

    def fake_pause(seconds: float) -> None:
        waits.append(seconds)

    client.send_key = fake_send  # type: ignore[method-assign]
    client.run_key_sequence(
        ["KEY_SOURCE", "KEY_RIGHT", "KEY_OK"],
        delay=0.4,
        pause=fake_pause,
    )
    assert sent == ["KEY_SOURCE", "KEY_RIGHT", "KEY_OK"]
    assert waits == [0.4, 0.4]


def test_key_source_uses_open_source(proto_client) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    opened: list[str] = []

    def fake_open() -> None:
        opened.append("open")

    client.open_source = fake_open  # type: ignore[method-assign]
    client.send_key("KEY_SOURCE")
    client.send_key("source")
    assert opened == ["open", "open"]
