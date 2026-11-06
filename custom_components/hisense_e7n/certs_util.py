"""Optional mTLS helper.

E7N Pro's broker asks for a client certificate.  Some firmware only
checks that *a* cert is presented; newer builds want the official
VIDAA app identity.  This module:

* generates a stand-in cert with the VIDAA subject (enough for many sets)
* loads user-supplied PEM paths when the stand-in is rejected
"""

from __future__ import annotations

import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path


VIDAA_SUBJECT = {
    "country": "CN",
    "state": "shandong",
    "org": "hh",
    "ou": "multimedia",
    "cn": "VidaaAppAndroidV01",
}


def generate_standin_cert(cert_file: Path, key_file: Path) -> None:
    """Write a self-signed cert whose subject matches the VIDAA Android app."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    cert_file.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, VIDAA_SUBJECT["country"]),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, VIDAA_SUBJECT["state"]),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, VIDAA_SUBJECT["org"]),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, VIDAA_SUBJECT["ou"]),
            x509.NameAttribute(NameOID.COMMON_NAME, VIDAA_SUBJECT["cn"]),
        ]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    key_file.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.chmod(0o600)
    cert_file.chmod(0o644)


def ensure_cert_pair(directory: Path) -> tuple[str, str]:
    """Return ``(cert, key)`` paths, creating a stand-in pair if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    cert_file = directory / "client.pem"
    key_file = directory / "client.key"
    if not cert_file.exists() or not key_file.exists():
        generate_standin_cert(cert_file, key_file)
    return str(cert_file), str(key_file)


def build_ssl_context(certfile: str | None, keyfile: str | None) -> ssl.SSLContext:
    """TLS context that skips verifying the TV's self-signed server cert."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if certfile and keyfile:
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    return context
