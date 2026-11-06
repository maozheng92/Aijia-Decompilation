"""Credential algorithm matches published VIDAA live captures."""

from __future__ import annotations


def test_normalize_uuid_colon_and_plain(proto_credentials) -> None:
    assert proto_credentials.normalize_uuid("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert proto_credentials.normalize_uuid("aabbccddeeff") == "aa:bb:cc:dd:ee:ff"


def test_random_uuid_is_locally_administered(proto_credentials) -> None:
    uuid = proto_credentials.random_client_uuid()
    first = int(uuid.split(":")[0], 16)
    assert first & 0x02
    assert not first & 0x01
    assert len(uuid.split(":")) == 6


def test_modern_vector_from_protocol_notes(proto_credentials) -> None:
    creds = proto_credentials.generate_dynamic_credentials(
        "56:b8:88:4e:f7:19", timestamp=1766974704, modern=True
    )
    assert creds.client_id == "56:b8:88:4e:f7:19$his$256DBF_vidaacommon_001"
    assert creds.username == "his$6239759786168176024"
    assert creds.password == "C3BA44782E18ABF4892AC44D79A622D2"


def test_live_capture_2026(proto_credentials) -> None:
    creds = proto_credentials.generate_dynamic_credentials(
        "88:b8:0a:41:bb:48", timestamp=1785895169, modern=True
    )
    assert creds.client_id == "88:b8:0a:41:bb:48$his$C23ED5_vidaacommon_001"
    assert creds.username == "his$6239759786153422953"
    assert creds.password == "7D5A1D30D1EC5944FE46851B2C3C3AB0"


def test_static_credentials(proto_credentials) -> None:
    creds = proto_credentials.generate_static_credentials("aa:bb:cc:dd:ee:ff")
    assert creds.username == "hisenseservice"
    assert creds.password == "multimqttservice"
    assert creds.client_id == "aa:bb:cc:dd:ee:ff$vidaa_common"
    assert proto_credentials.generate_static_credentials(
        "aa:bb:cc:dd:ee:ff", flavor="normal"
    ).client_id == "aa:bb:cc:dd:ee:ff$normal"


def test_prefer_tv_mac_uuid(proto_credentials) -> None:
    assert (
        proto_credentials.prefer_tv_mac_uuid("12:34:56:78:9a:bc", "AA-BB-CC-DD-EE-FF")
        == "aa:bb:cc:dd:ee:ff"
    )
    assert (
        proto_credentials.prefer_tv_mac_uuid("12:34:56:78:9a:bc", None)
        == "12:34:56:78:9a:bc"
    )


def test_auto_mode_includes_mac_shaped_static(proto_credentials) -> None:
    modes = [item.client_id for item in proto_credentials.credentials_for_mode("auto", "aa:bb:cc:dd:ee:ff")]
    assert "aa:bb:cc:dd:ee:ff$vidaa_common" in modes
    assert "aa:bb:cc:dd:ee:ff$normal" in modes
    assert not any(item.startswith("hisense_ha_") for item in modes)
