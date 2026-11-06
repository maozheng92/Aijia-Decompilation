"""Remote key codes shared by 海信爱家 and VIDAA sendkey."""

from __future__ import annotations

# Names recovered from com.hisense.ms.fly2tv (libapp.so) plus the
# public VIDAA sendkey set used on E7N Pro.
KEY_POWER = "KEY_POWER"
KEY_VOLUMEUP = "KEY_VOLUMEUP"
KEY_VOLUMEDOWN = "KEY_VOLUMEDOWN"
KEY_MUTE = "KEY_MUTE"
KEY_UP = "KEY_UP"
KEY_DOWN = "KEY_DOWN"
KEY_LEFT = "KEY_LEFT"
KEY_RIGHT = "KEY_RIGHT"
KEY_OK = "KEY_OK"
KEY_RETURNS = "KEY_RETURNS"
KEY_HOME = "KEY_HOME"
KEY_MENU = "KEY_MENU"
KEY_MULTITASK = "KEY_MULTITASK"
KEY_CONTROL_CENTER = "KEY_CONTROL_CENTER"
KEY_BRIGHTUP = "KEY_BRIGHTUP"
KEY_BRIGHTDOWN = "KEY_BRIGHTDOWN"
KEY_JUBAO = "KEY_JUBAO"
KEY_PLAY = "KEY_PLAY"
KEY_PAUSE = "KEY_PAUSE"
KEY_STOP = "KEY_STOP"
KEY_FORWARDS = "KEY_FORWARDS"
KEY_BACK = "KEY_BACK"
KEY_CHANNELUP = "KEY_CHANNELUP"
KEY_CHANNELDOWN = "KEY_CHANNELDOWN"
KEY_EXIT = "KEY_EXIT"
KEY_SOURCE = "KEY_SOURCE"
KEY_NETFLIX = "KEY_NETFLIX"
KEY_YOUTUBE = "KEY_YOUTUBE"

ALIASES: dict[str, str] = {
    "power": KEY_POWER,
    "poweroff": KEY_POWER,
    "power_off": KEY_POWER,
    "volup": KEY_VOLUMEUP,
    "volume_up": KEY_VOLUMEUP,
    "volumeup": KEY_VOLUMEUP,
    "voldown": KEY_VOLUMEDOWN,
    "volume_down": KEY_VOLUMEDOWN,
    "volumedown": KEY_VOLUMEDOWN,
    "mute": KEY_MUTE,
    "up": KEY_UP,
    "down": KEY_DOWN,
    "left": KEY_LEFT,
    "right": KEY_RIGHT,
    "ok": KEY_OK,
    "enter": KEY_OK,
    "select": KEY_OK,
    "back": KEY_RETURNS,
    "return": KEY_RETURNS,
    "returns": KEY_RETURNS,
    "home": KEY_HOME,
    "menu": KEY_MENU,
    "multitask": KEY_MULTITASK,
    "control_center": KEY_CONTROL_CENTER,
    "brightup": KEY_BRIGHTUP,
    "brightdown": KEY_BRIGHTDOWN,
    "jubao": KEY_JUBAO,
    "play": KEY_PLAY,
    "pause": KEY_PAUSE,
    "stop": KEY_STOP,
    "forward": KEY_FORWARDS,
    "fastforward": KEY_FORWARDS,
    "rewind": KEY_BACK,
    "chup": KEY_CHANNELUP,
    "chdown": KEY_CHANNELDOWN,
    "exit": KEY_EXIT,
    "source": KEY_SOURCE,
    "netflix": KEY_NETFLIX,
    "youtube": KEY_YOUTUBE,
}


def normalize_key(key: str) -> str:
    """Accept ``KEY_HOME`` or ``home`` and return the wire key name."""
    raw = key.strip()
    if not raw:
        raise ValueError("Empty key")
    upper = raw.upper()
    if upper.startswith("KEY_"):
        return upper
    return ALIASES.get(raw.lower(), upper if upper.startswith("KEY_") else f"KEY_{upper}")
