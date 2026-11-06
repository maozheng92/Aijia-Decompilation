"""VIDAA MQTT credential generation.

E7N Pro (VIDAA U7/U8, 2024+) rejects the old static
``hisenseservice`` / ``multimqttservice`` login.  The phone app
mints a MAC-shaped UUID, then derives client_id / username / password
the same way ``libmqttcrypt.so`` does.

The algorithm and the two live test vectors below are public
protocol notes, not secrets extracted from a keystore.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

from .const import STATIC_MQTT_PASSWORD, STATIC_MQTT_USERNAME

# From libmqttcrypt.so getSalt()/getInfo().
PATTERN = "38D65DC30F45109A369A86FCE866A85B"
VALUE_SUFFIX_MODERN = "h!i@s#$v%i^d&a*a"
VALUE_SUFFIX_LEGACY = "h*i&s%e!r^v0i1c9"
XOR_CONST = 0x569814772B03A968
BRAND = "his"
OPERATION = "vidaacommon"


def _md5_upper(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().upper()


def random_client_uuid() -> str:
    """Mint a locally-administered unicast MAC-shaped UUID.

    The official app does not use the phone's hardware MAC; it
    persists a random identifier of this form.
    """
    raw = bytearray(secrets.token_bytes(6))
    raw[0] = (raw[0] | 0x02) & 0xFE
    return ":".join(f"{byte:02x}" for byte in raw)


def normalize_uuid(uuid: str) -> str:
    cleaned = uuid.strip().replace("-", ":").lower()
    parts = [part for part in cleaned.split(":") if part]
    if len(parts) == 1 and len(parts[0]) == 12:
        hex_str = parts[0]
        parts = [hex_str[i : i + 2] for i in range(0, 12, 2)]
    if len(parts) != 6:
        raise ValueError(f"Invalid MAC/UUID: {uuid}")
    return ":".join(parts)


@dataclass(frozen=True)
class MqttCredentials:
    client_id: str
    username: str
    password: str
    uuid: str
    timestamp: int
    mode: str


def generate_dynamic_credentials(
    uuid: str,
    timestamp: int | None = None,
    *,
    modern: bool = True,
) -> MqttCredentials:
    """Build MQTT CONNECT credentials for a VIDAA broker."""
    uuid = normalize_uuid(uuid)
    if timestamp is None:
        timestamp = int(time.time())

    race_md5 = _md5_upper(f"{PATTERN}${uuid}")[:6]
    client_id = f"{uuid}${BRAND}${race_md5}_{OPERATION}_001"
    username = f"{BRAND}${timestamp ^ XOR_CONST}"

    remainder = sum(int(digit) for digit in str(timestamp)) % 10
    suffix = VALUE_SUFFIX_MODERN if modern else VALUE_SUFFIX_LEGACY
    value_md5 = _md5_upper(f"{BRAND}{remainder}{suffix}")[:6]
    password = _md5_upper(f"{timestamp}${value_md5}")

    return MqttCredentials(
        client_id=client_id,
        username=username,
        password=password,
        uuid=uuid,
        timestamp=timestamp,
        mode="dynamic_modern" if modern else "dynamic_legacy",
    )


def generate_static_credentials(uuid: str) -> MqttCredentials:
    """Pre-2024 firmware: shared broker user, arbitrary client id."""
    uuid = normalize_uuid(uuid)
    compact = uuid.replace(":", "")
    return MqttCredentials(
        client_id=f"hisense_ha_{compact}",
        username=STATIC_MQTT_USERNAME,
        password=STATIC_MQTT_PASSWORD,
        uuid=uuid,
        timestamp=0,
        mode="static",
    )


def credentials_for_mode(mode: str, uuid: str) -> list[MqttCredentials]:
    """Return credential candidates in try-order for ``auto``/``dynamic``/``static``."""
    mode = (mode or "auto").lower()
    dynamic_modern = generate_dynamic_credentials(uuid, modern=True)
    dynamic_legacy = generate_dynamic_credentials(uuid, modern=False)
    static = generate_static_credentials(uuid)
    if mode == "static":
        return [static]
    if mode == "dynamic":
        return [dynamic_modern, dynamic_legacy]
    return [dynamic_modern, dynamic_legacy, static]
