"""Bo dieu khien Twinmotion: gom logic an toan (cua so dang foreground, vung toa do hop le, chot an toan goc man
hinh, che do chi-doc) tren mot Backend he dieu hanh (winapi.WindowsBackend that / testing.FakeBackend gia).

Twinmotion 2026.1 KHONG co API script hay dieu khien tu xa duoc cong bo, nen dieu khien o tang giao dien:
chup man hinh -> LLM nhin -> chuot/phim -> chup lai kiem tra.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from . import capture
from .backend import Backend, WindowInfo
from .geometry import OutOfBounds, Rect, checked_screen_point, interpolate
from .keys import MODIFIERS, parse_hotkey, vk_for
from .lnk import Shortcut, ShortcutError, resolve_shortcut
from .process import ProcInfo, ProcessApi

DEFAULT_SHORTCUT = r"C:\Users\Public\Desktop\Twinmotion 2026.1 For Revit.lnk"
MAX_TEXT = 2000


class ControlError(RuntimeError):
    """Loi dieu khien co the giai thich cho LLM/nguoi dung (khong phai bug)."""


@dataclass
class Settings:
    shortcut: str = DEFAULT_SHORTCUT
    exe: str | None = None             # ghi de duong dan exe (bo qua shortcut)
    process_hint: str = "twinmotion"   # chuoi con trong ten tien trinh
    input_enabled: bool = True         # False = che do chi-doc: khong chuot/phim
    allow_kill: bool = True

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "Settings":
        e = os.environ if env is None else env
        return Settings(
            shortcut=e.get("TM_SHORTCUT") or DEFAULT_SHORTCUT,
            exe=e.get("TM_EXE") or None,
            process_hint=(e.get("TM_PROCESS_HINT") or "twinmotion").lower(),
            input_enabled=e.get("TM_MCP_ALLOW_INPUT", "1") != "0",
            allow_kill=e.get("TM_MCP_ALLOW_KILL", "1") != "0",
        )


class TwinmotionController:
    def __init__(self, backend: Backend, proc: ProcessApi, settings: Settings | None = None, *,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self.backend, self.proc = backend, proc
        self.settings = settings or Settings.from_env()
        self.sleep, self.clock = sleep, clock
        self._shortcut: Shortcut | None = None
        self.log: list[str] = []

    # ------------------------------------------------------------------ shortcut / tien trinh
    def shortcut(self, refresh: bool = False) -> Shortcut:
        if self._shortcut is None or refresh:
            try:
                self._shortcut = resolve_shortcut(self.settings.shortcut)
            except ShortcutError as exc:
                raise ControlError(f"{exc} (dat TM_SHORTCUT hoac TM_EXE).") from exc
        return self._shortcut

    def exe_path(self) -> str | None:
        if self.settings.exe:
            return self.settings.exe
        try:
            return self.shortcut().target
        except ControlError:
            return None

    def _process_names(self) -> set[str]:
        exe = self.exe_path()
        return {os.path.basename(exe).lower()} if exe else set()

    def processes(self) -> list[ProcInfo]:
        return self.proc.find(self._process_names(), self.settings.process_hint)

    def app_windows(self) -> list[WindowInfo]:
        pids = {p.pid for p in self.processes()}
        wins = [w for w in self.backend.list_windows() if w.pid in pids and w.visible]
        return sorted(wins, key=lambda w: w.minimized)          # cua so dang hien truoc, thu nho sau

    def main_window(self) -> WindowInfo | None:
        wins = self.app_windows()
        if not wins:
            return None
        named = [w for w in wins if "twinmotion" in w.title.lower()] or wins
        return max(named, key=lambda w: w.client.width * w.client.height)

    # ------------------------------------------------------------------ trang thai
    def status(self) -> dict:
        self.backend.prepare()
        try:
            sc = self.shortcut().as_dict()
        except ControlError as exc:
            sc = {"error": str(exc)}
        procs = self.processes()
        main = self.main_window()
        fg = self.backend.foreground_hwnd()
        return {
            "shortcut": sc,
            "exe": self.exe_path(),
            "running": bool(procs),
            "processes": [p.as_dict() for p in procs],
            "main_window": main.as_dict() if main else None,
            "main_window_is_foreground": bool(main and main.hwnd == fg),
            "windows": [w.as_dict() for w in self.app_windows()],
            "screen": self.backend.screen_rect().as_dict(),
            "input_enabled": self.settings.input_enabled,
            "note": "Twinmotion khong co API script; dieu khien qua giao dien (chup man hinh + chuot/phim).",
        }

    # ------------------------------------------------------------------ khoi dong / dong
    def launch(self, args: list[str] | None = None, wait_s: float = 90.0, allow_second: bool = False) -> dict:
        self.backend.prepare()
        args = list(args or [])
        if self.processes() and not allow_second:
            main = self.main_window()
            return {"launched": False, "already_running": True, "main_window": main.as_dict() if main else None}
        sc = None
        try:
            sc = self.shortcut()
        except ControlError:
            if not self.settings.exe:
                raise
        exe = self.settings.exe or (sc.target if sc else None)
        if exe and not os.path.exists(exe):
            raise ControlError(f"Khong thay file chay: {exe}")
        self.proc.launch(exe, None if self.settings.exe else self.settings.shortcut, args,
                         sc.working_dir if sc else None)
        start = self.clock()
        while self.clock() - start < wait_s:
            self.sleep(1.0)
            main = self.main_window()
            if main and main.client.width > 200 and main.client.height > 200:
                return {"launched": True, "main_window": main.as_dict(), "waited_s": round(self.clock() - start, 1)}
        return {"launched": True, "window_ready": False,
                "note": f"Da chay nhung chua thay cua so chinh sau {wait_s:g}s (co the dang tai/hoi dang nhap). Dung tm_status/tm_screenshot."}

    def close(self, force: bool = False, wait_s: float = 15.0) -> dict:
        self.backend.prepare()
        procs = self.processes()
        if not procs:
            return {"closed": True, "was_running": False}
        if force:
            if not self.settings.allow_kill:
                raise ControlError("Dong cuong buc bi tat (TM_MCP_ALLOW_KILL=0).")
            for p in procs:
                self.proc.terminate(p.pid, True)
            self.sleep(1.0)
            return {"closed": not any(self.proc.alive(p.pid) for p in procs), "forced": True,
                    "warning": "Dong cuong buc - thay doi chua luu se mat."}
        main = self.main_window()
        if main:
            self.backend.close(main.hwnd)
        deadline = self.clock() + wait_s
        while self.clock() < deadline:
            self.sleep(0.5)
            if not any(self.proc.alive(p.pid) for p in procs):
                return {"closed": True, "forced": False}
        return {"closed": False, "reason": "Twinmotion van chay - co the dang hien hop thoai hoi luu. "
                                           "Dung tm_screenshot de xem, xu ly hop thoai, hoac tm_close(force=true).",
                "windows": [w.as_dict() for w in self.app_windows()]}

    # ------------------------------------------------------------------ cua so / vung dieu khien
    def _require_main(self) -> WindowInfo:
        main = self.main_window()
        if main is None:
            raise ControlError("Twinmotion chua chay hoac khong co cua so (dung tm_launch / tm_status).")
        return main

    def main_hwnd(self) -> int:
        return self._require_main().hwnd

    def focus(self) -> WindowInfo:
        main = self._require_main()
        if not self.backend.focus(main.hwnd):
            raise ControlError("Khong dua duoc cua so Twinmotion len truoc (Windows chan foreground?). "
                               "Hay nhap vao cua so Twinmotion bang tay 1 lan roi thu lai.")
        return self.backend.get_window(main.hwnd) or main

    def set_window(self, state: str | None = None, x: int | None = None, y: int | None = None,
                   width: int | None = None, height: int | None = None) -> dict:
        main = self._require_main()
        if state:
            if state not in ("maximize", "minimize", "restore"):
                raise ControlError("state phai la maximize | minimize | restore.")
            self.backend.set_state(main.hwnd, state)
        if None not in (x, y, width, height):
            self.backend.set_state(main.hwnd, "restore")
            self.backend.move_resize(main.hwnd, int(x), int(y), int(width), int(height))
        self.sleep(0.3)
        return (self.backend.get_window(main.hwnd) or main).as_dict()

    def _target_window(self, target: str) -> WindowInfo:
        """target: main (cua so chinh) | active (cua so cua ung dung dang foreground - hop thoai, menu)."""
        if target == "main":
            return self._require_main()
        if target == "active":
            fg = self.backend.foreground_hwnd()
            for w in self.app_windows():
                if w.hwnd == fg:
                    return w
            raise ControlError("Khong co cua so cua Twinmotion dang o foreground (dung target='main' hoac tm_focus).")
        raise ControlError("target phai la 'main' hoac 'active'.")

    def _area(self, target: str, area: str) -> tuple[WindowInfo, Rect]:
        win = self._target_window(target)
        if win.minimized:
            raise ControlError("Cua so Twinmotion dang thu nho; dung tm_set_window(state='restore') hoac tm_focus.")
        return win, (win.client if area == "client" else win.rect)

    # ------------------------------------------------------------------ chup man hinh
    def screenshot(self, target: str = "main", area: str = "client", grid: int = 0, max_width: int = 1600,
                   mark: tuple[int, int] | None = None) -> tuple[bytes, dict]:
        """PNG cua vung `area` (client|window) cua cua so. Toa do (0,0) = goc tren-trai anh GOC; neu anh bi thu
        nho (max_width) thi toa do tren anh nho = toa do that x scale (scale co trong meta)."""
        self.backend.prepare()
        win, rect = self._area(target, area)
        if not win.title and rect.width <= 0:
            raise ControlError("Cua so khong co noi dung de chup.")
        img = self.backend.grab(rect)
        if grid:
            img = capture.draw_grid(img, grid)
        if mark:
            img = capture.mark_point(img, int(mark[0]), int(mark[1]))
        png = capture.to_png(img, max_width)
        out_w = min(img.width, max_width) if max_width else img.width
        meta = {
            "target": target, "area": area, "window_title": win.title, "origin_screen": [rect.left, rect.top],
            "width": rect.width, "height": rect.height, "scale": round(out_w / img.width, 4),
            "foreground": self.backend.foreground_hwnd() == win.hwnd,
        }
        return png, meta

    def wait_stable(self, timeout_s: float = 60.0, interval_s: float = 1.0, stable_frames: int = 3,
                    threshold: float = 0.002) -> dict:
        self.backend.prepare()
        _, rect = self._area("main", "client")
        return capture.wait_until_stable(lambda: self.backend.grab(rect), timeout_s, interval_s, stable_frames,
                                         threshold, self.sleep, self.clock)

    # ------------------------------------------------------------------ dau vao (chuot / phim)
    def _guard_input(self, target: str) -> WindowInfo:
        if not self.settings.input_enabled:
            raise ControlError("Che do CHI-DOC: dau vao chuot/phim bi tat (TM_MCP_ALLOW_INPUT=0).")
        self.backend.prepare()
        if self.backend.cursor_pos() == (0, 0):
            raise ControlError("CHOT AN TOAN: con tro chuot dang o goc tren-trai man hinh (0,0) - dung dieu khien. "
                               "Di chuot ra khoi goc roi thu lai.")
        win = self._target_window(target)
        if win.minimized:
            raise ControlError("Cua so Twinmotion dang thu nho; dung tm_focus truoc.")
        fg = self.backend.foreground_hwnd()
        app_hwnds = {w.hwnd for w in self.app_windows()}
        if fg not in app_hwnds:
            # Dua cua so chinh len truoc roi kiem tra lai - TUYET DOI khong gui phim/chuot khi foreground la app khac.
            self.focus()
            fg = self.backend.foreground_hwnd()
            if fg not in {w.hwnd for w in self.app_windows()}:
                raise ControlError("Cua so dang o foreground khong phai Twinmotion; huy de tranh gui phim nham ung dung.")
        return self._target_window(target)

    def _point(self, win: WindowInfo, x: float, y: float) -> tuple[int, int]:
        try:
            return checked_screen_point(win.client, x, y)
        except OutOfBounds as exc:
            raise ControlError(str(exc)) from exc

    def move(self, x: float, y: float, target: str = "main") -> dict:
        win = self._guard_input(target)
        sx, sy = self._point(win, x, y)
        self.backend.mouse_move(sx, sy)
        return {"screen": [sx, sy]}

    def click(self, x: float, y: float, button: str = "left", double: bool = False, target: str = "main") -> dict:
        if button not in ("left", "right", "middle"):
            raise ControlError("button phai la left | right | middle.")
        win = self._guard_input(target)
        sx, sy = self._point(win, x, y)
        self.backend.mouse_move(sx, sy)
        self.sleep(0.06)
        for _ in range(2 if double else 1):
            self.backend.mouse_button(button, True)
            self.sleep(0.04)
            self.backend.mouse_button(button, False)
            self.sleep(0.06)
        return {"clicked": [sx, sy], "button": button, "double": double}

    def drag(self, x1: float, y1: float, x2: float, y2: float, button: str = "left", duration_ms: int = 400,
             target: str = "main") -> dict:
        """Keo chuot (xoay/di chuyen camera, keo thanh truot). Di chuyen bang su kien TUONG DOI (raw input) vi
        game/engine nhu Unreal doc chuot theo raw input chu khong theo SetCursorPos."""
        if button not in ("left", "right", "middle"):
            raise ControlError("button phai la left | right | middle.")
        if not 50 <= duration_ms <= 10000:
            raise ControlError("duration_ms phai trong 50..10000.")
        win = self._guard_input(target)
        sx1, sy1 = self._point(win, x1, y1)
        sx2, sy2 = self._point(win, x2, y2)
        steps = max(8, min(60, duration_ms // 16))
        self.backend.mouse_move(sx1, sy1)
        self.sleep(0.08)
        self.backend.mouse_button(button, True)
        self.sleep(0.05)
        try:
            px, py = sx1, sy1
            for tx, ty in interpolate(sx1, sy1, sx2, sy2, steps):
                self.backend.mouse_move_relative(tx - px, ty - py)
                px, py = tx, ty
                self.sleep(duration_ms / 1000 / steps)
        finally:
            self.backend.mouse_button(button, False)          # luon nha chuot du loi giua chung
        return {"dragged": [[sx1, sy1], [sx2, sy2]], "button": button, "steps": steps}

    def scroll(self, x: float, y: float, notches: int, target: str = "main") -> dict:
        if notches == 0 or abs(notches) > 50:
            raise ControlError("notches phai khac 0 va |notches| <= 50 (duong = cuon len/zoom vao).")
        win = self._guard_input(target)
        sx, sy = self._point(win, x, y)
        self.backend.mouse_move(sx, sy)
        self.sleep(0.05)
        for _ in range(abs(notches)):
            self.backend.mouse_wheel(1 if notches > 0 else -1)
            self.sleep(0.03)
        return {"scrolled": notches, "at": [sx, sy]}

    def type_text(self, text: str, interval_ms: int = 0, target: str = "main") -> dict:
        if not text:
            raise ControlError("text rong.")
        if len(text) > MAX_TEXT:
            raise ControlError(f"text qua dai ({len(text)} > {MAX_TEXT}).")
        self._guard_input(target)
        chunk = 1 if interval_ms > 0 else 40
        for i in range(0, len(text), chunk):
            self.backend.type_text(text[i:i + chunk])
            if interval_ms > 0:
                self.sleep(interval_ms / 1000)
        return {"typed": len(text)}

    def hotkey(self, spec: str, target: str = "main") -> dict:
        try:
            vks = parse_hotkey(spec)
        except ValueError as exc:
            raise ControlError(str(exc)) from exc
        self._guard_input(target)
        pressed: list[int] = []
        try:
            for vk in vks:
                self.backend.key(vk, True)
                pressed.append(vk)
                self.sleep(0.03)
        finally:
            for vk in reversed(pressed):                       # luon nha het phim, tranh ket modifier
                self.backend.key(vk, False)
                self.sleep(0.02)
        return {"pressed": spec}

    def press(self, key: str, count: int = 1, hold_ms: int = 0, target: str = "main") -> dict:
        """Nhan 1 phim `count` lan, moi lan giu `hold_ms` (vd giu W 800ms de bay camera toi)."""
        try:
            vk = vk_for(key)
        except ValueError as exc:
            raise ControlError(str(exc)) from exc
        if not 1 <= count <= 100 or not 0 <= hold_ms <= 10000:
            raise ControlError("count trong 1..100, hold_ms trong 0..10000.")
        self._guard_input(target)
        for _ in range(count):
            self.backend.key(vk, True)
            try:
                self.sleep(max(hold_ms, 30) / 1000)
            finally:
                self.backend.key(vk, False)
            self.sleep(0.05)
        return {"pressed": key, "count": count, "hold_ms": hold_ms, "is_modifier": key.lower() in MODIFIERS}

    # ------------------------------------------------------------------ tep
    PROJECT_SUFFIXES = {".tm": "twinmotion", ".udatasmith": "datasmith", ".fbx": "fbx", ".skp": "sketchup",
                        ".rvt": "revit", ".ifc": "ifc", ".obj": "obj", ".c4d": "cinema4d", ".3ds": "3ds"}

    @classmethod
    def find_files(cls, folder: str, kinds: list[str] | None = None, limit: int = 50, recursive: bool = True) -> list[dict]:
        root = Path(folder)
        if not root.is_dir():
            raise ControlError(f"Khong phai thu muc: {folder}")
        wanted = {("." + k.lower().lstrip(".")) for k in kinds} if kinds else set(cls.PROJECT_SUFFIXES)
        it = root.rglob("*") if recursive else root.glob("*")
        rows = []
        for p in it:
            try:
                if p.is_file() and p.suffix.lower() in wanted:
                    st = p.stat()
                    rows.append({"path": str(p), "kind": cls.PROJECT_SUFFIXES.get(p.suffix.lower(), p.suffix.lower()),
                                 "size_mb": round(st.st_size / 1048576, 2), "modified": st.st_mtime})
            except OSError:
                continue
        rows.sort(key=lambda r: r["modified"], reverse=True)
        for r in rows:
            r["modified"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["modified"]))
        return rows[:max(limit, 1)]

    def open_project(self, path: str, wait_s: float = 120.0) -> dict:
        p = Path(path)
        if not p.is_file():
            raise ControlError(f"Khong thay file: {path}")
        if p.suffix.lower() not in (".tm", ".udatasmith", ".fbx", ".skp", ".obj", ".ifc", ".rvt"):
            raise ControlError("Chi mo cac dinh dang Twinmotion nhan: .tm .udatasmith .fbx .skp .obj .ifc .rvt")
        if self.processes():
            raise ControlError("Twinmotion dang chay: mo file qua giao dien (tm_hotkey 'ctrl+o' roi go duong dan vao hop "
                               "thoai bang tm_type_text) hoac tm_close roi goi lai tm_open_project.")
        res = self.launch([str(p)], wait_s)
        res["opened_path"] = str(p)
        res["note"] = "Mo file qua doi so dong lenh (chua kiem chung voi 2026.1): xem tieu de cua so / chup man hinh de xac nhan."
        return res
