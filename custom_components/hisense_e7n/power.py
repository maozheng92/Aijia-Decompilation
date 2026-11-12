"""Resolve the Home Assistant service used to physically power the TV on.

爱家 cannot wake a fully off E7N Pro: MQTT on TCP 36669 is down, so KEY_POWER
never arrives. Each TV stores its own power-on action, the same way the
official Sony integration stores a per-device wake method:

* a button / switch / script (``button.press`` or ``turn_on``)
* an infrared remote (``remote.send_command``)
* Wake-on-LAN, only when a Wi-Fi MAC is set
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_POWER_ON_BUTTON,
    CONF_POWER_ON_COMMAND,
    CONF_POWER_ON_DEVICE,
    CONF_POWER_ON_MODE,
    CONF_POWER_ON_REMOTE,
    DEFAULT_POWER_ON_COMMAND,
    POWER_ON_MODE_BUTTON,
    POWER_ON_MODE_REMOTE,
    POWER_ON_MODE_WOL,
)

PRESS_DOMAINS = frozenset({"button", "input_button"})
TURN_ON_DOMAINS = frozenset({"switch", "script", "scene", "input_boolean", "automation"})
POWER_ON_DOMAINS = tuple(sorted(PRESS_DOMAINS | TURN_ON_DOMAINS))
REMOTE_DOMAIN = "remote"
POWER_ON_MODES = (POWER_ON_MODE_BUTTON, POWER_ON_MODE_REMOTE, POWER_ON_MODE_WOL)


def normalize_power_on_entity(entity_id: str | None) -> str | None:
    if not entity_id:
        return None
    value = str(entity_id).strip()
    if not value or "." not in value:
        return None
    return value


def power_on_service(entity_id: str) -> tuple[str, str]:
    """Return (domain, service) to invoke for a button / switch / script."""
    normalized = normalize_power_on_entity(entity_id)
    if normalized is None:
        raise ValueError("power-on entity is empty")
    domain = normalized.split(".", 1)[0]
    if domain in PRESS_DOMAINS:
        return domain, "press"
    if domain in TURN_ON_DOMAINS:
        return domain, "turn_on"
    raise ValueError(f"unsupported power-on domain: {domain}")


def infer_power_on_mode(
    mode: str | None,
    button: str | None,
    remote: str | None,
    mac: str | None,
) -> str:
    """Pick a mode for entries saved before the IR remote field existed."""
    if mode in POWER_ON_MODES:
        return mode
    if normalize_power_on_entity(button):
        return POWER_ON_MODE_BUTTON
    if normalize_power_on_entity(remote):
        return POWER_ON_MODE_REMOTE
    if (mac or "").strip():
        return POWER_ON_MODE_WOL
    return POWER_ON_MODE_BUTTON


@dataclass(frozen=True)
class PowerOnCall:
    """One Home Assistant service call that physically turns the TV on."""

    domain: str
    service: str
    data: dict[str, Any]


def power_on_call(
    mode: str | None,
    button: str | None,
    remote: str | None,
    command: str | None,
    device: str | None = None,
    mac: str | None = None,
) -> PowerOnCall | None:
    """Build the service call for button or IR remote. Wake-on-LAN returns None."""
    chosen = infer_power_on_mode(mode, button, remote, mac)
    if chosen == POWER_ON_MODE_REMOTE:
        entity = normalize_power_on_entity(remote)
        if entity is None or not entity.startswith(f"{REMOTE_DOMAIN}."):
            return None
        name = (command or "").strip() or DEFAULT_POWER_ON_COMMAND
        payload: dict[str, Any] = {"entity_id": entity, "command": [name]}
        device_name = (device or "").strip()
        if device_name:
            payload["device"] = device_name
        return PowerOnCall(REMOTE_DOMAIN, "send_command", payload)
    if chosen == POWER_ON_MODE_BUTTON:
        entity = normalize_power_on_entity(button)
        if entity is None:
            return None
        try:
            domain, service = power_on_service(entity)
        except ValueError:
            return None
        return PowerOnCall(domain, service, {"entity_id": entity})
    return None


def power_on_form_errors(data: dict[str, Any]) -> dict[str, str]:
    """Validate the per-TV power-on fields. Empty button mode is allowed."""
    mode = data.get(CONF_POWER_ON_MODE) or POWER_ON_MODE_BUTTON
    errors: dict[str, str] = {}
    if mode == POWER_ON_MODE_REMOTE:
        remote = normalize_power_on_entity(data.get(CONF_POWER_ON_REMOTE))
        if remote is None or not remote.startswith(f"{REMOTE_DOMAIN}."):
            errors[CONF_POWER_ON_REMOTE] = "power_on_required"
        if not str(data.get(CONF_POWER_ON_COMMAND) or "").strip():
            errors[CONF_POWER_ON_COMMAND] = "power_on_required"
    elif mode == POWER_ON_MODE_WOL and not str(data.get("mac") or "").strip():
        errors["mac"] = "power_on_required"
    return errors


def clean_power_on_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize stored power-on values before they are written to the entry."""
    cleaned = dict(data)
    cleaned[CONF_POWER_ON_BUTTON] = normalize_power_on_entity(data.get(CONF_POWER_ON_BUTTON)) or ""
    cleaned[CONF_POWER_ON_REMOTE] = normalize_power_on_entity(data.get(CONF_POWER_ON_REMOTE)) or ""
    command = str(data.get(CONF_POWER_ON_COMMAND) or "").strip()
    cleaned[CONF_POWER_ON_COMMAND] = command or DEFAULT_POWER_ON_COMMAND
    cleaned[CONF_POWER_ON_DEVICE] = str(data.get(CONF_POWER_ON_DEVICE) or "").strip()
    cleaned[CONF_POWER_ON_MODE] = infer_power_on_mode(
        data.get(CONF_POWER_ON_MODE),
        cleaned[CONF_POWER_ON_BUTTON],
        cleaned[CONF_POWER_ON_REMOTE],
        data.get("mac"),
    )
    return cleaned
