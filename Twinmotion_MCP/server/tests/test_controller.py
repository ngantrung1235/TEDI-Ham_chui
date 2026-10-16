"""Test TwinmotionController voi backend/tien trinh gia: logic an toan, anh xa toa do, vong doi tien trinh."""

import io
from dataclasses import replace

import pytest
from PIL import Image

from tm_mcp.controller import ControlError, Settings, TwinmotionController
from tm_mcp.keys import vk_for
from tm_mcp.testing import FakeBackend, FakeProcessApi, make_proc, make_window

EXE = r"C:\Program Files\Twinmotion\Twinmotion.exe"


class Clock:
    """Dong ho gia: sleep() chi cong don thoi gian, khong ngu that."""

    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def now(self):
        return self.t


def make(running=True, **settings_kw):
    clock = Clock()
    win = make_window()
    backend = FakeBackend([win] if running else [])
    proc = FakeProcessApi([make_proc()] if running else [])
    settings = Settings(shortcut="X.lnk", exe=EXE, **settings_kw)
    ctl = TwinmotionController(backend, proc, settings, sleep=clock.sleep, clock=clock.now)
    return ctl, backend, proc, clock


def actions(backend, kind):
    return [a for a in backend.actions if a[0] == kind]


# ------------------------------------------------------------------ trang thai / vong doi
def test_status_running_and_not_running():
    ctl, backend, *_ = make(running=True)
    st = ctl.status()
    assert st["running"] and st["main_window"]["title"].startswith("Twinmotion") and st["input_enabled"] is True
    assert st["main_window_is_foreground"] is True
    ctl2, *_ = make(running=False)
    st2 = ctl2.status()
    assert st2["running"] is False and st2["main_window"] is None


def test_main_window_prefers_twinmotion_titled_and_largest():
    ctl, backend, *_ = make()
    backend.windows.append(make_window(hwnd=101, title="Save As", width=500, height=300))
    backend.windows.append(make_window(hwnd=102, title="Twinmotion 2026.1 - Splash", width=300, height=200))
    assert ctl.main_window().hwnd == 100
    backend.windows.append(make_window(hwnd=103, pid=9999, title="Twinmotion web page", width=3000, height=2000))   # tien trinh khac
    assert ctl.main_window().hwnd == 100


def test_launch_waits_for_window_and_avoids_second_instance(monkeypatch):
    ctl, backend, proc, clock = make(running=False)
    monkeypatch.setattr("os.path.exists", lambda p: True)

    def appear():
        proc.procs.append(make_proc())
        backend.windows.append(make_window())

    proc.on_launch = appear
    res = ctl.launch(["x.tm"], wait_s=30)
    assert res["launched"] and res["main_window"]["pid"] == 4242
    assert proc.launched == [(EXE, None, ["x.tm"], None)]
    again = ctl.launch()
    assert again["already_running"] and len(proc.launched) == 1


def test_launch_times_out_gracefully(monkeypatch):
    ctl, backend, proc, clock = make(running=False)
    monkeypatch.setattr("os.path.exists", lambda p: True)
    res = ctl.launch(wait_s=5)
    assert res["launched"] and res.get("window_ready") is False and "tm_status" in res["note"]


def test_close_graceful_with_save_dialog_then_force():
    ctl, backend, proc, clock = make()
    proc.survives_terminate = False
    # Dong em nhung tien trinh van song (hop thoai hoi luu)
    res = ctl.close(wait_s=3)
    assert actions(backend, "close") and res["closed"] is False and "force" in res["reason"]
    forced = ctl.close(force=True)
    assert forced["closed"] and forced["forced"] and proc.terminated == [(4242, True)]


def test_force_close_can_be_disabled():
    ctl, *_ = make(allow_kill=False)
    with pytest.raises(ControlError, match="TM_MCP_ALLOW_KILL"):
        ctl.close(force=True)


def test_requires_running_app():
    ctl, *_ = make(running=False)
    with pytest.raises(ControlError, match="chua chay"):
        ctl.screenshot()


# ------------------------------------------------------------------ chuot
def test_click_maps_client_coordinates_to_screen():
    ctl, backend, *_ = make()
    client = make_window().client                       # left=108, top=81
    res = ctl.click(10, 20)
    assert res["clicked"] == [client.left + 10, client.top + 20]
    assert actions(backend, "move") == [("move", 118, 101)]
    assert [a[1:] for a in actions(backend, "button")] == [("left", True), ("left", False)]


def test_double_click_and_right_click():
    ctl, backend, *_ = make()
    ctl.click(5, 5, button="right", double=True)
    assert [a[1:] for a in actions(backend, "button")] == [("right", True), ("right", False)] * 2
    with pytest.raises(ControlError):
        ctl.click(5, 5, button="back")


@pytest.mark.parametrize("x,y", [(-1, 10), (10, -1), (5000, 10), (10, 5000)])
def test_out_of_bounds_click_is_rejected_without_any_input(x, y):
    ctl, backend, *_ = make()
    before = len(backend.actions)
    with pytest.raises(ControlError, match="ngoai vung dieu khien"):
        ctl.click(x, y)
    assert not [a for a in backend.actions[before:] if a[0] in ("move", "button", "key", "text", "wheel", "rel")]


def test_failsafe_corner_stops_everything():
    ctl, backend, *_ = make()
    backend.cursor = (0, 0)
    with pytest.raises(ControlError, match="CHOT AN TOAN"):
        ctl.click(10, 10)
    with pytest.raises(ControlError, match="CHOT AN TOAN"):
        ctl.hotkey("ctrl+s")
    assert not actions(backend, "button") and not actions(backend, "key")


def test_read_only_mode_blocks_all_input_but_not_screenshot():
    ctl, backend, *_ = make(input_enabled=False)
    for fn in (lambda: ctl.click(1, 1), lambda: ctl.move(1, 1), lambda: ctl.type_text("a"), lambda: ctl.hotkey("a"),
               lambda: ctl.press("w"), lambda: ctl.scroll(1, 1, 1), lambda: ctl.drag(1, 1, 5, 5)):
        with pytest.raises(ControlError, match="CHI-DOC"):
            fn()
    png, _ = ctl.screenshot()
    assert png.startswith(b"\x89PNG")


def test_foreground_must_be_twinmotion_never_types_into_other_app():
    ctl, backend, *_ = make()
    backend.foreground = 555                              # cua so cua ung dung khac
    backend.focus_works = False                           # Windows chan viec chiem foreground
    with pytest.raises(ControlError):
        ctl.type_text("mat khau bi mat")
    assert not actions(backend, "text") and not actions(backend, "key")


def test_refocuses_main_window_when_other_app_is_foreground():
    ctl, backend, *_ = make()
    backend.foreground = 555
    ctl.hotkey("ctrl+s")
    assert ("focus", 100) in backend.actions and backend.foreground == 100
    assert actions(backend, "key")


def test_does_not_steal_focus_from_app_dialog():
    ctl, backend, *_ = make()
    dialog = make_window(hwnd=101, title="Save As", left=300, top=200, width=600, height=400)
    backend.windows.append(dialog)
    backend.foreground = 101
    ctl.hotkey("enter")
    assert not actions(backend, "focus")                  # dang o hop thoai cua chinh Twinmotion: giu nguyen
    res = ctl.click(10, 10, target="active")
    assert res["clicked"] == [dialog.client.left + 10, dialog.client.top + 10]


def test_minimized_window_is_rejected():
    ctl, backend, *_ = make()
    backend.windows = [replace(backend.windows[0], minimized=True)]
    with pytest.raises(ControlError, match="thu nho"):
        ctl.click(10, 10)


def test_drag_uses_relative_moves_and_always_releases_button():
    ctl, backend, *_ = make()
    res = ctl.drag(100, 100, 300, 200, button="right", duration_ms=320)
    rel = actions(backend, "rel")
    assert len(rel) == res["steps"] >= 8
    assert sum(a[1] for a in rel) == 200 and sum(a[2] for a in rel) == 100        # tong dich chuyen dung
    buttons = [a[1:] for a in actions(backend, "button")]
    assert buttons == [("right", True), ("right", False)]
    assert backend.cursor == (108 + 300, 81 + 200)


def test_drag_releases_button_even_if_move_fails():
    ctl, backend, *_ = make()

    def boom(dx, dy):
        raise OSError("SendInput that bai")

    backend.mouse_move_relative = boom
    with pytest.raises(OSError):
        ctl.drag(10, 10, 50, 50)
    assert actions(backend, "button")[-1][1:] == ("left", False)


@pytest.mark.parametrize("kw", [dict(duration_ms=10), dict(duration_ms=99999)])
def test_drag_validates_duration(kw):
    ctl, *_ = make()
    with pytest.raises(ControlError, match="duration_ms"):
        ctl.drag(1, 1, 5, 5, **kw)


def test_scroll_direction_and_limits():
    ctl, backend, *_ = make()
    ctl.scroll(10, 10, 3)
    ctl.scroll(10, 10, -2)
    assert [a[1] for a in actions(backend, "wheel")] == [1, 1, 1, -1, -1]
    for bad in (0, 51):
        with pytest.raises(ControlError):
            ctl.scroll(10, 10, bad)


# ------------------------------------------------------------------ ban phim
def test_hotkey_presses_in_order_and_releases_in_reverse():
    ctl, backend, *_ = make()
    ctl.hotkey("ctrl+shift+s")
    keys = [(a[1], a[2]) for a in actions(backend, "key")]
    ctrl, shift, s = vk_for("ctrl"), vk_for("shift"), vk_for("s")
    assert keys == [(ctrl, True), (shift, True), (s, True), (s, False), (shift, False), (ctrl, False)]


def test_hotkey_releases_pressed_keys_if_a_key_fails():
    ctl, backend, *_ = make()
    real = backend.key
    calls = {"n": 0}

    def flaky(vk, down):
        calls["n"] += 1
        if calls["n"] == 3 and down:
            raise OSError("loi giua chung")
        real(vk, down)

    backend.key = flaky
    with pytest.raises(OSError):
        ctl.hotkey("ctrl+shift+s")
    ups = [a[1] for a in actions(backend, "key") if a[2] is False]
    assert set(ups) == {vk_for("ctrl"), vk_for("shift")}                   # modifier khong bi ket


def test_invalid_hotkey_is_reported_before_any_input():
    ctl, backend, *_ = make()
    with pytest.raises(ControlError, match="Phim"):
        ctl.hotkey("ctrl+zzz")
    assert not actions(backend, "key")


def test_type_text_chunks_and_limits():
    ctl, backend, *_ = make()
    ctl.type_text("x" * 100)
    assert [len(a[1]) for a in actions(backend, "text")] == [40, 40, 20]
    backend.actions.clear()
    ctl.type_text("Dầm", interval_ms=10)
    assert [a[1] for a in actions(backend, "text")] == ["D", "ầ", "m"]
    with pytest.raises(ControlError):
        ctl.type_text("")
    with pytest.raises(ControlError, match="qua dai"):
        ctl.type_text("y" * 2001)


def test_press_holds_key():
    ctl, backend, _, clock = make()
    t0 = clock.t
    ctl.press("w", count=2, hold_ms=500)
    assert [a[2] for a in actions(backend, "key")] == [True, False, True, False]
    assert clock.t - t0 >= 1.0
    with pytest.raises(ControlError):
        ctl.press("w", count=0)


# ------------------------------------------------------------------ chup man hinh
def test_screenshot_meta_scale_and_png():
    ctl, backend, *_ = make()
    png, meta = ctl.screenshot(max_width=600)
    img = Image.open(io.BytesIO(png))
    client = make_window().client
    assert meta["width"] == client.width and meta["height"] == client.height
    assert meta["origin_screen"] == [client.left, client.top]
    assert img.width == 600 and abs(meta["scale"] - 600 / client.width) < 1e-3
    assert ("grab", client.as_tuple()) in backend.actions
    full, meta2 = ctl.screenshot(max_width=0, grid=200, mark=(100, 100))
    assert Image.open(io.BytesIO(full)).width == client.width and meta2["scale"] == 1.0


def test_screenshot_window_area_and_active_target():
    ctl, backend, *_ = make()
    win = make_window()
    ctl.screenshot(area="window")
    assert ("grab", win.rect.as_tuple()) in backend.actions
    with pytest.raises(ControlError, match="foreground"):
        backend.foreground = 555
        ctl.screenshot(target="active")
    with pytest.raises(ControlError, match="target"):
        ctl.screenshot(target="screen")


def test_wait_stable_uses_client_area():
    ctl, backend, *_ = make()
    still = Image.new("RGB", (100, 100), (9, 9, 9))
    backend.frames = [Image.new("RGB", (100, 100), (200, 0, 0)), still]
    res = ctl.wait_stable(timeout_s=30, interval_s=1.0, stable_frames=2)
    assert res["stable"] is True


# ------------------------------------------------------------------ cua so / tep
def test_set_window_state_and_geometry():
    ctl, backend, *_ = make()
    info = ctl.set_window("maximize")
    assert info["maximized"] is True
    info = ctl.set_window(x=0, y=0, width=1600, height=900)
    assert info["rect"]["width"] == 1600
    with pytest.raises(ControlError):
        ctl.set_window("explode")


def test_focus_failure_is_explained():
    ctl, backend, *_ = make()
    backend.focus_works = False
    with pytest.raises(ControlError, match="foreground"):
        ctl.focus()


def test_find_files_sorted_by_mtime_and_filtered(tmp_path):
    import os
    a, b, c = tmp_path / "a.tm", tmp_path / "sub" / "b.udatasmith", tmp_path / "c.txt"
    b.parent.mkdir()
    for p in (a, b, c):
        p.write_bytes(b"x" * 1024)
    os.utime(a, (1_000_000, 1_000_000))
    os.utime(b, (2_000_000, 2_000_000))
    rows = TwinmotionController.find_files(str(tmp_path))
    assert [r["path"] for r in rows] == [str(b), str(a)] and rows[0]["kind"] == "datasmith"
    assert [r["path"] for r in TwinmotionController.find_files(str(tmp_path), ["tm"])] == [str(a)]
    assert not TwinmotionController.find_files(str(tmp_path), recursive=False, kinds=["udatasmith"])
    with pytest.raises(ControlError):
        TwinmotionController.find_files(str(tmp_path / "khong_co"))


def test_open_project_rules(tmp_path, monkeypatch):
    f = tmp_path / "ham.tm"
    f.write_bytes(b"x")
    ctl, backend, proc, clock = make(running=True)
    with pytest.raises(ControlError, match="dang chay"):
        ctl.open_project(str(f))
    (tmp_path / "x.exe").write_bytes(b"x")
    with pytest.raises(ControlError, match="Chi mo"):
        make(running=False)[0].open_project(str(tmp_path / "x.exe"))
    with pytest.raises(ControlError, match="Khong thay file"):
        make(running=False)[0].open_project(str(tmp_path / "nope.tm"))
    ctl2, backend2, proc2, _ = make(running=False)
    monkeypatch.setattr("os.path.exists", lambda p: True)
    proc2.on_launch = lambda: (proc2.procs.append(make_proc()), backend2.windows.append(make_window()))
    res = ctl2.open_project(str(f), wait_s=10)
    assert res["launched"] and proc2.launched[0][2] == [str(f)] and res["opened_path"] == str(f)


def test_settings_from_env():
    s = Settings.from_env({"TM_SHORTCUT": "a.lnk", "TM_EXE": "b.exe", "TM_MCP_ALLOW_INPUT": "0", "TM_MCP_ALLOW_KILL": "0"})
    assert (s.shortcut, s.exe, s.input_enabled, s.allow_kill) == ("a.lnk", "b.exe", False, False)
    d = Settings.from_env({})
    assert d.shortcut.endswith("Twinmotion 2026.1 For Revit.lnk") and d.input_enabled and d.allow_kill


def test_focus_reported_ok_but_foreground_still_other_app_is_still_rejected():
    ctl, backend, *_ = make()
    backend.foreground = 555
    backend.focus = lambda hwnd: True                 # focus() "thanh cong" nhung foreground van la app khac (race)
    with pytest.raises(ControlError, match="khong phai Twinmotion"):
        ctl.type_text("khong duoc gui")
    assert not actions(backend, "text")
