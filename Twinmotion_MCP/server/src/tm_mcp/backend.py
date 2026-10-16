"""Giao dien backend he dieu hanh: tach lop goi Win32 (winapi.py) khoi logic dieu khien (controller.py)
de test logic bang backend gia (testing.FakeBackend) tren moi he dieu hanh."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from .geometry import Rect


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    rect: Rect            # toan cua so (ke ca vien/tieu de), toa do man hinh
    client: Rect          # vung client (noi dung ung dung), toa do man hinh
    minimized: bool
    maximized: bool
    visible: bool = True

    def as_dict(self) -> dict:
        return {
            "hwnd": self.hwnd, "pid": self.pid, "title": self.title, "rect": self.rect.as_dict(),
            "client": self.client.as_dict(), "minimized": self.minimized, "maximized": self.maximized,
        }


class Backend(Protocol):
    def prepare(self) -> None: ...                                     # vd dat DPI-aware
    def list_windows(self) -> list[WindowInfo]: ...                    # cua so top-level dang hien
    def get_window(self, hwnd: int) -> WindowInfo | None: ...
    def foreground_hwnd(self) -> int: ...
    def focus(self, hwnd: int) -> bool: ...
    def set_state(self, hwnd: int, state: str) -> None: ...            # maximize | minimize | restore
    def move_resize(self, hwnd: int, x: int, y: int, w: int, h: int) -> None: ...
    def close(self, hwnd: int) -> None: ...                            # WM_CLOSE (de ung dung tu hoi luu)
    def cursor_pos(self) -> tuple[int, int]: ...
    def mouse_move(self, x: int, y: int) -> None: ...                  # tuyet doi, toa do man hinh
    def mouse_move_relative(self, dx: int, dy: int) -> None: ...
    def mouse_button(self, button: str, down: bool) -> None: ...
    def mouse_wheel(self, notches: int) -> None: ...
    def key(self, vk: int, down: bool) -> None: ...
    def type_text(self, text: str) -> None: ...
    def grab(self, area: Rect) -> Image.Image: ...
    def screen_rect(self) -> Rect: ...                                 # toan bo man hinh ao (da monitor)
