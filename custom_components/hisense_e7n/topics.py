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


def subscription_topics(creds: MqttCredentials) -> list[str]:
    return [
        _mobile_data(creds, "ui_service", "authentication"),
        _mobile_data(creds, "ui_service", "authenticationcodetoast"),
        _mobile_data(creds, "ui_service", "authenticationcodeclose"),
        _mobile_data(creds, "ui_service", "tokenissuance"),
        _mobile_data(creds, "ui_service", "state"),
        _mobile_data(creds, "ui_service", "sourcelist"),
        _mobile_data(creds, "ui_service", "applist"),
        _mobile_data(creds, "ui_service", "vidaa_app_connect"),
        _mobile_data(creds, "platform_service", "volume"),
        _mobile_data(creds, "platform_service", "tokenissuance"),
        "/remoteapp/mobile/broadcast/ui_service/state",
        "/remoteapp/mobile/broadcast/platform_service/data/volumechange",
        "/remoteapp/mobile/broadcast/platform_service/volume",
    ]
