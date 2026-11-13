"""Local key channel used by 海信爱家 on the TV itself.

The app probes TCP 7778 and 7779 and posts the key name to
``http://<tv>:<port>/<KEY>..controller``. That request does not use the
MQTT session, so it still works when the TV never shows a pairing code.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

_LOGGER = logging.getLogger(__name__)

LOCAL_KEY_PORTS = (7778, 7779)


def send_local_key(
    host: str,
    key: str,
    *,
    ports: tuple[int, ...] = LOCAL_KEY_PORTS,
    timeout: float = 2.0,
) -> int | None:
    """POST the key. Return the HTTP status, or None if no port answered."""
    name = key.strip()
    if not name or any(ch in name for ch in "/?#"):
        raise ValueError(f"invalid key: {key}")
    answered: int | None = None
    for port in ports:
        url = f"http://{host}:{port}/{name}..controller"
        for method in ("POST", "GET"):
            status = _request(url, method, timeout)
            if status is None:
                break
            answered = status
            if 200 <= status < 300:
                _LOGGER.info("TV accepted %s on port %s", name, port)
                return status
        # This port is not the key service. Try the other one.
    return answered


def _request(url: str, method: str, timeout: float) -> int | None:
    data = b"{}" if method == "POST" else None
    headers = {"Content-Type": "application/json", "Connection": "close"} if data else {}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code
    except (TimeoutError, OSError, urllib.error.URLError):
        return None
