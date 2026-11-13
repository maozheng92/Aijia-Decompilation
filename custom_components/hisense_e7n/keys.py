"""Remote key codes shared by 海信爱家 and VIDAA sendkey."""

from __future__ import annotations

from dataclasses import dataclass

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
    "settings": KEY_CONTROL_CENTER,
    "controlcenter": KEY_CONTROL_CENTER,
    "screenshot": "screenshot",
    "smart_image": "smart_image",
    "ai": "smart_image",
}


@dataclass(frozen=True)
class RemoterButton:
    """One control on the 爱家 ``control_page_tv`` remoter."""

    slug: str
    translation_key: str
    icon: str
    kind: str
    payload: str | None = None


# Layout matches 海信爱家 电视遥控页 (control_page_tv_buttons.dart):
# 电源 / 音量- 静音 音量+ / 截屏 / 信号源 / AI识图 / 设置 / 方向键 OK / 返回 首页 菜单
# 「切换遥控模式」和底部语音是 App 内能力，不作为电视按键。
AIJIA_REMOTER_BUTTONS: tuple[RemoterButton, ...] = (
    RemoterButton("power", "power", "mdi:power", "power", KEY_POWER),
    RemoterButton("volume_down", "volume_down", "mdi:minus", "key", KEY_VOLUMEDOWN),
    RemoterButton("mute", "mute", "mdi:volume-mute", "key", KEY_MUTE),
    RemoterButton("volume_up", "volume_up", "mdi:plus", "key", KEY_VOLUMEUP),
    RemoterButton("screenshot", "screenshot", "mdi:monitor-screenshot", "screenshot"),
    RemoterButton("source", "source", "mdi:import", "source", KEY_SOURCE),
    RemoterButton("smart_image", "smart_image", "mdi:image-search-outline", "smart_image"),
    RemoterButton("settings", "settings", "mdi:cog-outline", "key", KEY_CONTROL_CENTER),
    RemoterButton("up", "up", "mdi:chevron-up", "key", KEY_UP),
    RemoterButton("left", "left", "mdi:chevron-left", "key", KEY_LEFT),
    RemoterButton("ok", "ok", "mdi:circle-outline", "key", KEY_OK),
    RemoterButton("right", "right", "mdi:chevron-right", "key", KEY_RIGHT),
    RemoterButton("down", "down", "mdi:chevron-down", "key", KEY_DOWN),
    RemoterButton("back", "back", "mdi:arrow-u-left-top", "key", KEY_RETURNS),
    RemoterButton("home", "home", "mdi:home-outline", "key", KEY_HOME),
    RemoterButton("menu", "menu", "mdi:menu", "key", KEY_MENU),
)


def aijia_send_commands() -> list[str]:
    """Commands ``remote.send_command`` accepts, in 爱家 keypad order."""
    commands: list[str] = []
    for item in AIJIA_REMOTER_BUTTONS:
        if item.payload:
            commands.append(item.payload)
        elif item.kind in {"screenshot", "smart_image"}:
            commands.append(item.kind)
    return commands


def normalize_key(key: str) -> str:
    """Accept ``KEY_HOME`` or ``home`` and return the wire key name."""
    raw = key.strip()
    if not raw:
        raise ValueError("Empty key")
    upper = raw.upper()
    if upper.startswith("KEY_"):
        return upper
    return ALIASES.get(raw.lower(), upper if upper.startswith("KEY_") else f"KEY_{upper}")
