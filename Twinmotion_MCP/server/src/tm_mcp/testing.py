"""Backend / ProcessApi gia de test controller va server tren moi he dieu hanh (khong dung Win32 that)."""

from __future__ import annotations

from dataclasses import replace

from PIL import Image

from .backend import WindowInfo
from .geometry import Rect
from .process import ProcInfo


class FakeBackend:
    """Mo phong man hinh 1920x1080 voi danh sach cua so; ghi lai moi thao tac vao `actions`."""

    def __init__(self, windows: list[WindowInfo] | None = None) -> None:
        self.windows: list[WindowInfo] = windows or []
        self.foreground = self.windows[0].hwnd if self.windows else 0
        self.cursor = (500, 400)
        self.actions: list[tuple] = []
        self.focus_works = True
        self.frames: list[Image.Image] = []           # anh tra ve lan luot cho grab() (lap lai anh cuoi)
        self._grab_calls = 0

    def prepare(self) -> None:
        self.actions.append(("prepare",))

    def list_windows(self) -> list[WindowInfo]:
        return list(self.windows)

    def get_window(self, hwnd: int):
        return next((w for w in self.windows if w.hwnd == hwnd), None)

    def foreground_hwnd(self) -> int:
        return self.foreground

    def focus(self, hwnd: int) -> bool:
        self.actions.append(("focus", hwnd))
        if not self.focus_works:
            return False
        self.foreground = hwnd
        self.windows = [replace(w, minimized=False) if w.hwnd == hwnd else w for w in self.windows]
        return True

    def set_state(self, hwnd: int, state: str) -> None:
        self.actions.append(("state", hwnd, state))
        self.windows = [replace(w, minimized=state == "minimize", maximized=state == "maximize") if w.hwnd == hwnd else w
                        for w in self.windows]

    def move_resize(self, hwnd: int, x: int, y: int, w: int, h: int) -> None:
        self.actions.append(("move_resize", hwnd, x, y, w, h))
        self.windows = [replace(win, rect=Rect(x, y, x + w, y + h), client=Rect(x + 8, y + 31, x + w - 8, y + h - 8))
                        if win.hwnd == hwnd else win for win in self.windows]

    def close(self, hwnd: int) -> None:
        self.actions.append(("close", hwnd))

    def cursor_pos(self) -> tuple[int, int]:
        return self.cursor

    def mouse_move(self, x: int, y: int) -> None:
        self.cursor = (x, y)
        self.actions.append(("move", x, y))

    def mouse_move_relative(self, dx: int, dy: int) -> None:
        self.cursor = (self.cursor[0] + dx, self.cursor[1] + dy)
        self.actions.append(("rel", dx, dy))

    def mouse_button(self, button: str, down: bool) -> None:
        self.actions.append(("button", button, down))

    def mouse_wheel(self, notches: int) -> None:
        self.actions.append(("wheel", notches))

    def key(self, vk: int, down: bool) -> None:
        self.actions.append(("key", vk, down))

    def type_text(self, text: str) -> None:
        self.actions.append(("text", text))

    def grab(self, area: Rect) -> Image.Image:
        self.actions.append(("grab", area.as_tuple()))
        if self.frames:
            img = self.frames[min(self._grab_calls, len(self.frames) - 1)]
        else:
            img = Image.new("RGB", (max(area.width, 1), max(area.height, 1)), (30, 60, 90))
        self._grab_calls += 1
        return img

    def screen_rect(self) -> Rect:
        return Rect(0, 0, 1920, 1080)


class FakeProcessApi:
    def __init__(self, procs: list[ProcInfo] | None = None) -> None:
        self.procs = list(procs or [])
        self.launched: list[tuple] = []
        self.terminated: list[tuple[int, bool]] = []
        self.on_launch = None            # callable() -> None, de test them cua so/tien trinh sau khi "chay"
        self.survives_terminate = False

    def find(self, names: set[str], hint: str) -> list[ProcInfo]:
        return [p for p in self.procs if p.name.lower() in names or (hint and hint in p.name.lower())]

    def launch(self, target, shortcut, args, cwd) -> None:
        self.launched.append((target, shortcut, list(args), cwd))
        if self.on_launch:
            self.on_launch()

    def terminate(self, pid: int, force: bool) -> None:
        self.terminated.append((pid, force))
        if not self.survives_terminate:
            self.procs = [p for p in self.procs if p.pid != pid]

    def alive(self, pid: int) -> bool:
        return any(p.pid == pid for p in self.procs)


def make_window(hwnd: int = 100, pid: int = 4242, title: str = "Twinmotion 2026.1 - Hamchui",
                left: int = 100, top: int = 50, width: int = 1280, height: int = 800, **kw) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd, pid=pid, title=title,
        rect=Rect(left, top, left + width, top + height),
        client=Rect(left + 8, top + 31, left + width - 8, top + height - 8),
        minimized=kw.get("minimized", False), maximized=kw.get("maximized", False), visible=kw.get("visible", True),
    )


def make_proc(pid: int = 4242, name: str = "Twinmotion.exe") -> ProcInfo:
    return ProcInfo(pid=pid, name=name, exe=rf"C:\Program Files\Twinmotion\{name}", started_at=0.0, rss_mb=2048.0)
