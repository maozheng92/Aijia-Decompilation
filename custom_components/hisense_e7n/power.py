"""Resolve the Home Assistant service used to physically power the TV on.

The Aijia app (and VIDAA MQTT) cannot wake a fully powered-off E7N Pro:
the broker on TCP 36669 is down, so KEY_POWER never leaves the phone.
A local button / input_button / switch / script is what actually turns it on.
"""

from __future__ import annotations

PRESS_DOMAINS = frozenset({"button", "input_button"})
TURN_ON_DOMAINS = frozenset({"switch", "script", "scene", "input_boolean", "automation"})
POWER_ON_DOMAINS = tuple(sorted(PRESS_DOMAINS | TURN_ON_DOMAINS))


def normalize_power_on_entity(entity_id: str | None) -> str | None:
    if not entity_id:
        return None
    value = str(entity_id).strip()
    if not value or "." not in value:
        return None
    return value


def power_on_service(entity_id: str) -> tuple[str, str]:
    """Return (domain, service) to invoke for the configured power-on entity."""
    normalized = normalize_power_on_entity(entity_id)
    if normalized is None:
        raise ValueError("power-on entity is empty")
    domain = normalized.split(".", 1)[0]
    if domain in PRESS_DOMAINS:
        return domain, "press"
    if domain in TURN_ON_DOMAINS:
        return domain, "turn_on"
    raise ValueError(f"unsupported power-on domain: {domain}")
