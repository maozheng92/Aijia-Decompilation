"""Local VIDAA MQTT client for Hisense E7N Pro.

Talks to the TV's own broker on TCP 36669 (MQTT 3.1.1 over TLS).
No Hisense cloud, no extra Mosquitto bridge.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt

from . import topics
from .certs_util import build_ssl_context
from .const import DEFAULT_PORT, MQTT_KEEPALIVE
from .credentials import MqttCredentials, credentials_for_mode, normalize_uuid
from .keys import KEY_POWER, normalize_key

_LOGGER = logging.getLogger(__name__)

CONNECT_PAYLOAD = {
    "app_version": 2,
    "connect_result": 0,
    "device_type": "Home Assistant",
}


def _paho_client(client_id: str) -> mqtt.Client:
    callback_api = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api is not None:
        try:
            return mqtt.Client(
                callback_api_version=callback_api.VERSION1,
                client_id=client_id,
                protocol=mqtt.MQTTv311,
                clean_session=True,
            )
        except (TypeError, ValueError):
            return mqtt.Client(
                callback_api_version=callback_api.VERSION2,
                client_id=client_id,
                protocol=mqtt.MQTTv311,
            )
    return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311, clean_session=True)


def _rc_failed(reason_code: Any) -> bool:
    if hasattr(reason_code, "is_failure"):
        return bool(reason_code.is_failure)
    return int(reason_code) != 0


def _rc_value(reason_code: Any) -> int:
    if hasattr(reason_code, "value"):
        try:
            return int(reason_code.value)
        except (TypeError, ValueError):
            pass
    try:
        return int(reason_code)
    except (TypeError, ValueError):
        return -1


def send_wol(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    mac_bytes = bytes.fromhex(normalize_uuid(mac).replace(":", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))


def _loads(payload: bytes | str) -> Any:
    if payload is None:
        return None
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace").strip()
    else:
        text = str(payload).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


@dataclass
class TvState:
    available: bool = False
    power_on: bool = False
    volume: int | None = None
    muted: bool = False
    statetype: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    sources: list[dict[str, str]] = field(default_factory=list)
    apps: list[dict[str, Any]] = field(default_factory=list)
    auth_mode: str | None = None
    last_error: str | None = None
    needs_pin: bool = False
    already_paired: bool = False
    access_token: str | None = None
    refresh_token: str | None = None


class HisenseTvClient:
    """Threaded paho client with asyncio-friendly helpers."""

    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        uuid: str,
        tv_mac: str | None = None,
        auth_mode: str = "auto",
        certfile: str | None = None,
        keyfile: str | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.uuid = normalize_uuid(uuid)
        self.tv_mac = tv_mac
        self.auth_mode = auth_mode
        self.certfile = certfile
        self.keyfile = keyfile
        self._loop = loop
        self.state = TvState()
        self._listeners: list[Callable[[TvState], None]] = []
        self._client: mqtt.Client | None = None
        self._creds: MqttCredentials | None = None
        self._stop = threading.Event()
        self._connected_event: asyncio.Event | None = None
        self._pin_event: asyncio.Event | None = None
        self._token_event: asyncio.Event | None = None
        self._connect_rc: int = -1
        self._lock = threading.Lock()

    @property
    def creds(self) -> MqttCredentials | None:
        return self._creds

    def add_listener(self, callback: Callable[[TvState], None]) -> None:
        self._listeners.append(callback)

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _notify(self) -> None:
        state = self.state
        for listener in list(self._listeners):
            try:
                listener(state)
            except Exception:  # noqa: BLE001 — listener errors must not kill MQTT
                _LOGGER.exception("State listener failed")

    def _set_loop_event(self, event: asyncio.Event | None) -> None:
        if event is None:
            return
        loop = self._loop
        if loop is None:
            event.set()
            return
        loop.call_soon_threadsafe(event.set)

    def _apply_volume(self, data: Any) -> None:
        if data is None:
            return
        payload = data
        if isinstance(data, list) and data:
            payload = data[0]
        if isinstance(payload, (int, float, str)) and str(payload).isdigit():
            self.state.volume = int(payload)
            return
        if not isinstance(payload, dict):
            return
        for key in ("volume_value", "volume", "vol"):
            if key in payload and payload[key] is not None:
                try:
                    self.state.volume = int(payload[key])
                except (TypeError, ValueError):
                    pass
                break
        mute = payload.get("mute", payload.get("mute_status"))
        if mute is not None:
            self.state.muted = str(mute) in {"1", "true", "True", "on"} or mute is True

    def _apply_state(self, data: Any) -> None:
        if not isinstance(data, dict):
            if isinstance(data, str) and data:
                self.state.statetype = data
                self.state.power_on = True
            return
        self.state.statetype = data.get("statetype") or data.get("state")
        name = data.get("sourcename") or data.get("source_name")
        sid = data.get("sourceid") or data.get("source_id")
        if name:
            self.state.source_name = str(name)
        if sid is not None:
            self.state.source_id = str(sid)
        self.state.power_on = True
        self._apply_volume(data)

    def _apply_sources(self, data: Any) -> None:
        items = data
        if isinstance(data, dict):
            items = data.get("source_list") or data.get("sourcelist") or data.get("list") or []
        if not isinstance(items, list):
            return
        sources: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sid = item.get("sourceid", item.get("source_id", item.get("id")))
            name = item.get("sourcename", item.get("source_name", item.get("name", sid)))
            if sid is None:
                continue
            sources.append({"id": str(sid), "name": str(name)})
        if sources:
            self.state.sources = sources

    def _apply_apps(self, data: Any) -> None:
        items = data
        if isinstance(data, dict):
            items = data.get("app_list") or data.get("applist") or data.get("list") or []
        if not isinstance(items, list):
            return
        apps = [item for item in items if isinstance(item, dict)]
        if apps:
            self.state.apps = apps

    def _handle_message(self, topic: str, payload: bytes) -> None:
        data = _loads(payload)
        _LOGGER.debug("MQTT %s <- %s", topic, data)
        if topic.endswith("/data/authentication") or topic.endswith("/data/authenticationcodetoast"):
            self.state.needs_pin = not self.state.already_paired
            self._set_loop_event(self._pin_event)
        elif topic.endswith("/actions/vidaa_app_connect") or topic.endswith("/data/vidaa_app_connect"):
            result = data.get("connect_result") if isinstance(data, dict) else None
            if result in (1, "1"):
                self.state.already_paired = True
                self.state.needs_pin = False
            self._set_loop_event(self._pin_event)
        elif topic.endswith("/data/tokenissuance"):
            if isinstance(data, dict):
                self.state.access_token = data.get("accesstoken")
                self.state.refresh_token = data.get("refreshtoken")
            self.state.already_paired = True
            self.state.needs_pin = False
            self._set_loop_event(self._token_event)
            self._set_loop_event(self._pin_event)
        elif topic.endswith("/data/state") or topic.endswith("/ui_service/state"):
            self._apply_state(data)
        elif topic.endswith("/data/sourcelist"):
            self._apply_sources(data)
        elif topic.endswith("/data/applist"):
            self._apply_apps(data)
        elif "volume" in topic:
            self._apply_volume(data)
        self._notify()

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        self._connect_rc = _rc_value(reason_code)
        if _rc_failed(reason_code):
            _LOGGER.warning("MQTT CONNECT refused rc=%s", reason_code)
            self.state.available = False
            self.state.last_error = f"mqtt_rc_{self._connect_rc}"
            self._set_loop_event(self._connected_event)
            return
        _LOGGER.info("Connected to %s:%s as %s", self.host, self.port, self._creds.client_id if self._creds else "")
        self.state.available = True
        self.state.power_on = True
        self.state.last_error = None
        if self._creds:
            for topic in topics.subscription_topics(self._creds):
                client.subscribe(topic, qos=0)
        self._set_loop_event(self._connected_event)
        self._notify()
        if self._creds:
            self._publish(topics.gettvstate(self._creds), "")
            self._publish(topics.getvolume(self._creds), "")
            self._publish(topics.sourcelist(self._creds), "")
            self._publish(topics.applist(self._creds), "")

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, *args: Any, **kwargs: Any) -> None:
        reason_code: Any = 0
        for item in args:
            if hasattr(item, "is_failure") or isinstance(item, int):
                reason_code = item
                break
        _LOGGER.info("Disconnected from TV rc=%s", reason_code)
        self.state.available = False
        self.state.power_on = False
        self._notify()

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            self._handle_message(message.topic, message.payload)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed handling MQTT message on %s", message.topic)

    def _publish(self, topic: str, payload: Any) -> None:
        if self._client is None:
            raise RuntimeError("MQTT client is not connected")
        if payload is None:
            body: str | bytes = ""
        elif isinstance(payload, (dict, list)):
            body = json.dumps(payload, separators=(",", ":"))
        else:
            body = str(payload)
        info = self._client.publish(topic, body, qos=0, retain=False)
        _LOGGER.debug("MQTT %s -> %s", topic, body)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Publish failed rc={info.rc} topic={topic}")

    def _try_connect(self, creds: MqttCredentials) -> int:
        self._creds = creds
        client = _paho_client(creds.client_id)
        client.username_pw_set(creds.username, creds.password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        context = build_ssl_context(self.certfile, self.keyfile)
        client.tls_set_context(context)
        client.tls_insecure_set(True)
        self._client = client
        self._connect_rc = -1
        try:
            client.connect(self.host, self.port, keepalive=MQTT_KEEPALIVE)
        except ssl.SSLError as err:
            _LOGGER.warning("TLS handshake failed: %s", err)
            return 99
        except OSError as err:
            _LOGGER.warning("TCP connect failed: %s", err)
            return 98
        client.loop_start()
        # on_connect will set _connect_rc; wait briefly for CONNACK.
        for _ in range(50):
            if self._connect_rc != -1:
                break
            threading.Event().wait(0.1)
        return self._connect_rc

    def connect_blocking(self) -> MqttCredentials:
        """Try credential candidates until CONNECT is accepted."""
        self._stop.clear()
        last_error: str | None = None
        for creds in credentials_for_mode(self.auth_mode, self.uuid):
            _LOGGER.debug("Trying MQTT auth mode %s client_id=%s", creds.mode, creds.client_id)
            if self._client is not None:
                try:
                    self._client.loop_stop()
                    self._client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                self._client = None
            rc = self._try_connect(creds)
            if rc == 0:
                self.state.auth_mode = creds.mode
                self.state.last_error = None
                return creds
            last_error = f"mqtt_rc_{rc}"
            self.state.last_error = last_error
        self.disconnect_blocking()
        raise ConnectionError(last_error or "cannot_connect")

    async def async_connect(self) -> MqttCredentials:
        loop = asyncio.get_running_loop()
        self.attach_loop(loop)
        self._connected_event = asyncio.Event()
        return await loop.run_in_executor(None, self.connect_blocking)

    def disconnect_blocking(self) -> None:
        self._stop.set()
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        try:
            client.loop_stop()
        except Exception:  # noqa: BLE001
            pass
        self.state.available = False

    async def async_disconnect(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.disconnect_blocking)

    def _require_creds(self) -> MqttCredentials:
        if self._creds is None:
            raise RuntimeError("Not connected")
        return self._creds

    def send_key(self, key: str) -> None:
        creds = self._require_creds()
        self._publish(topics.sendkey(creds), normalize_key(key))

    def set_volume(self, volume: int) -> None:
        creds = self._require_creds()
        volume = max(0, min(100, int(volume)))
        self._publish(topics.changevolume(creds), str(volume))
        self.state.volume = volume

    def change_source(self, source_id: str, source_name: str | None = None) -> None:
        creds = self._require_creds()
        payload: dict[str, str] = {"sourceid": str(source_id)}
        if source_name:
            payload["sourcename"] = source_name
        self._publish(topics.changesource(creds), payload)

    def launch_app(self, name: str, url: str | None = None) -> None:
        creds = self._require_creds()
        payload = {
            "name": name,
            "urlType": 37,
            "storeType": 0,
            "url": url or name.lower().replace(" ", ""),
        }
        self._publish(topics.launchapp(creds), payload)

    def refresh_status(self) -> None:
        creds = self._require_creds()
        self._publish(topics.gettvstate(creds), "")
        self._publish(topics.getvolume(creds), "")

    def start_pairing(self) -> None:
        creds = self._require_creds()
        self._publish(
            topics.login_each_other_info(creds),
            {
                "type": "login",
                "tvLogin": False,
                "tvDeviceId": "",
                "tvCountry": "",
                "mobileLogin": True,
                "mobileDeviceId": self.uuid,
            },
        )
        self._publish(topics.vidaa_app_connect(creds), CONNECT_PAYLOAD)

    def submit_pin(self, pin: str) -> None:
        creds = self._require_creds()
        self._publish(topics.authenticationcode(creds), {"authNum": str(pin).strip()})

    async def async_pair(self, pin_timeout: float = 8.0) -> TvState:
        """Trigger the on-screen PIN (or detect an already-paired UUID)."""
        loop = asyncio.get_running_loop()
        self._pin_event = asyncio.Event()
        await loop.run_in_executor(None, self.start_pairing)
        try:
            await asyncio.wait_for(self._pin_event.wait(), timeout=pin_timeout)
        except TimeoutError:
            # No PIN push — try a volume probe; success means already authorized.
            try:
                await loop.run_in_executor(None, self.refresh_status)
                await asyncio.sleep(1.2)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Status probe after pairing timeout failed", exc_info=True)
        return self.state

    async def async_submit_pin(self, pin: str, timeout: float = 15.0) -> TvState:
        loop = asyncio.get_running_loop()
        self._token_event = asyncio.Event()
        await loop.run_in_executor(None, self.submit_pin, pin)
        try:
            await asyncio.wait_for(self._token_event.wait(), timeout=timeout)
        except TimeoutError as err:
            raise TimeoutError("PIN not accepted") from err
        return self.state

    async def async_send_key(self, key: str) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.send_key, key)

    async def async_set_volume(self, volume: int) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.set_volume, volume)

    async def async_change_source(self, source_id: str, source_name: str | None = None) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, self.change_source, source_id, source_name
        )

    async def async_launch_app(self, name: str, url: str | None = None) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.launch_app, name, url)

    async def async_wait_for_broker(self) -> bool:
        """Retry MQTT after a physical power-on (button / WoL)."""
        if self.state.available:
            return True
        for delay in (3, 5, 8, 13, 21):
            await asyncio.sleep(delay)
            try:
                await self.async_connect()
                return True
            except ConnectionError:
                _LOGGER.debug("TV broker not up yet, retrying")
        return False

    async def async_turn_on(self) -> None:
        """Wake via Wake-on-LAN when no HA button is configured."""
        if self.state.available:
            return
        if self.tv_mac:
            await asyncio.get_running_loop().run_in_executor(None, send_wol, self.tv_mac)
            await self.async_wait_for_broker()
            return
        _LOGGER.warning(
            "Cannot wake TV: configure a power-on button entity (Aijia cannot power on a dead TV)"
        )

    async def async_turn_off(self) -> None:
        if self.state.available:
            await self.async_send_key(KEY_POWER)

    async def async_toggle_mute(self) -> None:
        await self.async_send_key("KEY_MUTE")
        self.state.muted = not self.state.muted
        self._notify()
