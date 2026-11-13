"""Installed TV apps, the same list 爱家 shows under 电视应用 → 我的应用."""

from __future__ import annotations

from typing import Any

_NAME_KEYS = ("name", "appName", "appname", "title", "app_name", "label")
_URL_KEYS = ("url", "appUrl", "appurl", "launchUrl")
_ID_KEYS = ("appId", "appid", "id", "packageName", "packagename", "package")
_PACKAGE_KEYS = ("packageName", "packagename", "package", "pkgName", "pkg")
_SIZE_KEYS = (
    "size",
    "appSize",
    "apkSize",
    "packageSize",
    "fileSize",
    "installSize",
    "occupiedSize",
    "dataSize",
)
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
    "installedApps",
    "installedAppList",
    "packageList",
)
# 热门/推荐 are the store rows next to 我的应用, not the installed set.
_OTHER_GROUPS = {"recommend", "hot", "store", "banner", "ad", "推荐", "热门", "应用推荐"}


def normalize_apps(data: Any) -> list[dict[str, Any]]:
    """Return installed apps as ``{name, url, app_id, url_type, store_type}``."""
    apps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _items(data):
        app = _one_app(item)
        if app is None:
            continue
        key = app.get("package") or app["name"]
        if key in seen:
            continue
        seen.add(key)
        apps.append(app)
    return apps


def format_app_title(app: dict[str, Any]) -> str:
    """Display name like 爱家: ``健身镜 (51.45M)`` when size is known."""
    name = str(app.get("name") or app.get("package") or "").strip()
    size = str(app.get("size") or "").strip()
    if name and size:
        return f"{name} ({size})"
    return name


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
        if any(key in data for key in (*_NAME_KEYS, *_ID_KEYS, *_PACKAGE_KEYS)):
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
    package = _first(item, _PACKAGE_KEYS)
    name = _first(item, _NAME_KEYS)
    app_id = _first(item, _ID_KEYS)
    url = _first(item, _URL_KEYS) or package or app_id or name
    icon = _first(item, ("icon", "iconUrl", "appIcon", "thumbnail"))
    size = _format_size(item)
    local = _truthy(item.get("isLocalApp", item.get("islocalapp")))
    if package and (local or not _first(item, _URL_KEYS)):
        url = package
    if not name:
        name = package or app_id or url
    if not name:
        return None
    url_type = _as_int(item.get("urlType", item.get("urltype")), 0 if package else 37)
    if package and local:
        url_type = 0
    return _record(
        name,
        url,
        app_id or package or url,
        url_type,
        _as_int(item.get("storeType", item.get("storetype")), 0),
        icon or None,
        package or None,
        size,
    )


def _record(
    name: str,
    url: str,
    app_id: str,
    url_type: int,
    store_type: int,
    icon: str | None = None,
    package: str | None = None,
    size: str | None = None,
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
    if package:
        app["package"] = package
    if size:
        app["size"] = size
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


def _truthy(value: Any) -> bool:
    return str(value).lower() in {"1", "true", "yes"}


def _format_size(item: dict[str, Any]) -> str | None:
    for key in _SIZE_KEYS:
        if key not in item or item[key] in (None, ""):
            continue
        value = item[key]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            if text[-1:].upper() in {"B", "K", "M", "G"} or text[-2:].upper() in {
                "KB",
                "MB",
                "GB",
            }:
                return text
            try:
                value = float(text)
            except ValueError:
                return text
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number < 0:
            continue
        # Bytes when large; already-MB when small.
        if number >= 1024 * 1024:
            return f"{number / (1024 * 1024):.2f}M"
        if number >= 1024:
            return f"{number / 1024:.2f}K"
        if number >= 100:
            return f"{number:.2f}M"
        return f"{number:.2f}M"
    return None
