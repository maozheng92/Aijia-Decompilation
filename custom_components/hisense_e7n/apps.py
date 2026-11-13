"""Installed TV apps, the same list 爱家 shows under 电视应用 → 我的应用."""

from __future__ import annotations

from typing import Any

_NAME_KEYS = ("name", "appName", "appname", "title", "app_name")
_URL_KEYS = ("url", "appUrl", "appurl", "launchUrl")
_ID_KEYS = ("appId", "appid", "id", "packageName", "packagename", "package")
_LIST_KEYS = (
    "app_list",
    "applist",
    "appList",
    "list",
    "apps",
    "data",
    "myapp",
    "myApp",
    "my_app",
    "mqttAppNameList",
)
# 热门/推荐 are the store rows next to 我的应用, not the installed set.
_OTHER_GROUPS = {"recommend", "hot", "store", "banner", "ad", "推荐", "热门", "应用推荐"}


def normalize_apps(data: Any) -> list[dict[str, Any]]:
    """Return installed apps as ``{name, url, app_id, url_type, store_type}``."""
    apps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _items(data):
        app = _one_app(item)
        if app is None or app["name"] in seen:
            continue
        seen.add(app["name"])
        apps.append(app)
    return apps


def _items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = _items(value)
                if nested:
                    return nested
        if any(key in data for key in (*_NAME_KEYS, *_ID_KEYS)):
            return [data]
    return []


def _one_app(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        name = item.strip()
        if not name:
            return None
        return _record(name, name, name, 37, 0)
    if not isinstance(item, dict) or not _installed(item):
        return None
    name = _first(item, _NAME_KEYS)
    app_id = _first(item, _ID_KEYS)
    url = _first(item, _URL_KEYS) or app_id or name
    icon = _first(item, ("icon", "iconUrl", "appIcon", "thumbnail"))
    if not name:
        name = app_id or url
    if not name:
        return None
    return _record(
        name,
        url,
        app_id or url,
        _as_int(item.get("urlType", item.get("urltype")), 37),
        _as_int(item.get("storeType", item.get("storetype")), 0),
        icon or None,
    )


def _record(
    name: str,
    url: str,
    app_id: str,
    url_type: int,
    store_type: int,
    icon: str | None = None,
) -> dict[str, Any]:
    app = {
        "name": name,
        "url": url,
        "app_id": app_id,
        "url_type": url_type,
        "store_type": store_type,
    }
    if icon:
        app["icon"] = icon
    return app


def _installed(item: dict[str, Any]) -> bool:
    for key in ("isuninstalled", "uninstalled", "isUninstalled"):
        if key in item and str(item[key]).lower() in {"1", "true"}:
            return False
    for key in ("installed", "isinstalled", "isInstalled"):
        if key in item and str(item[key]).lower() in {"0", "false"}:
            return False
    group = str(
        item.get("from") or item.get("category") or item.get("group") or item.get("appType") or ""
    ).strip().lower()
    return group not in {value.lower() for value in _OTHER_GROUPS}


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
