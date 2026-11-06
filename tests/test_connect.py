"""MQTT connect: TLS fallback, 爱家 cert extract, error classification."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APK = ROOT / "com.hisense.ms.fly2tv.apk"


def test_classify_connect_error(proto_client) -> None:
    assert proto_client.classify_connect_error("mqtt_rc_5") == "not_authorized"
    assert proto_client.classify_connect_error("mqtt_rc_99") == "tls_failed"
    assert proto_client.classify_connect_error("tcp_timeout") == "timeout"
    assert proto_client.classify_connect_error("tcp_refused") == "cannot_connect"
    assert proto_client.classify_connect_error("mqtt_rc_98") == "cannot_connect"


def test_ssl_context_allows_legacy_ciphers(proto_certs) -> None:
    context = proto_certs.build_ssl_context(None, None)
    assert context.verify_mode == proto_certs.ssl.CERT_NONE
    assert context.check_hostname is False
    ciphers = context.get_ciphers()
    assert ciphers  # SECLEVEL=0 still selected something


def test_probe_tcp_timeout(proto_client, monkeypatch) -> None:
    def boom(address, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(proto_client.socket, "create_connection", boom)
    with pytest.raises(ConnectionError, match="tcp_timeout"):
        proto_client.probe_tcp("192.0.2.1", 36669, timeout=0.1)


def test_probe_tcp_refused(proto_client, monkeypatch) -> None:
    def boom(address, timeout=None):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(proto_client.socket, "create_connection", boom)
    with pytest.raises(ConnectionError, match="tcp_refused"):
        proto_client.probe_tcp("192.0.2.1", 36669)


def test_connect_falls_back_to_plain_after_tls_fail(proto_client, monkeypatch) -> None:
    client = proto_client.HisenseTvClient("127.0.0.1", uuid="aa:bb:cc:dd:ee:ff")
    calls: list[bool] = []

    def fake_try(creds, *, use_tls, certfile, keyfile):
        calls.append(use_tls)
        return 99 if use_tls else 0

    monkeypatch.setattr(proto_client, "probe_tcp", lambda *a, **k: None)
    monkeypatch.setattr(client, "_try_connect", fake_try)
    monkeypatch.setattr(client, "_stop_client", lambda: None)
    creds = client.connect_blocking()
    assert creds.mode == "static"
    assert True in calls and False in calls
    assert client.transport == "plain"
    assert client.use_ssl is False


@pytest.mark.skipif(not APK.is_file(), reason="爱家 APK not in workspace")
def test_extract_official_aijia_cert(proto_certs, tmp_path) -> None:
    pair = proto_certs.extract_official_cert(tmp_path, search_roots=[ROOT])
    assert pair is not None
    cert_path, key_path = pair
    pem = Path(cert_path).read_text()
    assert "BEGIN CERTIFICATE" in pem
    assert Path(key_path).read_text().startswith("-----BEGIN")
