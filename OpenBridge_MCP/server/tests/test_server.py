import asyncio
import json

import pytest

from mcp_bridge_common.testing import FakeBridge
from obd_mcp.server import create_server

mcp_client = pytest.importorskip("mcp").__dict__.get("Client")


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    discovery = tmp_path / "bridge.json"
    monkeypatch.setenv("OBD_MCP_DISCOVERY", str(discovery))
    monkeypatch.delenv("OBD_MCP_URL", raising=False)
    monkeypatch.delenv("OBD_MCP_TOKEN", raising=False)
    with FakeBridge() as fb:
        fb.write_discovery(discovery)
        yield fb


def run_with_client(coro_fn):
    if mcp_client is None:
        pytest.skip("mcp.Client (in-process) chi co tu mcp 2.x")

    async def runner():
        async with mcp_client(create_server()) as client:
            return await coro_fn(client)

    return asyncio.run(runner())


def payload(res):
    assert not res.is_error, res.content[0].text
    return res.structured_content or json.loads(res.content[0].text)


GIRDER = dict(height_mm=1650, top_flange_width_mm=800, top_flange_thickness_mm=180, top_haunch_height_mm=100,
              web_thickness_mm=200, bottom_flange_width_mm=650, bottom_flange_thickness_mm=230,
              bottom_haunch_height_mm=225)


def test_tools_registered(bridge):
    tools = run_with_client(lambda c: c.list_tools())
    names = {t.name for t in tools.tools}
    assert {"obd_status", "obd_send_keyins", "obd_run_csharp", "obd_ec_summary", "obd_find_by_ec_class",
            "obd_section_properties", "obd_create_girders", "obd_create_deck_slab", "obd_create_pier"} <= names
    assert not any(n.startswith("otd_") for n in names)


def test_girders_create_one_extrusion_per_girder_with_offsets(bridge):
    args = dict(start=[0, 0, 10], end=[33, 0, 10], count=5, spacing_mm=2400, **GIRDER)
    out = payload(run_with_client(lambda c: c.call_tool("obd_create_girders", args)))
    calls = [p for m, p in bridge.calls if m == "geometry.extrusion"]
    assert len(calls) == 5 and len(out["elements"]) == 5
    assert [round(p["origin"][1], 6) for p in calls] == [-4.8, -2.4, 0.0, 2.4, 4.8]
    assert all(p["level"] == "Dam_BeTong" and len(p["loops"]) == 1 for p in calls)
    assert out["concrete_volume_total_m3"] == pytest.approx(5 * out["concrete_volume_per_girder_m3"], rel=1e-3)


def test_girder_dry_run_with_composite(bridge):
    args = dict(start=[0, 0], end=[33, 0], slab_effective_width_mm=2400, slab_thickness_mm=200,
                slab_haunch_mm=50, modular_ratio=0.85, dry_run=True, **GIRDER)
    out = payload(run_with_client(lambda c: c.call_tool("obd_create_girders", args)))
    assert bridge.calls == []
    g, c = out["section_properties_mm"], out["composite_properties_mm"]
    assert c["Ix_mm4"] > g["Ix_mm4"] and c["centroid_mm"][1] > g["centroid_mm"][1]


def test_composite_needs_both_slab_params(bridge):
    args = dict(start=[0, 0], end=[33, 0], slab_effective_width_mm=2400, dry_run=True, **GIRDER)
    res = run_with_client(lambda c: c.call_tool("obd_create_girders", args))
    assert res.is_error and "slab_thickness_mm" in res.content[0].text


def test_pier_creates_vertical_components(bridge):
    args = dict(base_point=[500, 800, 2.5], orientation_deg=30, footing_length_mm=9000, footing_width_mm=4000,
                footing_thickness_mm=2000, column_count=2, column_height_mm=7000, column_spacing_mm=5000,
                cap_length_mm=9500, cap_width_mm=1800, cap_depth_mm=1600, column_diameter_mm=1500)
    out = payload(run_with_client(lambda c: c.call_tool("obd_create_pier", args)))
    calls = [p for m, p in bridge.calls if m == "geometry.extrusion"]
    assert [e["name"] for e in out["elements"]] == ["be_tru", "cot_1", "cot_2", "xa_mu"]
    assert all(p["section_plane"] == "perpendicular" for p in calls)
    assert all(p["origin"][:2] == p["end"][:2] for p in calls)          # dun thang dung
    assert out["quantities"]["elevation_top_cap_m"] == pytest.approx(2.5 + 2 + 7 + 1.6)


def test_invalid_pier_is_tool_error(bridge):
    args = dict(base_point=[0, 0, 0], orientation_deg=0, footing_length_mm=4000, footing_width_mm=4000,
                footing_thickness_mm=2000, column_count=2, column_height_mm=7000, column_spacing_mm=5000,
                cap_length_mm=9500, cap_width_mm=1800, cap_depth_mm=1600, column_diameter_mm=1500)
    res = run_with_client(lambda c: c.call_tool("obd_create_pier", args))
    assert res.is_error and "vuot ra ngoai be" in res.content[0].text
    assert bridge.calls == []


def test_deck_slab_routes_to_extrusion(bridge):
    args = dict(start=[0, 0, 12], end=[40, 0, 12.4], width_mm=12000, thickness_mm=200)
    out = payload(run_with_client(lambda c: c.call_tool("obd_create_deck_slab", args)))
    assert out["area_m2"] == pytest.approx(2.4)
    method, params = bridge.calls[-1]
    assert method == "geometry.extrusion" and params["level"] == "BanMatCau"


def test_ec_tools_and_guide(bridge):
    out = payload(run_with_client(lambda c: c.call_tool("obd_find_by_ec_class", {"class_name": "Pier"})))
    assert out == {"echo": "ec.find"}
    assert bridge.calls[-1][1]["class_name"] == "Pier"
    res = run_with_client(lambda c: c.read_resource("obd://guide"))
    text = res.contents[0].text
    assert "OpenBridge Designer 2026" in text and "obd_ec_summary" in text and "otd_" not in text
