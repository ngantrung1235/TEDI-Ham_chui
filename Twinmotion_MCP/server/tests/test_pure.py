"""Test phan thuan logic (khong can Windows): phim, hinh hoc, .lnk, anh, cau truc Win32."""

import ctypes
import struct

import pytest
from PIL import Image

from tm_mcp import capture, winapi
from tm_mcp.geometry import OutOfBounds, Rect, checked_screen_point, interpolate
from tm_mcp.keys import is_extended, parse_hotkey, vk_for
from tm_mcp.lnk import ShortcutError, parse_lnk_bytes


# ------------------------------------------------------------------ phim
@pytest.mark.parametrize("name,vk", [
    ("a", 0x41), ("Z", 0x5A), ("0", 0x30), ("9", 0x39), ("f1", 0x70), ("F11", 0x7A), ("f24", 0x87),
    ("enter", 0x0D), ("esc", 0x1B), ("space", 0x20), ("left", 0x25), ("num7", 0x67), ("numpad0", 0x60),
    ("ctrl", 0x11), ("shift", 0x10), ("alt", 0x12), ("win", 0x5B), ("comma", 0xBC), ("/", 0xBF),
])
def test_vk_for(name, vk):
    assert vk_for(name) == vk


@pytest.mark.parametrize("bad", ["", "f25", "ctrl+", "numpad10", "a b", "xyz"])
def test_vk_for_rejects(bad):
    with pytest.raises(ValueError):
        vk_for(bad)


def test_parse_hotkey_orders_modifiers_first_and_dedupes():
    assert parse_hotkey("ctrl+shift+s") == [0x11, 0x10, 0x53]
    assert parse_hotkey("S+Ctrl") == [0x11, 0x53]                    # modifier len truoc
    assert parse_hotkey("ctrl+control+a") == [0x11, 0x41]
    assert parse_hotkey("f11") == [0x7A]
    assert parse_hotkey("alt + f4") == [0x12, 0x73]


@pytest.mark.parametrize("bad", ["", "+", "a+b", "ctrl+a+b", "ctrl+zzz"])
def test_parse_hotkey_rejects(bad):
    with pytest.raises(ValueError):
        parse_hotkey(bad)


def test_extended_keys():
    assert is_extended(vk_for("left")) and is_extended(vk_for("delete")) and not is_extended(vk_for("a"))


# ------------------------------------------------------------------ hinh hoc
def test_checked_screen_point_maps_and_bounds():
    area = Rect(108, 81, 1372, 842)                                   # 1264 x 761
    assert checked_screen_point(area, 0, 0) == (108, 81)
    assert checked_screen_point(area, 10.4, 20.6) == (118, 102)       # lam tron
    assert checked_screen_point(area, 1263, 760) == (1371, 841)
    for x, y in [(1264, 0), (0, 761), (-1, 5), (5, -1)]:
        with pytest.raises(OutOfBounds, match="ngoai vung dieu khien"):
            checked_screen_point(area, x, y)


def test_zero_sized_area_rejected():
    with pytest.raises(OutOfBounds, match="kich thuoc 0"):
        checked_screen_point(Rect(0, 0, 0, 0), 0, 0)


def test_interpolate_ends_at_target_and_is_monotonic():
    pts = interpolate(0, 0, 100, 50, 10)
    assert pts[-1] == (100, 50) and len(pts) == 10
    assert all(b[0] >= a[0] for a, b in zip(pts, pts[1:]))
    assert interpolate(5, 5, 5, 5, 0) == [(5, 5)]


# ------------------------------------------------------------------ .lnk
CLSID = bytes.fromhex("0114020000000000c000000000000046")


def build_lnk(*, target=None, relative=None, working_dir=None, arguments=None, unicode=True, link_info=True):
    """Tao file .lnk toi thieu theo MS-SHLLINK de test bo doc."""
    flags = 0
    if link_info and target is not None:
        flags |= 0x02
    if relative is not None:
        flags |= 0x08
    if working_dir is not None:
        flags |= 0x10
    if arguments is not None:
        flags |= 0x20
    if unicode:
        flags |= 0x80
    header = struct.pack("<I", 0x4C) + CLSID + struct.pack("<I", flags) + b"\x00" * (0x4C - 4 - 16 - 4)
    assert len(header) == 0x4C
    body = b""
    if link_info and target is not None:
        base, _, suffix = target.rpartition("\\")
        local = (base + "\\").encode("cp1252") + b"\x00"
        suffix_b = suffix.encode("cp1252") + b"\x00"
        vol = struct.pack("<IIIII", 17, 3, 0, 16, 0) + b"\x00"          # VolumeID gia (khong dung)
        header_size = 0x1C
        local_off = header_size + len(vol)
        suffix_off = local_off + len(local)
        info = struct.pack("<IIIIIII", header_size + len(vol) + len(local) + len(suffix_b), header_size, 0x1,
                           header_size, local_off, 0, suffix_off) + vol + local + suffix_b
        body += info

    def sd(text):
        raw = text.encode("utf-16-le") if unicode else text.encode("cp1252")
        return struct.pack("<H", len(text)) + raw

    if relative is not None:
        body += sd(relative)
    if working_dir is not None:
        body += sd(working_dir)
    if arguments is not None:
        body += sd(arguments)
    return header + body


def test_parse_lnk_with_linkinfo_and_args():
    data = build_lnk(target=r"C:\Program Files\Twinmotion 2026.1\Twinmotion.exe",
                     working_dir=r"C:\Program Files\Twinmotion 2026.1", arguments="-revit -nosplash")
    sc = parse_lnk_bytes(data, r"C:\Users\Public\Desktop\Twinmotion 2026.1 For Revit.lnk")
    assert sc.target == r"C:\Program Files\Twinmotion 2026.1\Twinmotion.exe"
    assert sc.working_dir == r"C:\Program Files\Twinmotion 2026.1"
    assert sc.arguments == "-revit -nosplash" and sc.source == "parser"


@pytest.mark.parametrize("unicode", [True, False])
def test_parse_lnk_string_encodings(unicode):
    sc = parse_lnk_bytes(build_lnk(target=r"D:\Epic\Twinmotion.exe", arguments="abc", unicode=unicode))
    assert sc.target == r"D:\Epic\Twinmotion.exe" and sc.arguments == "abc"


def test_parse_lnk_relative_path_only_resolves_against_shortcut_dir():
    data = build_lnk(relative=r"..\Tm\Twinmotion.exe", link_info=False)
    sc = parse_lnk_bytes(data, "/x/desktop/a.lnk")
    assert sc.target.replace("\\", "/").endswith("x/Tm/Twinmotion.exe")


def test_parse_lnk_rejects_garbage():
    with pytest.raises(ShortcutError):
        parse_lnk_bytes(b"not a shortcut at all" * 10)


# ------------------------------------------------------------------ anh
def test_grid_keeps_size_adds_marks_and_validates_step():
    base = Image.new("RGB", (400, 300), (0, 0, 0))
    out = capture.draw_grid(base, 100)
    assert out.size == base.size and out.getpixel((100, 150)) != (0, 0, 0) and base.getpixel((100, 150)) == (0, 0, 0)
    with pytest.raises(ValueError):
        capture.draw_grid(base, 10)


def test_to_png_resizes_and_keeps_ratio():
    png = capture.to_png(Image.new("RGBA", (2000, 1000)), 1000)
    import io
    img = Image.open(io.BytesIO(png))
    assert img.size == (1000, 500) and img.mode == "RGB"
    assert Image.open(io.BytesIO(capture.to_png(Image.new("RGB", (800, 600)), 0))).size == (800, 600)


def test_difference_ratio():
    a = Image.new("RGB", (200, 100), (10, 10, 10))
    b = Image.new("RGB", (200, 100), (10, 10, 10))
    assert capture.difference_ratio(a, b) == 0
    b.paste((250, 250, 250), (0, 0, 100, 100))                       # nua anh doi
    assert 0.4 < capture.difference_ratio(a, b) < 0.6
    assert capture.difference_ratio(a, Image.new("RGB", (10, 10))) == 1.0


def test_wait_until_stable_detects_settling():
    still = Image.new("RGB", (100, 100), (5, 5, 5))
    moving = [Image.new("RGB", (100, 100), (i * 40, 0, 0)) for i in range(1, 4)]
    frames = iter(moving + [still] * 10)
    now = {"t": 0.0}
    res = capture.wait_until_stable(lambda: next(frames), timeout_s=30, interval_s=1.0, stable_frames=3,
                                    sleep=lambda s: now.__setitem__("t", now["t"] + s), clock=lambda: now["t"])
    assert res["stable"] is True and res["frames"] <= 8


def test_wait_until_stable_times_out_on_constant_motion():
    n = {"i": 0}

    def grab():
        n["i"] += 1
        return Image.new("RGB", (100, 100), ((n["i"] * 60) % 256, 0, 0))

    now = {"t": 0.0}
    res = capture.wait_until_stable(grab, timeout_s=5, interval_s=1.0, sleep=lambda s: now.__setitem__("t", now["t"] + s),
                                    clock=lambda: now["t"])
    assert res["stable"] is False and res["waited_s"] >= 5


# ------------------------------------------------------------------ cau truc Win32
def test_win32_struct_sizes_match_x64_layout():
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        pytest.skip("kich thuoc INPUT chi kiem chung cho 64-bit")
    assert ctypes.sizeof(winapi.INPUT) == 40
    assert ctypes.sizeof(winapi.MOUSEINPUT) == 32 and ctypes.sizeof(winapi.KEYBDINPUT) == 24
    assert ctypes.sizeof(winapi.RECT) == 16 and ctypes.sizeof(winapi.POINT) == 8


def test_backend_refuses_off_windows():
    if winapi.IS_WINDOWS:
        pytest.skip("chi kiem tra tren he khac Windows")
    with pytest.raises(OSError, match="chi chay tren Windows"):
        winapi.WindowsBackend().prepare()


def test_unicode_typing_splits_surrogate_pairs():
    sent = []

    class Spy(winapi.WindowsBackend):
        def prepare(self):
            pass

        def _send(self, *inputs):
            sent.extend((i.ki.wScan, i.ki.dwFlags) for i in inputs)

    Spy().type_text("a😀")                                           # 😀 = U+1F600 -> cap thay the D83D DE00
    downs = [scan for scan, flags in sent if not flags & winapi.KEYEVENTF_KEYUP]
    assert downs == [0x61, 0xD83D, 0xDE00]
    assert all(flags & winapi.KEYEVENTF_UNICODE for _, flags in sent)
