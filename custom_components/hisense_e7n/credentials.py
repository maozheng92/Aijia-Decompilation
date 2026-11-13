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

from .const import REMOTE_CLIENT_ID, STATIC_MQTT_PASSWORD, STATIC_MQTT_USERNAME

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


def stable_client_uuid(stored: str | None, tv_mac: str | None = None) -> str:
    """Return the persisted phone-style client id.

    VIDAA sendkey is authorized for this id, not for the TV Wi-Fi MAC.
    A stored id that is just the TV MAC is discarded so keys are not published
    as the television talking to itself.
    """
    mac_norm = None
    if tv_mac:
        try:
            mac_norm = normalize_uuid(tv_mac)
        except ValueError:
            mac_norm = None
    if stored:
        try:
            stored_norm = normalize_uuid(stored)
        except ValueError:
            stored_norm = None
        else:
            if stored_norm != mac_norm:
                return stored_norm
    return random_client_uuid()


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


def generate_static_credentials(uuid: str, *, flavor: str = "vidaa_common") -> MqttCredentials:
    """Pre-2024 firmware: shared broker user; topic identity must be MAC-shaped."""
    uuid = normalize_uuid(uuid)
    if flavor == "normal":
        client_id = f"{uuid}$normal"
        mode = "static_normal"
    elif flavor == "bare":
        client_id = uuid
        mode = "static_bare"
    else:
        client_id = f"{uuid}$vidaa_common"
        mode = "static"
    return MqttCredentials(
        client_id=client_id,
        username=STATIC_MQTT_USERNAME,
        password=STATIC_MQTT_PASSWORD,
        uuid=uuid,
        timestamp=0,
        mode=mode,
    )


def _as_remote_client(creds: MqttCredentials) -> MqttCredentials:
    """Keep the password, but use the sehaas remote client id."""
    return MqttCredentials(
        client_id=REMOTE_CLIENT_ID,
        username=creds.username,
        password=creds.password,
        uuid=creds.uuid,
        timestamp=creds.timestamp,
        mode=f"remote_{creds.mode}",
    )


def generate_remote_static_credentials(uuid: str) -> MqttCredentials:
    """sehaas bridge login: client ``HomeAssistant``, user ``hisenseservice``."""
    return _as_remote_client(generate_static_credentials(uuid))


def with_access_token(creds: MqttCredentials, access_token: str) -> MqttCredentials:
    """Swap in the control password the TV issues after the on-screen code.

    The MD5 password only opens the broker. Commands are accepted after
    reconnecting with the same client id and username, and this token as
    the password.
    """
    token = access_token.strip()
    if not token:
        raise ValueError("access token is empty")
    return MqttCredentials(
        client_id=creds.client_id,
        username=creds.username,
        password=token,
        uuid=creds.uuid,
        timestamp=creds.timestamp,
        mode="access_token",
    )


def credentials_for_mode(mode: str, uuid: str) -> list[MqttCredentials]:
    """Pairing passwords, in try order.

    The dynamic client id must stay paired with its own password. Trying
    ``HomeAssistant`` first accepts a login the TV will not authorize for
    keys. That static client is only a last resort for older firmware.
    """
    mode = (mode or "auto").lower()
    dynamic_modern = generate_dynamic_credentials(uuid, modern=True)
    dynamic_legacy = generate_dynamic_credentials(uuid, modern=False)
    remote_static = generate_remote_static_credentials(uuid)
    remote_modern = _as_remote_client(dynamic_modern)
    remote_legacy = _as_remote_client(dynamic_legacy)
    statics = [
        generate_static_credentials(uuid, flavor="vidaa_common"),
        generate_static_credentials(uuid, flavor="normal"),
        generate_static_credentials(uuid, flavor="bare"),
    ]
    if mode == "static":
        return [*statics, remote_static]
    if mode == "dynamic":
        return [dynamic_modern, dynamic_legacy, remote_modern, remote_legacy]
    return [
        dynamic_modern,
        dynamic_legacy,
        *statics,
        remote_modern,
        remote_legacy,
        remote_static,
    ]
