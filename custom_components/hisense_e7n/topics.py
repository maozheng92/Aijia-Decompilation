"""VIDAA ``/remoteapp/`` topic helpers.

Wildcards are unreliable on some firmware, so the client subscribes
to the concrete topics listed here.
"""

from __future__ import annotations

from .credentials import MqttCredentials


def _tv_action(creds: MqttCredentials, service: str, action: str) -> str:
    return f"/remoteapp/tv/{service}/{creds.client_id}/actions/{action}"


def _mobile_data(creds: MqttCredentials, service: str, data_type: str) -> str:
    return f"/remoteapp/mobile/{creds.client_id}/{service}/data/{data_type}"


def command_identities(creds: MqttCredentials, tv_mac: str | None = None) -> list[str]:
    """Topic identity the broker actually routes.

    sendkey is delivered only to the ``client_id`` of this MQTT session
    (``{uuid}$his${hash}_vidaacommon_001`` or the static ``$vidaa_common`` /
    ``$normal`` id we connected with). The TV Wi-Fi MAC is not that id.
    ``tv_mac`` is accepted so older callers keep working and is not used.
    """
    del tv_mac
    client_id = (creds.client_id or "").strip()
    return [client_id] if client_id else []


def action_topics(
    creds: MqttCredentials,
    service: str,
    action: str,
    tv_mac: str | None = None,
) -> list[str]:
    return [
        f"/remoteapp/tv/{service}/{ident}/actions/{action}"
        for ident in command_identities(creds, tv_mac)
    ]


def sendkey(creds: MqttCredentials) -> str:
    return _tv_action(creds, "remote_service", "sendkey")


def gettvstate(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "gettvstate")


def sourcelist(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "sourcelist")


def changesource(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "changesource")


def launchapp(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "launchapp")


def applist(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "applist")


def vidaa_app_connect(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "vidaa_app_connect")


def authenticationcode(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "authenticationcode")


def login_each_other_info(creds: MqttCredentials) -> str:
    return _tv_action(creds, "ui_service", "login_each_other_info")


def getvolume(creds: MqttCredentials) -> str:
    return _tv_action(creds, "platform_service", "getvolume")


def changevolume(creds: MqttCredentials) -> str:
    return _tv_action(creds, "platform_service", "changevolume")


_MOBILE_DATA = (
    ("ui_service", "authentication"),
    ("ui_service", "authenticationcodetoast"),
    ("ui_service", "authenticationcodeclose"),
    ("ui_service", "tokenissuance"),
    ("ui_service", "state"),
    ("ui_service", "sourcelist"),
    ("ui_service", "applist"),
    ("ui_service", "vidaa_app_connect"),
    ("platform_service", "volume"),
    ("platform_service", "tokenissuance"),
)

_BROADCASTS = (
    "/remoteapp/mobile/broadcast/ui_service/state",
    "/remoteapp/mobile/broadcast/platform_service/data/volumechange",
    "/remoteapp/mobile/broadcast/platform_service/actions/volumechange",
    "/remoteapp/mobile/broadcast/platform_service/volume",
)


def subscription_topics(creds: MqttCredentials, tv_mac: str | None = None) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for ident in command_identities(creds, tv_mac):
        for service, data_type in _MOBILE_DATA:
            topic = f"/remoteapp/mobile/{ident}/{service}/data/{data_type}"
            if topic not in seen:
                seen.add(topic)
                topics.append(topic)
    for topic in _BROADCASTS:
        if topic not in seen:
            topics.append(topic)
    return topics
