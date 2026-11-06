"""mTLS helpers for the TV's old Mosquitto broker.

Home Assistant's OpenSSL 3 stack rejects the ciphers Hisense still uses
unless SECLEVEL is dropped *before* loading the client chain.  Chinese
爱家 firmware also expects the RemoteNOW client cert from the APK
(CN=remoteclientmobile), not a self-signed stand-in.
"""

from __future__ import annotations

import logging
import ssl
import zipfile
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

VIDAA_SUBJECT = {
    "country": "CN",
    "state": "shandong",
    "org": "hh",
    "ou": "multimedia",
    "cn": "VidaaAppAndroidV01",
}

# Public protocol constant (same store password documented for VIDAA / RemoteNOW).
P12_PASSWORDS = (
    "186e990688070325a1c4b0ce275d2388",
    "multiscreen123",
    "ayd6afbj2huf3",
)

COMPONENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = COMPONENT_DIR.parent.parent
AIJIA_APK_NAME = "com.hisense.ms.fly2tv.apk"


def generate_standin_cert(cert_file: Path, key_file: Path) -> None:
    """Write a self-signed cert whose subject matches the VIDAA Android app."""
    from datetime import datetime, timedelta, timezone

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
    """TLS context that can talk to Hisense's legacy Mosquitto.

    Cipher SECLEVEL must be lowered *before* load_cert_chain: OpenSSL 3
    otherwise rejects the 2018 RemoteNOW key with EE_KEY_TOO_SMALL /
    CA_MD_TOO_WEAK and the handshake never starts.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    for cipher in ("DEFAULT:@SECLEVEL=0", "ALL:@SECLEVEL=0", "DEFAULT:@SECLEVEL=1"):
        try:
            context.set_ciphers(cipher)
            break
        except ssl.SSLError:
            continue
    legacy = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    if legacy:
        context.options |= legacy
    min_ver = getattr(ssl, "TLSVersion", None)
    if min_ver is not None:
        for candidate in (
            getattr(min_ver, "MINIMUM_SUPPORTED", None),
            getattr(min_ver, "TLSv1", None),
            getattr(min_ver, "TLSv1_2", None),
        ):
            if candidate is None:
                continue
            try:
                context.minimum_version = candidate
                break
            except (ValueError, OverflowError, ssl.SSLError):
                continue
    if certfile and keyfile:
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    return context


def _write_p12(data: bytes, cert_file: Path, key_file: Path) -> bool:
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        pkcs12,
    )

    for password in P12_PASSWORDS:
        try:
            private_key, cert, _extra = pkcs12.load_key_and_certificates(
                data, password.encode("utf-8")
            )
        except (ValueError, TypeError):
            continue
        if private_key is None or cert is None:
            continue
        cert_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(
            private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
        )
        cert_file.write_bytes(cert.public_bytes(Encoding.PEM))
        key_file.chmod(0o600)
        cert_file.chmod(0o644)
        _LOGGER.info("Unlocked 爱家/VIDAA client certificate into %s", cert_file)
        return True
    return False


def _p12_blobs_from_apk(apk: Path) -> list[bytes]:
    blobs: list[bytes] = []
    with zipfile.ZipFile(apk) as zf:
        names = [name for name in zf.namelist() if name.lower().endswith(".p12")]
        # Prefer the 2565-byte RemoteNOW store used by 爱家 (`res/6D.p12`).
        names.sort(key=lambda name: (0 if zf.getinfo(name).file_size == 2565 else 1, name))
        for name in names:
            blobs.append(zf.read(name))
    return blobs


def iter_cert_sources(search_roots: list[Path] | None = None) -> list[Path]:
    """APK / PKCS#12 locations: HA config dir, repo root, integration certs."""
    candidates: list[Path] = []
    roots = list(search_roots or [])
    roots.extend([COMPONENT_DIR / "certs", REPO_ROOT, Path.cwd()])
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        extras = [resolved]
        if resolved.is_dir():
            extras.extend(
                [
                    resolved / AIJIA_APK_NAME,
                    resolved / "certs" / "client.p12",
                    resolved / "client.p12",
                ]
            )
        for path in extras:
            try:
                real = path.resolve()
            except OSError:
                continue
            if real in seen or not real.is_file():
                continue
            if real.suffix.lower() in {".apk", ".p12"}:
                seen.add(real)
                candidates.append(real)
    return candidates


def extract_official_cert(
    dest_dir: Path, search_roots: list[Path] | None = None
) -> tuple[str, str] | None:
    """Unlock the 爱家 RemoteNOW client cert into ``dest_dir`` if a store is found."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    cert_file = dest_dir / "aijia_client.pem"
    key_file = dest_dir / "aijia_client.key"
    if cert_file.exists() and key_file.exists() and cert_file.stat().st_size > 0:
        return str(cert_file), str(key_file)
    for source in iter_cert_sources(search_roots):
        try:
            if source.suffix.lower() == ".p12":
                ok = _write_p12(source.read_bytes(), cert_file, key_file)
            else:
                ok = any(
                    _write_p12(blob, cert_file, key_file) for blob in _p12_blobs_from_apk(source)
                )
        except (OSError, zipfile.BadZipFile) as err:
            _LOGGER.debug("Skipped cert source %s: %s", source, err)
            continue
        if ok:
            return str(cert_file), str(key_file)
    return None


def resolve_cert_candidates(
    dest_dir: Path,
    user_cert: str | None = None,
    user_key: str | None = None,
    search_roots: list[Path] | None = None,
) -> list[tuple[str, str]]:
    """Official 爱家 cert first, then the generated VidaaAppAndroidV01 stand-in."""
    pairs: list[tuple[str, str]] = []
    if user_cert and user_key and Path(user_cert).is_file() and Path(user_key).is_file():
        pairs.append((user_cert, user_key))
    official = extract_official_cert(dest_dir, search_roots=search_roots)
    if official and official not in pairs:
        pairs.append(official)
    standin = ensure_cert_pair(dest_dir)
    if standin not in pairs:
        pairs.append(standin)
    return pairs
