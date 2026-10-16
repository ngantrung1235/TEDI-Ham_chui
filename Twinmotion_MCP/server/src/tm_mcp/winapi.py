"""Backend Windows (ctypes + user32). CHI chay tren Windows; import tren he khac van duoc (de test cau truc).

CHUA duoc kiem chung tren Windows that (xem README): moi ham la goi Win32 chuan, khai bao argtypes/restype day
du de khong cat cut handle 64-bit. Cau truc INPUT dung kieu do rong co dinh (c_uint32...) de kich thuoc giong
nhau tren moi nen tang (40 byte tren 64-bit) - co test.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import c_int, c_int32, c_size_t, c_uint16, c_uint32, c_void_p

from PIL import Image

from .geometry import Rect
from .keys import is_extended

IS_WINDOWS = sys.platform == "win32"

# --- hang so Win32
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0001, 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, MOUSEEVENTF_WHEEL = 0x0020, 0x0040, 0x0800
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004
SW_SHOW, SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 5, 3, 6, 9
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
WM_CLOSE = 0x0010
WHEEL_DELTA = 120
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class RECT(ctypes.Structure):
    _fields_ = [("left", c_int32), ("top", c_int32), ("right", c_int32), ("bottom", c_int32)]


class POINT(ctypes.Structure):
    _fields_ = [("x", c_int32), ("y", c_int32)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", c_int32), ("dy", c_int32), ("mouseData", c_uint32), ("dwFlags", c_uint32),
                ("time", c_uint32), ("dwExtraInfo", c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", c_uint16), ("wScan", c_uint16), ("dwFlags", c_uint32), ("time", c_uint32),
                ("dwExtraInfo", c_size_t)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", c_uint32), ("u", _INPUT_UNION)]


def _user32():
    if not IS_WINDOWS:
        raise OSError("Backend Windows chi chay tren Windows.")
    return ctypes.windll.user32


class WindowsBackend:
    def __init__(self) -> None:
        self._ready = False

    # ------------------------------------------------------------------ khoi tao
    def prepare(self) -> None:
        """Dat tien trinh DPI-aware de GetWindowRect/SendInput/ImageGrab cung dung pixel vat ly."""
        if self._ready:
            return
        u = _user32()
        try:
            u.SetProcessDpiAwarenessContext.argtypes = [c_void_p]
            if not u.SetProcessDpiAwarenessContext(c_void_p(-4)):          # PER_MONITOR_AWARE_V2
                raise OSError
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                u.SetProcessDPIAware()
        self._declare(u)
        self._ready = True

    @staticmethod
    def _declare(u) -> None:
        sig = {
            "IsWindowVisible": (c_int, [c_void_p]), "IsIconic": (c_int, [c_void_p]), "IsZoomed": (c_int, [c_void_p]),
            "GetWindowTextLengthW": (c_int, [c_void_p]),
            "GetWindowTextW": (c_int, [c_void_p, ctypes.c_wchar_p, c_int]),
            "GetWindowThreadProcessId": (c_uint32, [c_void_p, ctypes.POINTER(c_uint32)]),
            "GetWindowRect": (c_int, [c_void_p, ctypes.POINTER(RECT)]),
            "GetClientRect": (c_int, [c_void_p, ctypes.POINTER(RECT)]),
            "ClientToScreen": (c_int, [c_void_p, ctypes.POINTER(POINT)]),
            "GetForegroundWindow": (c_void_p, []), "SetForegroundWindow": (c_int, [c_void_p]),
            "BringWindowToTop": (c_int, [c_void_p]), "ShowWindow": (c_int, [c_void_p, c_int]),
            "SetWindowPos": (c_int, [c_void_p, c_void_p, c_int, c_int, c_int, c_int, c_uint32]),
            "PostMessageW": (c_int, [c_void_p, c_uint32, c_size_t, c_size_t]),
            "AttachThreadInput": (c_int, [c_uint32, c_uint32, c_int]),
            "SetCursorPos": (c_int, [c_int, c_int]), "GetCursorPos": (c_int, [ctypes.POINTER(POINT)]),
            "SendInput": (c_uint32, [c_uint32, ctypes.POINTER(INPUT), c_int]),
            "GetSystemMetrics": (c_int, [c_int]),
        }
        for name, (res, args) in sig.items():
            fn = getattr(u, name)
            fn.restype, fn.argtypes = res, args
        ctypes.windll.kernel32.GetCurrentThreadId.restype = c_uint32

    # ------------------------------------------------------------------ cua so
    def _info(self, hwnd: int):
        from .backend import WindowInfo
        u = _user32()
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        pid = c_uint32()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        r = RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        cr = RECT()
        u.GetClientRect(hwnd, ctypes.byref(cr))
        origin = POINT(0, 0)
        u.ClientToScreen(hwnd, ctypes.byref(origin))
        return WindowInfo(
            hwnd=int(hwnd), pid=int(pid.value), title=buf.value,
            rect=Rect(r.left, r.top, r.right, r.bottom),
            client=Rect(origin.x, origin.y, origin.x + cr.right, origin.y + cr.bottom),
            minimized=bool(u.IsIconic(hwnd)), maximized=bool(u.IsZoomed(hwnd)), visible=bool(u.IsWindowVisible(hwnd)),
        )

    def list_windows(self):
        self.prepare()
        u = _user32()
        found: list[int] = []
        proto = ctypes.WINFUNCTYPE(c_int, c_void_p, c_void_p)

        def callback(hwnd, _lparam):
            if u.IsWindowVisible(hwnd) and u.GetWindowTextLengthW(hwnd) > 0:
                found.append(int(hwnd))
            return 1

        u.EnumWindows.argtypes = [proto, c_void_p]
        u.EnumWindows(proto(callback), None)
        return [self._info(h) for h in found]

    def get_window(self, hwnd: int):
        self.prepare()
        u = _user32()
        return self._info(hwnd) if u.GetWindowRect(hwnd, ctypes.byref(RECT())) else None

    def foreground_hwnd(self) -> int:
        self.prepare()
        return int(_user32().GetForegroundWindow() or 0)

    def focus(self, hwnd: int) -> bool:
        """Dua cua so len truoc. Windows chan SetForegroundWindow tu tien trinh nen -> gan tam input voi luong
        dang giu foreground (cach thong dung); xac nhan lai bang GetForegroundWindow."""
        self.prepare()
        u = _user32()
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, SW_RESTORE)
        if self.foreground_hwnd() != hwnd:
            fg = u.GetForegroundWindow()
            fg_tid = u.GetWindowThreadProcessId(fg, None) if fg else 0
            me = ctypes.windll.kernel32.GetCurrentThreadId()
            attached = bool(fg_tid and fg_tid != me and u.AttachThreadInput(me, fg_tid, 1))
            try:
                u.BringWindowToTop(hwnd)
                u.ShowWindow(hwnd, SW_SHOW)
                u.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    u.AttachThreadInput(me, fg_tid, 0)
            time.sleep(0.15)
        return self.foreground_hwnd() == hwnd

    def set_state(self, hwnd: int, state: str) -> None:
        self.prepare()
        cmd = {"maximize": SW_MAXIMIZE, "minimize": SW_MINIMIZE, "restore": SW_RESTORE}[state]
        _user32().ShowWindow(hwnd, cmd)

    def move_resize(self, hwnd: int, x: int, y: int, w: int, h: int) -> None:
        self.prepare()
        _user32().SetWindowPos(hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE)

    def close(self, hwnd: int) -> None:
        self.prepare()
        _user32().PostMessageW(hwnd, WM_CLOSE, 0, 0)

    # ------------------------------------------------------------------ chuot
    def cursor_pos(self) -> tuple[int, int]:
        self.prepare()
        p = POINT()
        _user32().GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def mouse_move(self, x: int, y: int) -> None:
        self.prepare()
        _user32().SetCursorPos(int(x), int(y))

    def _send(self, *inputs: INPUT) -> None:
        arr = (INPUT * len(inputs))(*inputs)
        sent = _user32().SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            raise OSError(f"SendInput chi gui duoc {sent}/{len(inputs)} su kien (UIPI chan? ung dung dang chay quyen Admin?).")

    @staticmethod
    def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
        i = INPUT()
        i.type = INPUT_MOUSE
        i.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
        return i

    def mouse_move_relative(self, dx: int, dy: int) -> None:
        self.prepare()
        self._send(self._mouse(MOUSEEVENTF_MOVE, int(dx), int(dy)))

    def mouse_button(self, button: str, down: bool) -> None:
        self.prepare()
        d, u_ = _BUTTONS[button]
        self._send(self._mouse(d if down else u_))

    def mouse_wheel(self, notches: int) -> None:
        self.prepare()
        self._send(self._mouse(MOUSEEVENTF_WHEEL, data=int(notches) * WHEEL_DELTA))

    # ------------------------------------------------------------------ ban phim
    @staticmethod
    def _key(vk: int, scan: int, flags: int) -> INPUT:
        i = INPUT()
        i.type = INPUT_KEYBOARD
        i.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
        return i

    def key(self, vk: int, down: bool) -> None:
        self.prepare()
        flags = (KEYEVENTF_EXTENDEDKEY if is_extended(vk) else 0) | (0 if down else KEYEVENTF_KEYUP)
        self._send(self._key(vk, 0, flags))

    def type_text(self, text: str) -> None:
        """Go ky tu Unicode (KEYEVENTF_UNICODE) - dung duoc cho tieng Viet, khong phu thuoc bo cuc ban phim."""
        self.prepare()
        units = text.encode("utf-16-le")
        for i in range(0, len(units), 2):
            code = int.from_bytes(units[i:i + 2], "little")
            self._send(self._key(0, code, KEYEVENTF_UNICODE), self._key(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))

    # ------------------------------------------------------------------ man hinh
    def grab(self, area: Rect) -> Image.Image:
        self.prepare()
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=area.as_tuple(), all_screens=True)

    def screen_rect(self) -> Rect:
        self.prepare()
        u = _user32()
        x, y = u.GetSystemMetrics(SM_XVIRTUALSCREEN), u.GetSystemMetrics(SM_YVIRTUALSCREEN)
        return Rect(x, y, x + u.GetSystemMetrics(SM_CXVIRTUALSCREEN), y + u.GetSystemMetrics(SM_CYVIRTUALSCREEN))
