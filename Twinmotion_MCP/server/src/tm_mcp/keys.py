"""Bang ma phim ao (Windows Virtual-Key) va bo phan tich chuoi phim tat: "ctrl+shift+s" -> [VK_CONTROL, VK_SHIFT, 'S'].

Thuan Python (khong phu thuoc Windows) nen test duoc o moi he dieu hanh. Cac phim dau cau gia dinh ban phim
My (US) - phim OEM thay doi theo bo cuc ban phim; voi ky tu van ban hay dung tm_type_text (gui Unicode).
"""

from __future__ import annotations

VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN = 0x10, 0x11, 0x12, 0x5B

MODIFIERS: dict[str, int] = {
    "ctrl": VK_CONTROL, "control": VK_CONTROL, "ctl": VK_CONTROL,
    "shift": VK_SHIFT,
    "alt": VK_MENU, "menu": VK_MENU,
    "win": VK_LWIN, "windows": VK_LWIN, "cmd": VK_LWIN, "super": VK_LWIN,
}

_NAMED: dict[str, int] = {
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20, "spacebar": 0x20,
    "backspace": 0x08, "bksp": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "ins": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91, "printscreen": 0x2C, "prtsc": 0x2C, "pause": 0x13,
    "add": 0x6B, "subtract": 0x6D, "multiply": 0x6A, "divide": 0x6F, "decimal": 0x6E,
    # dau cau (ban phim US)
    "comma": 0xBC, ",": 0xBC, "period": 0xBE, ".": 0xBE, "minus": 0xBD, "-": 0xBD, "equals": 0xBB, "=": 0xBB,
    "plus": 0xBB, "semicolon": 0xBA, ";": 0xBA, "slash": 0xBF, "/": 0xBF, "backtick": 0xC0, "`": 0xC0,
    "lbracket": 0xDB, "[": 0xDB, "rbracket": 0xDD, "]": 0xDD, "backslash": 0xDC, "\\": 0xDC,
    "quote": 0xDE, "'": 0xDE,
}

# Phim "extended" can co KEYEVENTF_EXTENDEDKEY de he thong phan biet voi phim numpad
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x6F, 0x5B, 0x5C}


def vk_for(name: str) -> int:
    """'a' -> 0x41, '5' -> 0x35, 'f11' -> 0x7A, 'enter' -> 0x0D, 'num7' -> 0x67."""
    key = name.strip().lower()
    if not key:
        raise ValueError("Ten phim rong.")
    if key in MODIFIERS:
        return MODIFIERS[key]
    if key in _NAMED:
        return _NAMED[key]
    if len(key) == 1 and "a" <= key <= "z":
        return ord(key.upper())
    if len(key) == 1 and "0" <= key <= "9":
        return ord(key)
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1
    for prefix in ("num", "numpad"):
        if key.startswith(prefix) and key[len(prefix):].isdigit() and len(key) == len(prefix) + 1:
            return 0x60 + int(key[len(prefix):])
    raise ValueError(f"Phim khong hop le: {name!r}")


def is_extended(vk: int) -> bool:
    return vk in _EXTENDED


def parse_hotkey(spec: str) -> list[int]:
    """'ctrl+shift+s' -> [0x11, 0x10, 0x53]; phim thuong dung o cuoi, modifier dung truoc.

    Ky tu '+' lam phim thi viet 'plus'. Chi cho phep DUNG 1 phim khong-modifier (to hop kieu 'a+b' khong co nghia).
    """
    parts = [p for p in spec.replace(" ", "").split("+") if p != ""]
    if not parts:
        raise ValueError("Phim tat rong.")
    mods: list[int] = []
    plain: list[int] = []
    for part in parts:
        vk = vk_for(part)
        (mods if part.lower() in MODIFIERS else plain).append(vk)
    if len(plain) > 1:
        raise ValueError(f"Phim tat {spec!r} co {len(plain)} phim thuong; chi cho phep modifier + 1 phim.")
    # bo trung modifier, giu thu tu xuat hien
    seen: set[int] = set()
    ordered_mods = [m for m in mods if not (m in seen or seen.add(m))]
    return ordered_mods + plain
