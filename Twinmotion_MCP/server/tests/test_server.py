import asyncio
import io
import json

import pytest
from PIL import Image

from tm_mcp.controller import Settings, TwinmotionController
from tm_mcp.server import create_server
from tm_mcp.testing import FakeBackend, FakeProcessApi, make_proc, make_window

mcp_client = pytest.importorskip("mcp").__dict__.get("Client")

EXPECTED = {
    "tm_status", "tm_resolve_shortcut", "tm_launch", "tm_open_project", "tm_close", "tm_list_windows", "tm_focus",
    "tm_set_window", "tm_screenshot", "tm_wait_stable", "tm_click", "tm_move", "tm_drag", "tm_scroll", "tm_type_text",
    "tm_hotkey", "tm_press", "tm_uia_tree", "tm_uia_invoke", "tm_find_files",
}


def make_controller(**kw):
    backend = FakeBackend([make_window()])
    ctl = TwinmotionController(backend, FakeProcessApi([make_proc()]),
                               Settings(shortcut="X.lnk", exe=r"C:\Tm\Twinmotion.exe", **kw), sleep=lambda s: None)
    return ctl, backend


def run(ctl, coro_fn):
    if mcp_client is None:
        pytest.skip("mcp.Client (in-process) chi co tu mcp 2.x")

    async def runner():
        async with mcp_client(create_server(ctl)) as client:
            return await coro_fn(client)

    return asyncio.run(runner())


def call(ctl, name, args=None):
    return run(ctl, lambda c: c.call_tool(name, args or {}))


def test_tools_registered_with_annotations():
    ctl, _ = make_controller()
    tools = run(ctl, lambda c: c.list_tools())
    by_name = {t.name: t for t in tools.tools}
    assert set(by_name) == EXPECTED
    assert by_name["tm_screenshot"].annotations.read_only_hint is True
    assert by_name["tm_click"].annotations.destructive_hint is True
    assert by_name["tm_close"].annotations.destructive_hint is True
    assert "{product}" not in (by_name["tm_screenshot"].description or "")
    assert "tm_screenshot" in by_name["tm_click"].description


def test_status_and_windows():
    ctl, _ = make_controller()
    st = call(ctl, "tm_status")
    data = st.structured_content or json.loads(st.content[0].text)
    assert data["running"] is True and data["main_window"]["title"].startswith("Twinmotion")


def test_screenshot_returns_image_and_meta():
    ctl, backend = make_controller()
    res = call(ctl, "tm_screenshot", {"max_width": 640, "grid": 100, "mark_x": 50, "mark_y": 60})
    assert not res.is_error
    assert [c.type for c in res.content] == ["image", "text"]
    meta = json.loads(res.content[1].text)
    assert meta["width"] == 1264 and abs(meta["scale"] - 640 / 1264) < 1e-3
    img = Image.open(io.BytesIO(__import__("base64").b64decode(res.content[0].data)))
    assert img.width == 640


def test_screenshot_rejects_tiny_grid():
    ctl, _ = make_controller()
    res = call(ctl, "tm_screenshot", {"grid": 5})
    assert res.is_error and "grid" in res.content[0].text


def test_click_errors_are_tool_errors_with_clear_message():
    ctl, backend = make_controller()
    res = call(ctl, "tm_click", {"x": 99999, "y": 5})
    assert res.is_error and "ngoai vung dieu khien" in res.content[0].text
    ok = call(ctl, "tm_click", {"x": 10, "y": 10, "button": "right"})
    assert not ok.is_error
    assert [a[1:] for a in backend.actions if a[0] == "button"] == [("right", True), ("right", False)]


def test_read_only_mode_surfaces_through_mcp():
    ctl, backend = make_controller(input_enabled=False)
    res = call(ctl, "tm_hotkey", {"keys": "ctrl+s"})
    assert res.is_error and "CHI-DOC" in res.content[0].text
    assert not [a for a in backend.actions if a[0] == "key"]
    assert not call(ctl, "tm_screenshot").is_error


def test_hotkey_and_type_text_and_press():
    ctl, backend = make_controller()
    assert not call(ctl, "tm_hotkey", {"keys": "ctrl+a"}).is_error
    assert not call(ctl, "tm_type_text", {"text": "D:\\Du an\\Hầm chui.tm"}).is_error
    assert not call(ctl, "tm_press", {"key": "enter"}).is_error
    assert ("text", "D:\\Du an\\Hầm chui.tm") in backend.actions


def test_find_files_tool(tmp_path):
    (tmp_path / "a.tm").write_bytes(b"x")
    ctl, _ = make_controller()
    res = call(ctl, "tm_find_files", {"folder": str(tmp_path)})
    rows = res.structured_content.get("result") if res.structured_content and "result" in res.structured_content else json.loads(res.content[0].text)
    assert not res.is_error and "a.tm" in json.dumps(rows)


def test_guide_resource_mentions_limits_and_safety():
    ctl, _ = make_controller()
    text = run(ctl, lambda c: c.read_resource("tm://guide")).contents[0].text
    assert "không có API" in text and "Chốt an toàn" in text and "Direct Link" in text and "scale" in text


def test_default_controller_refuses_off_windows(monkeypatch):
    import sys
    if sys.platform == "win32":
        pytest.skip("chi kiem tra tren he khac Windows")
    if mcp_client is None:
        pytest.skip("mcp.Client chi co tu mcp 2.x")

    async def runner():
        async with mcp_client(create_server()) as client:
            return await client.call_tool("tm_status", {})

    res = asyncio.run(runner())
    assert res.is_error and "Windows" in res.content[0].text
