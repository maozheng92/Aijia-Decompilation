"""User-defined TV inputs switched by a remoter key sequence.

Example (options text)::

    HDMI1: KEY_SOURCE, KEY_RIGHT, KEY_OK
    HDMI2: source, right, right, ok
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .keys import normalize_key

_NAME_SPLIT = re.compile(r"\s*[:：|＝=]\s*", re.UNICODE)
_KEY_SPLIT = re.compile(r"[\s,，、+/|]+")


def parse_custom_sources_text(text: str | None) -> list[dict[str, Any]]:
    """Parse ``Name: key, key, key`` lines into ``[{name, keys}]``."""
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _NAME_SPLIT.search(line):
            name, rest = _NAME_SPLIT.split(line, maxsplit=1)
        else:
            parts = line.split(None, 1)
            if len(parts) < 2:
                raise ValueError(f"invalid custom source line: {raw}")
            name, rest = parts
        name = name.strip()
        if not name:
            raise ValueError(f"empty custom source name: {raw}")
        keys = parse_key_sequence(rest)
        if not keys:
            raise ValueError(f"custom source {name!r} needs at least one key")
        if name in seen:
            raise ValueError(f"duplicate custom source name: {name}")
        seen.add(name)
        sources.append({"name": name, "keys": keys})
    return sources


def parse_key_sequence(text: str | None) -> list[str]:
    """Normalize a free-form key list into wire KEY_* names."""
    keys: list[str] = []
    for part in _KEY_SPLIT.split(str(text or "").strip()):
        token = part.strip()
        if not token:
            continue
        keys.append(normalize_key(token))
    return keys


def serialize_custom_sources(sources: list[dict[str, Any]] | None) -> str:
    """Render sources back to the options multiline text."""
    lines: list[str] = []
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        keys = item.get("keys") or []
        if not name or not isinstance(keys, list) or not keys:
            continue
        lines.append(f"{name}: {', '.join(str(key) for key in keys)}")
    return "\n".join(lines)


def normalize_custom_sources(value: Any) -> list[dict[str, Any]]:
    """Accept stored list/dict/text and return a clean ``[{name, keys}]``."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return parse_custom_sources_text(value)
    if isinstance(value, dict):
        # {"HDMI1": ["KEY_SOURCE", "KEY_OK"]} or {"HDMI1": "source, ok"}
        items = [{"name": key, "keys": keys} for key, keys in value.items()]
        return normalize_custom_sources(items)
    if not isinstance(value, list):
        raise ValueError("custom_sources must be a list or text")
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            parsed = parse_custom_sources_text(item)
            for entry in parsed:
                if entry["name"] in seen:
                    raise ValueError(f"duplicate custom source name: {entry['name']}")
                seen.add(entry["name"])
                sources.append(entry)
            continue
        if not isinstance(item, dict):
            raise ValueError(f"invalid custom source: {item!r}")
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("custom source name is required")
        raw_keys = item.get("keys")
        if isinstance(raw_keys, str):
            keys = parse_key_sequence(raw_keys)
        elif isinstance(raw_keys, list):
            keys = parse_key_sequence(",".join(str(part) for part in raw_keys))
        else:
            raise ValueError(f"custom source {name!r} needs keys")
        if not keys:
            raise ValueError(f"custom source {name!r} needs at least one key")
        if name in seen:
            raise ValueError(f"duplicate custom source name: {name}")
        seen.add(name)
        sources.append({"name": name, "keys": keys})
    return sources


def custom_source_slug(name: str) -> str:
    """Stable unique-id fragment for a custom source name."""
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    if ascii_part:
        return f"{ascii_part}_{digest}"
    return f"custom_{digest}"


def find_custom_source(
    sources: list[dict[str, Any]], name: str
) -> dict[str, Any] | None:
    needle = name.strip()
    for item in sources:
        if item.get("name") == needle:
            return item
    return None
