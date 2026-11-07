"""爱家 / Hisense BLE remoter.

Adding a TV in 海信爱家 prompts to turn Bluetooth on. The phone then talks
the Hisense BLE GATT profile (service UUID built on OUI 58:7E:61) via
flutter_blue_plus. MQTT 36669 can connect while keys do nothing because
爱家 pairing is BLE, not VIDAA sendkey.

HID usage values are from the Hisense ERF6A40 BLE remote specification.
Standard HID-over-GATT (HOGP) report characteristics are also used when
the TV exposes them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .keys import (
    KEY_CHANNELDOWN,
    KEY_CHANNELUP,
    KEY_CONTROL_CENTER,
    KEY_DOWN,
    KEY_EXIT,
    KEY_HOME,
    KEY_LEFT,
    KEY_MENU,
    KEY_MUTE,
    KEY_OK,
    KEY_PAUSE,
    KEY_PLAY,
    KEY_POWER,
    KEY_RETURNS,
    KEY_RIGHT,
    KEY_SOURCE,
    KEY_STOP,
    KEY_UP,
    KEY_VOLUMEDOWN,
    KEY_VOLUMEUP,
    normalize_key,
)

_LOGGER = logging.getLogger(__name__)

# libapp.so: 3a69{16-bit}-0000-1000-8000-00805f587e61 (Hisense OUI 58:7E:61)
HISENSE_BLE_SERVICE = "3a69180b-0000-1000-8000-00805f587e61"
HISENSE_BLE_WRITE = "3a692a12-0000-1000-8000-00805f587e61"
HISENSE_BLE_NOTIFY = "3a692a13-0000-1000-8000-00805f587e61"
HID_SERVICE = "00001812-0000-1000-8000-00805f9b34fb"
HID_REPORT = "00002a4d-0000-1000-8000-00805f9b34fb"

_NAME_HINTS = ("hisense", "vidaa", "e7n", "e7npro", "海信")


@dataclass(frozen=True)
class HidUsage:
    """Hisense BLE remote code: index, HID usage page, usage id."""

    index: int
    page: int
    usage: int


# FCC / Hisense ERF6A40 "Remote Code" table, plus Consumer Control usages
# for media keys the physical remote does not list.
HID_USAGES: dict[str, HidUsage] = {
    KEY_POWER: HidUsage(0x08, 0x0C, 0x30),
    KEY_SOURCE: HidUsage(0x0B, 0x0C, 0x1BB),
    KEY_UP: HidUsage(0x56, 0x0C, 0x42),
    KEY_DOWN: HidUsage(0x57, 0x0C, 0x43),
    KEY_LEFT: HidUsage(0x58, 0x0C, 0x44),
    KEY_RIGHT: HidUsage(0x59, 0x0C, 0x45),
    KEY_OK: HidUsage(0x5A, 0x0C, 0x41),
    KEY_RETURNS: HidUsage(0x04, 0x0C, 0x224),
    KEY_HOME: HidUsage(0x4A, 0x0C, 0x223),
    KEY_VOLUMEUP: HidUsage(0x02, 0x07, 0x80),
    KEY_VOLUMEDOWN: HidUsage(0x03, 0x07, 0x81),
    KEY_MUTE: HidUsage(0x09, 0x0C, 0xE2),
    KEY_MENU: HidUsage(0x43, 0x0C, 0x40),
    KEY_CONTROL_CENTER: HidUsage(0xE4, 0x0C, 0x9F),
    KEY_PLAY: HidUsage(0x00, 0x0C, 0xB0),
    KEY_PAUSE: HidUsage(0x00, 0x0C, 0xB1),
    KEY_STOP: HidUsage(0x00, 0x0C, 0xB7),
    KEY_CHANNELUP: HidUsage(0x00, 0x0C, 0x9C),
    KEY_CHANNELDOWN: HidUsage(0x00, 0x0C, 0x9D),
    KEY_EXIT: HidUsage(0x04, 0x0C, 0x224),
}

# FCC: key 0x44 is "BLE pairing".
HID_PAIR = HidUsage(0x44, 0x00, 0x00)


def normalize_ble_address(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().replace("-", ":").upper()
    parts = [part for part in cleaned.split(":") if part]
    if len(parts) == 1 and len(parts[0]) == 12:
        hex_str = parts[0]
        parts = [hex_str[i : i + 2] for i in range(0, 12, 2)]
    if len(parts) != 6 or any(len(part) != 2 for part in parts):
        raise ValueError(f"Invalid BLE address: {value}")
    try:
        int("".join(parts), 16)
    except ValueError as err:
        raise ValueError(f"Invalid BLE address: {value}") from err
    return ":".join(parts)


def hid_press_payload(usage: HidUsage) -> bytes:
    return bytes(
        [
            usage.index & 0xFF,
            usage.page & 0xFF,
            usage.usage & 0xFF,
            (usage.usage >> 8) & 0xFF,
        ]
    )


def hid_release_payload() -> bytes:
    return b"\x00\x00\x00\x00"


def hogp_press_payload(usage: HidUsage) -> bytes:
    return bytes([usage.usage & 0xFF, (usage.usage >> 8) & 0xFF])


def hogp_release_payload() -> bytes:
    return b"\x00\x00"


def hid_usage_for_key(key: str) -> HidUsage | None:
    return HID_USAGES.get(normalize_key(key))


def is_hisense_ble_advertisement(name: str | None, service_uuids: list[str] | None) -> bool:
    uuids = {item.lower() for item in (service_uuids or [])}
    if HISENSE_BLE_SERVICE in uuids or HID_SERVICE in uuids:
        return True
    text = (name or "").lower()
    return any(hint in text for hint in _NAME_HINTS)


def discovered_ble_addresses(hass: Any) -> list[str]:
    """BLE addresses currently seen that look like a Hisense TV / remoter."""
    try:
        from homeassistant.components import bluetooth
    except ImportError:
        return []
    scanner = getattr(bluetooth, "async_discovered_service_info", None)
    if scanner is None:
        return []
    try:
        infos = scanner(hass, connectable=True)
    except TypeError:
        infos = scanner(hass)
    found: list[str] = []
    for info in infos:
        if is_hisense_ble_advertisement(
            getattr(info, "name", None), getattr(info, "service_uuids", None)
        ):
            address = getattr(info, "address", None)
            if address and address not in found:
                found.append(address)
    return found


def _char_uuid(char: Any) -> str:
    return str(getattr(char, "uuid", char)).lower()


def _char_can_write(char: Any) -> bool:
    props = {str(item).lower().replace("_", "-") for item in getattr(char, "properties", ())}
    return bool(props & {"write", "write-without-response", "write-without-resp"})


class HisenseBleRemote:
    """BLE GATT client that sends Hisense remoter HID reports."""

    def __init__(self, hass: Any, address: str) -> None:
        self._hass = hass
        self.address = normalize_ble_address(address) or address
        self._client: Any = None
        self._vendor_char: str | None = HISENSE_BLE_WRITE
        self._hid_chars: list[str] = []

    @property
    def connected(self) -> bool:
        client = self._client
        return bool(client is not None and getattr(client, "is_connected", False))

    async def async_connect(self) -> None:
        try:
            from bleak import BleakClient
        except ImportError as err:
            raise RuntimeError(
                "bleak is missing. Enable the Home Assistant Bluetooth integration, "
                "which provides the bleak build pinned by this Core version."
            ) from err

        target: Any = self.address
        try:
            from homeassistant.components import bluetooth

            device = bluetooth.async_ble_device_from_address(
                self._hass, self.address, connectable=True
            )
            if device is not None:
                target = device
        except Exception:  # noqa: BLE001 — adapter optional at import time
            _LOGGER.debug("HA bluetooth helper unavailable, using raw address")
        try:
            client = BleakClient(target, timeout=20.0)
        except TypeError:
            client = BleakClient(target)
        try:
            await client.connect(timeout=20.0)
        except TypeError:
            await client.connect()
        if not getattr(client, "is_connected", False):
            raise RuntimeError(f"BLE connect to {self.address} did not complete")
        self._client = client
        self._inspect_services(client)
        try:
            await client.start_notify(HISENSE_BLE_NOTIFY, lambda *_args: None)
        except Exception:  # noqa: BLE001 — notify is optional
            _LOGGER.debug("BLE notify %s not available", HISENSE_BLE_NOTIFY)
        if self._vendor_char:
            try:
                await self._write(self._vendor_char, hid_press_payload(HID_PAIR))
                await asyncio.sleep(0.05)
                await self._write(self._vendor_char, hid_release_payload())
            except Exception:  # noqa: BLE001 — pairing write is best-effort
                _LOGGER.debug("BLE pairing write skipped", exc_info=True)
        _LOGGER.info("Paired Hisense TV over BLE at %s", self.address)

    def _inspect_services(self, client: Any) -> None:
        vendor = None
        hid_chars: list[str] = []
        try:
            services = getattr(client, "services", None)
            for service in services or []:
                service_uuid = str(getattr(service, "uuid", "")).lower()
                chars = getattr(service, "characteristics", None) or []
                for char in chars:
                    uuid = _char_uuid(char)
                    if uuid == HISENSE_BLE_WRITE:
                        vendor = uuid
                    if (
                        service_uuid == HID_SERVICE or uuid == HID_REPORT
                    ) and _char_can_write(char):
                        if uuid not in hid_chars:
                            hid_chars.append(uuid)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("BLE service inspect failed", exc_info=True)
        self._vendor_char = vendor or HISENSE_BLE_WRITE
        self._hid_chars = hid_chars

    async def async_disconnect(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("BLE disconnect ignored", exc_info=True)

    async def async_send_key(self, key: str) -> bool:
        usage = hid_usage_for_key(key)
        if not self.connected:
            await self.async_connect()
        if usage and self._vendor_char:
            await self._press_release(
                self._vendor_char, hid_press_payload(usage), hid_release_payload()
            )
            return True
        if usage and self._hid_chars:
            await self._press_release(
                self._hid_chars[0], hogp_press_payload(usage), hogp_release_payload()
            )
            return True
        body = normalize_key(key).encode("ascii")
        char = self._vendor_char or (self._hid_chars[0] if self._hid_chars else HISENSE_BLE_WRITE)
        await self._write(char, body)
        return True

    async def _press_release(self, char: str, press: bytes, release: bytes) -> None:
        await self._write(char, press)
        await asyncio.sleep(0.04)
        await self._write(char, release)

    async def _write(self, char: str, payload: bytes) -> None:
        client = self._client
        if client is None or not getattr(client, "is_connected", False):
            raise RuntimeError("BLE remote is not connected")
        try:
            await client.write_gatt_char(char, payload, response=False)
        except TypeError:
            await client.write_gatt_char(char, payload)
        except Exception:
            await client.write_gatt_char(char, payload, response=True)
