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
from .const import (
    DEFAULT_PORT,
    MQTT_CONNACK_WAIT,
    MQTT_CONNECT_TIMEOUT,
    MQTT_KEEPALIVE,
    RC_TCP_FAILED,
    RC_TLS_FAILED,
)
from .credentials import (
    MqttCredentials,
    credentials_for_mode,
    normalize_uuid,
)
from .keys import KEY_POWER, KEY_SOURCE, normalize_key

_LOGGER = logging.getLogger(__name__)

CONNECT_PAYLOAD = {
    "app_version": 2,
    "connect_result": 0,
    "device_type": "VIDAALiteMQTT",
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


def classify_connect_error(message: str) -> str:
    """Map ConnectionError text to a config-flow error key."""
    text = (message or "").lower()
    if "mqtt_rc_5" in text or "not_authorized" in text:
        return "not_authorized"
    if "mqtt_rc_99" in text or "tls" in text:
        return "tls_failed"
    if "tcp_timeout" in text or "timed out" in text or "mqtt_rc_-1" in text:
        return "timeout"
    if "tcp_refused" in text or "connection refused" in text:
        return "cannot_connect"
    return "cannot_connect"


def probe_tcp(host: str, port: int, timeout: float = MQTT_CONNECT_TIMEOUT) -> None:
    """Fail fast if 36669 is not reachable before starting MQTT/TLS."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return
    except TimeoutError as err:
        raise ConnectionError("tcp_timeout") from err
    except ConnectionRefusedError as err:
        raise ConnectionError("tcp_refused") from err
    except OSError as err:
        raise ConnectionError(f"tcp_failed:{err}") from err


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
        cert_pairs: list[tuple[str | None, str | None]] | None = None,
        use_ssl: bool | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.uuid = normalize_uuid(uuid)
        self.tv_mac = tv_mac
        self.auth_mode = auth_mode
        self.certfile = certfile
        self.keyfile = keyfile
        self.cert_pairs = cert_pairs or ([(certfile, keyfile)] if certfile and keyfile else [(None, None)])
        self.use_ssl = use_ssl
        self.transport: str | None = None
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
        self._maybe_learn_tv_mac(data)

    def _maybe_learn_tv_mac(self, data: Any) -> None:
        if self.tv_mac or not isinstance(data, dict):
            return
        for key in ("mac", "MAC", "tv_mac", "devicemac", "deviceMac"):
            value = data.get(key)
            if not value:
                continue
            try:
                self.tv_mac = normalize_uuid(str(value))
                _LOGGER.info("Learned TV MAC %s from MQTT state", self.tv_mac)
                return
            except ValueError:
                continue

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
            for topic in topics.subscription_topics(self._creds, self.tv_mac):
                client.subscribe(topic, qos=0)
        self._set_loop_event(self._connected_event)
        self._notify()
        if self._creds:
            try:
                self.start_pairing()
            except Exception:  # noqa: BLE001 — announce must not break CONNECT
                _LOGGER.debug("Client announce after CONNECT failed", exc_info=True)
            self._publish_action("ui_service", "gettvstate", "")
            self._publish_action("platform_service", "getvolume", "")
            self._publish_action("ui_service", "sourcelist", "")
            self._publish_action("ui_service", "applist", "")

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

    def _publish(self, topic: str, payload: Any, *, wait: bool = False) -> None:
        if self._client is None:
            raise RuntimeError("MQTT client is not connected")
        if payload is None:
            body: str | bytes = ""
        elif isinstance(payload, (dict, list)):
            body = json.dumps(payload, separators=(",", ":"))
        else:
            body = str(payload)
        info = self._client.publish(topic, body, qos=1, retain=False)
        _LOGGER.debug("MQTT %s -> %s", topic, body)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Publish failed rc={info.rc} topic={topic}")
        if not wait:
            return
        wait_fn = getattr(info, "wait_for_publish", None)
        if not callable(wait_fn):
            return
        try:
            wait_fn(timeout=1.5)
        except TypeError:
            # paho 1.x wait_for_publish() has no timeout; do not block HA.
            return
        except Exception:  # noqa: BLE001 — some brokers never ack QoS 0
            return

    def _stop_client(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client.loop_stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _try_connect(
        self,
        creds: MqttCredentials,
        *,
        use_tls: bool,
        certfile: str | None,
        keyfile: str | None,
    ) -> int:
        self._creds = creds
        client = _paho_client(creds.client_id)
        client.username_pw_set(creds.username, creds.password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client._connect_timeout = MQTT_CONNECT_TIMEOUT  # noqa: SLF001 — paho 2.x
        if use_tls:
            context = build_ssl_context(certfile, keyfile)
            client.tls_set_context(context)
            # Do not call tls_insecure_set: it can rebuild the context and
            # wipe SECLEVEL=0 / the client chain on some paho versions.
        self._client = client
        self._connect_rc = -1
        try:
            client.connect(self.host, self.port, keepalive=MQTT_KEEPALIVE)
        except ssl.SSLError as err:
            _LOGGER.warning("TLS handshake failed (%s cert=%s): %s", creds.mode, certfile, err)
            self._stop_client()
            return RC_TLS_FAILED
        except TimeoutError as err:
            _LOGGER.warning("MQTT TCP timed out: %s", err)
            self._stop_client()
            return RC_TCP_FAILED
        except OSError as err:
            _LOGGER.warning("TCP connect failed: %s", err)
            self._stop_client()
            return RC_TCP_FAILED
        client.loop_start()
        steps = max(1, int(MQTT_CONNACK_WAIT / 0.1))
        for _ in range(steps):
            if self._connect_rc != -1:
                break
            threading.Event().wait(0.1)
        return self._connect_rc

    def _credential_sets(self, use_tls: bool) -> list[MqttCredentials]:
        mode = "static" if not use_tls else self.auth_mode
        candidates = credentials_for_mode(mode, self.uuid)
        mac = (self.tv_mac or "").strip()
        if mac:
            try:
                extra = credentials_for_mode(mode, mac)
            except ValueError:
                extra = []
            for creds in extra:
                if all(creds.client_id != item.client_id for item in candidates):
                    candidates.append(creds)
        return candidates

    def _transports(self) -> list[tuple[str, bool, str | None, str | None]]:
        if self.use_ssl is False:
            return [("plain", False, None, None)]
        transports: list[tuple[str, bool, str | None, str | None]] = []
        for certfile, keyfile in self.cert_pairs:
            label = "tls" if certfile else "tls_anon"
            transports.append((label, True, certfile, keyfile))
        if not any(item[2] is None for item in transports):
            transports.append(("tls_anon", True, None, None))
        if self.use_ssl is not True:
            transports.append(("plain", False, None, None))
        return transports

    def connect_blocking(self) -> MqttCredentials:
        """Probe TCP, then try TLS (爱家 cert → stand-in → none) then plaintext."""
        self._stop.clear()
        probe_tcp(self.host, self.port)
        last_error: str | None = None
        for name, use_tls, certfile, keyfile in self._transports():
            for creds in self._credential_sets(use_tls):
                _LOGGER.debug(
                    "MQTT try transport=%s auth=%s client_id=%s cert=%s",
                    name,
                    creds.mode,
                    creds.client_id,
                    certfile,
                )
                self._stop_client()
                rc = self._try_connect(creds, use_tls=use_tls, certfile=certfile, keyfile=keyfile)
                if rc == 0:
                    self.transport = name
                    self.certfile = certfile
                    self.keyfile = keyfile
                    self.use_ssl = use_tls
                    self.state.auth_mode = creds.mode
                    self.state.last_error = None
                    _LOGGER.info("MQTT connected via %s auth=%s", name, creds.mode)
                    return creds
                last_error = f"mqtt_rc_{rc}"
                self.state.last_error = last_error
                if rc in {RC_TCP_FAILED, RC_TLS_FAILED, -1}:
                    # Same socket/TLS setup will fail for every password.
                    break
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

    def _publish_action(
        self,
        service: str,
        action: str,
        payload: Any,
        *,
        as_key: bool = False,
    ) -> None:
        creds = self._require_creds()
        if as_key:
            name = normalize_key(str(payload))
            bodies: list[Any] = [name, {"key": name}]
        else:
            bodies = [payload]
        last_error: Exception | None = None
        sent = 0
        for topic in topics.action_topics(creds, service, action, self.tv_mac):
            for body in bodies:
                try:
                    self._publish(topic, body, wait=sent == 0)
                    sent += 1
                except RuntimeError as err:
                    last_error = err
        if sent == 0 and last_error is not None:
            raise last_error

    def send_key(self, key: str) -> None:
        kind = key.strip().lower()
        if kind in {"screenshot", "capture", "capturescreen"}:
            self.capture_screenshot()
            return
        if kind in {"smart_image", "smartimage", "ai"}:
            self.push_smart_image()
            return
        if kind in {"source", "signal"}:
            self.open_source()
            return
        self._publish_action("remote_service", "sendkey", key, as_key=True)

    def capture_screenshot(self) -> None:
        """爱家 截屏: captureTvScreen / getTvScreenInfo."""
        for action in ("captureTvScreen", "getTvScreenInfo", "gettvpic", "screenshot"):
            self._publish_action("ui_service", action, "")

    def open_source(self) -> None:
        """爱家 信号源: refresh sourcelist and send the VIDAA source key."""
        self._publish_action("ui_service", "sourcelist", "")
        self._publish_action("remote_service", "sendkey", KEY_SOURCE, as_key=True)

    def push_smart_image(self) -> None:
        """爱家 AI识图: pushSmartImage / functionSmartImage."""
        for action in ("smartimage", "pushSmartImage", "functionSmartImage"):
            self._publish_action("ui_service", action, "")

    def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        self._publish_action("platform_service", "changevolume", str(volume))
        self.state.volume = volume

    def change_source(self, source_id: str, source_name: str | None = None) -> None:
        payload: dict[str, str] = {"sourceid": str(source_id)}
        if source_name:
            payload["sourcename"] = source_name
        self._publish_action("ui_service", "changesource", payload)

    def launch_app(self, name: str, url: str | None = None) -> None:
        payload = {
            "name": name,
            "urlType": 37,
            "storeType": 0,
            "url": url or name.lower().replace(" ", ""),
        }
        self._publish_action("ui_service", "launchapp", payload)

    def refresh_status(self) -> None:
        self._publish_action("ui_service", "gettvstate", "")
        self._publish_action("platform_service", "getvolume", "")

    def start_pairing(self) -> None:
        """Announce this client. 爱家 / E7N Pro does not use an on-screen PIN."""
        self._publish_action(
            "ui_service",
            "login_each_other_info",
            {
                "type": "login",
                "tvLogin": False,
                "tvDeviceId": "",
                "tvCountry": "",
                "mobileLogin": True,
                "mobileDeviceId": self.uuid,
            },
        )
        self._publish_action("ui_service", "vidaa_app_connect", CONNECT_PAYLOAD)

    async def async_pair(self) -> TvState:
        """Register with the TV without waiting for a PIN."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.start_pairing)
        return self.state

    async def async_send_key(self, key: str) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.send_key, key)

    async def async_capture_screenshot(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.capture_screenshot)

    async def async_open_source(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.open_source)

    async def async_push_smart_image(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.push_smart_image)

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
