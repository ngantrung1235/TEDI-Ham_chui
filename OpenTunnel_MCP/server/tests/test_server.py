import asyncio
import json

import pytest

from mcp_bridge_common.testing import FakeBridge
from otd_mcp.server import create_server


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    discovery = tmp_path / "bridge.json"
    monkeypatch.setenv("OTD_MCP_DISCOVERY", str(discovery))
    monkeypatch.delenv("OTD_MCP_URL", raising=False)
    monkeypatch.delenv("OTD_MCP_TOKEN", raising=False)
    with FakeBridge() as fb:
        fb.write_discovery(discovery)
        yield fb


# ---------------------------------------------------------------- MCP server (in-process)
mcp_client = pytest.importorskip("mcp").__dict__.get("Client")


def run_with_client(coro_fn):
    if mcp_client is None:
        pytest.skip("mcp.Client (in-process) chi co tu mcp 2.x")

    async def runner():
        async with mcp_client(create_server()) as client:
            return await coro_fn(client)

    return asyncio.run(runner())


EXPECTED_TOOLS = {
    "otd_status", "otd_open_file", "otd_save_file", "otd_list_models", "otd_list_levels", "otd_ensure_level",
    "otd_query_elements", "otd_get_element", "otd_get_selection", "otd_select_elements", "otd_delete_elements",
    "otd_send_keyins", "otd_send_data_point", "otd_send_reset", "otd_get_cexpression", "otd_draw_polyline",
    "otd_create_extrusion", "otd_create_box_culvert", "otd_capture_view", "otd_explore_api", "otd_run_csharp",
    "otd_bridge_methods", "otd_ec_summary", "otd_find_by_ec_class", "otd_section_properties",
}


def test_tools_registered_with_annotations(bridge):
    tools = run_with_client(lambda c: c.list_tools())
    by_name = {t.name: t for t in tools.tools}
    assert EXPECTED_TOOLS <= set(by_name)
    assert by_name["otd_delete_elements"].annotations.destructive_hint is True
    assert by_name["otd_query_elements"].annotations.read_only_hint is True


def test_box_culvert_routes_to_extrusion(bridge):
    args = dict(start=[0, 0, 5], end=[40, 0, 5], clear_width_mm=3500, clear_height_mm=3000,
                top_slab_mm=400, bottom_slab_mm=450, wall_mm=400, cells=2, mid_wall_mm=350,
                chamfer_top_mm=200, chamfer_bottom_mm=200)
    res = run_with_client(lambda c: c.call_tool("otd_create_box_culvert", args))
    assert not res.is_error
    payload = res.structured_content or json.loads(res.content[0].text)
    assert payload["element"] == {"id": 4242, "holes": 2}
    method, params = bridge.calls[-1]
    assert method == "geometry.extrusion"
    assert params["section_plane"] == "vertical" and params["level"] == "HamChui_BeTong"
    assert len(params["loops"]) == 3


def test_box_culvert_dry_run_does_not_call_bridge(bridge):
    args = dict(start=[0, 0], end=[10, 0], clear_width_mm=2000, clear_height_mm=2000,
                top_slab_mm=300, bottom_slab_mm=300, wall_mm=300, dry_run=True)
    res = run_with_client(lambda c: c.call_tool("otd_create_box_culvert", args))
    assert not res.is_error
    assert bridge.calls == []
    payload = res.structured_content or json.loads(res.content[0].text)
    props = payload["section_properties"]
    assert props["area_m2"] == pytest.approx(payload["quantities"]["concrete_area_m2"])
    assert props["centroid_m"][0] == pytest.approx(0, abs=1e-12)        # doi xung


def test_invalid_section_is_tool_error(bridge):
    args = dict(start=[0, 0], end=[10, 0], clear_width_mm=2000, clear_height_mm=2000,
                top_slab_mm=300, bottom_slab_mm=300, wall_mm=300, cells=2)
    res = run_with_client(lambda c: c.call_tool("otd_create_box_culvert", args))
    assert res.is_error
    assert "mid_wall_mm" in res.content[0].text


def test_capture_view_returns_png_and_fits_first(bridge):
    res = run_with_client(lambda c: c.call_tool("otd_capture_view", {"fit": True}))
    assert not res.is_error
    assert res.content[0].type == "image" and res.content[0].mime_type == "image/png"
    assert [m for m, _ in bridge.calls] == ["keyin.send", "view.capture"]
    assert bridge.calls[0][1]["keyins"] == ["fit view extended"]


def test_bridge_error_surfaces_as_tool_error(bridge):
    res = run_with_client(lambda c: c.call_tool("otd_get_element", {"element_id": 999}))
    assert res.is_error
    assert "Khong tim thay element id=999" in res.content[0].text


def test_guide_resource(bridge):
    res = run_with_client(lambda c: c.read_resource("otd://guide"))
    assert "Ba lớp công cụ" in res.contents[0].text
    assert "Hầm chui" in res.contents[0].text
