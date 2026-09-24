import asyncio

import pytest

from fake_plaxis import factory
from plaxis3d_mcp.engineering import culvert, traffic
from plaxis3d_mcp.ops import geometry, materials, project, staging
from plaxis3d_mcp.session import PlaxisSession, Settings


@pytest.fixture
def sess():
    g, make = factory()
    s = PlaxisSession(Settings(password="x"), server_factory=make)
    s.connect_input()
    s.fake = g
    return s


# -- traffic (TCVN 11823-3:2017) ------------------------------------------------------
def test_dynamic_allowance():
    assert traffic.dynamic_allowance_buried(0.0) == pytest.approx(33.0)
    assert traffic.dynamic_allowance_buried(1.5) == pytest.approx(33 * (1 - 0.615))
    assert traffic.dynamic_allowance_buried(3.0) == 0.0  # 33(1-1.23) < 0


def test_single_wheel_spread():
    # H = 0.6 m, LLDF 1.15: 0.94 x 1.20 m patch, wheels 1.8 m apart do not overlap
    d = traffic.pressure_at_depth("truck", 1, 0.6, 1.15)
    assert d["load"] == pytest.approx(72.5)
    assert d["pressure"] == pytest.approx(72.5 / ((0.25 + 0.69) * (0.51 + 0.69)))


def test_axle_wheels_merge_when_overlapping():
    # H = 2.0 m: transverse 0.51+2.3 = 2.81 > 1.8 -> both wheels of an axle merge,
    # longitudinal 0.25+2.3 = 2.55 < 4.3 -> truck axles stay separate
    d = traffic.pressure_at_depth("truck", 1, 2.0, 1.15)
    assert d["load"] == pytest.approx(145.0)
    assert d["width_transverse"] == pytest.approx(1.8 + 2.81)
    # tandem axles 1.2 m apart merge longitudinally as well
    t = traffic.pressure_at_depth("tandem", 1, 2.0, 1.15)
    assert t["load"] == pytest.approx(220.0)


def test_hl93_warnings():
    shallow = traffic.hl93_through_fill(0.4)
    assert any("0.6 m" in w for w in shallow["warnings"])
    deep = traffic.hl93_through_fill(4.0, clear_span=3.0)
    assert any("neglected" in w for w in deep["warnings"])
    assert shallow["governing"]["m"] == 1.2


# -- culvert layout ------------------------------------------------------------------------
def test_layout_default():
    p = culvert.BoxCulvertParams()
    lay = culvert.layout(p)
    assert lay["xw"] == pytest.approx(2.2)
    assert lay["z_top_slab"] == pytest.approx(0.25 + 3.2 + 0.225)
    assert lay["embankment_height"] == pytest.approx(lay["z_top_slab"] + 0.225 + 1.5)
    assert lay["culvert_length"] == pytest.approx(12 + 2 * 1.5 * 1.5)
    # the top block never extends beyond the culvert ends
    assert max(abs(y) for y, _ in lay["top_block"]) <= lay["culvert_length"] / 2 + 1e-9
    assert min(z for _, z in lay["top_block"]) == pytest.approx(lay["z_top_slab"])
    assert lay["headwall_top"] > lay["z_top_slab"]


def test_oriented_normal():
    pts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]  # normal +z
    assert culvert.oriented(pts, (0, 0, 1)) == pts
    assert culvert.oriented(pts, (0, 0, -1)) == list(reversed(pts))


def test_clip():
    square = [(0, 0), (2, 0), (2, 2), (0, 2)]
    assert culvert._area2d(culvert.clip(square, 0, 1, keep_above=True)) == pytest.approx(2)
    assert culvert.clip(square, 0, 5, keep_above=True) == []


# -- ops against the fake PLAXIS -----------------------------------------------------------
def test_material_name_and_rejected_props(sess):
    sess.fake.rejected.add("Gamma")
    r = materials.create_concrete_plate_material(sess, "B30", 0.4, "Wall")
    mat = sess.fake.registry[r["material"]]
    assert mat._props["Identification"] == "Wall"
    assert mat._props["E1"] == 32.5e6
    assert any("Gamma" in w for w in r["warnings"])


def test_borehole_levels(sess):
    geometry.create_borehole(sess, 0, 0, [0, -3, -12])
    assert len(sess.fake.Soillayers) == 2
    assert ("level", 2, -12.0) in sess.fake.log
    with pytest.raises(RuntimeError):
        geometry.create_borehole(sess, 0, 0, [0, 5])
    with pytest.raises(RuntimeError):
        geometry.create_borehole(sess, 0, 0, [0, 0])


def test_plate_and_staged_toggle(sess):
    r = geometry.create_plate(sess, [(0, 0, 0), (1, 0, 0), (1, 1, 0)], interfaces="both")
    assert r["plate"] == "Plate_1" and len(r["interfaces"]) == 2
    ph = staging.create_phase(sess, "Stage 1", activate=["Plate_1", "Missing_9"])
    assert sess.fake.registry["Plate_1"].calls == [("activate", ph["phase"])]
    assert any("Missing_9" in w for w in ph["warnings"])


def test_set_properties_resolves_references(sess):
    geometry.create_plate(sess, [(0, 0, 0), (1, 0, 0), (1, 1, 0)])
    with pytest.raises(RuntimeError, match="PlateMat_9"):  # unknown reference is an error
        project.set_object_properties(sess, "Plate_1", {"Material": "@PlateMat_9"})
    materials.create_material(sess, "plate", {"name": "Slab", "d": 0.5})
    assert project.set_object_properties(sess, "Plate_1", {"Material": "@PlateMat_1"})["ok"]
    assert sess.fake.registry["Plate_1"]._props["Material"] is sess.fake.registry["PlateMat_1"]


def test_run_python_is_gated(sess):
    with pytest.raises(RuntimeError, match="disabled"):
        project.run_python(sess, "result = 1")
    sess.settings.allow_python = True
    assert project.run_python(sess, "print('hi'); result = 2")["result"] == 2


def test_build_box_culvert(sess):
    out = culvert.build_box_culvert(sess, culvert.BoxCulvertParams())
    g = sess.fake
    # 4 culvert plates + 4 wing walls + 2 headwalls, each with one positive interface
    assert len(out["plates"]) == 10 and len(out["interfaces"]) == 10
    assert len(out["embankment_soils"]) == 3
    assert len(out["traffic_loads"]) == 6  # truck: 3 axles x 2 wheels
    # wheel pressure = 72.5 / (0.51*0.25) * 1.2 * (1 + IM)
    im = traffic.dynamic_allowance_buried(1.5)
    heavy = min(g.registry[n]._props["sigz"] for n in out["traffic_loads"])
    assert heavy == pytest.approx(-72.5 / 0.1275 * 1.2 * (1 + im / 100))
    # phases: Initial + 3
    assert [p["identification"] for p in out["phases"]][1:] == [
        "01 Culvert construction", "02 Embankment fill", "03 HL-93 traffic"]
    init = g.registry["InitialPhase"]
    assert init._props["DeformCalcType"] == "K0 procedure"
    for soil in out["embankment_soils"].values():
        calls = g.registry[soil].calls
        assert calls[0] == ("deactivate", "InitialPhase") and calls[1][0] == "activate"
    # plates oriented with the positive side towards the soil
    bottom = g.registry[out["plates"]["bottom_slab"]]._props["surface"]._props["points"]
    assert culvert._normal(list(bottom))[2] < 0


def test_build_rejects_layer_mismatch(sess):
    with pytest.raises(RuntimeError, match="2 soil layers"):
        culvert.build_box_culvert(sess, culvert.BoxCulvertParams(layer_levels=[0, -5, -20]))
    assert sess.fake.PlateMat == []  # nothing created


def test_server_registers_tools():
    from plaxis3d_mcp import server

    async def names():
        tools = await server.mcp.list_tools()
        return {t.name for t in tools}

    got = asyncio.run(names())
    for t in ("plaxis_connect", "build_box_culvert", "results_plate_forces", "hl93_live_load_through_fill"):
        assert t in got


def test_build_box_culvert_through_mcp(monkeypatch):
    from plaxis3d_mcp import server

    g, make = factory()
    s = PlaxisSession(Settings(password="x"), server_factory=make)
    monkeypatch.setattr(server, "SESSION", s)

    async def run():
        await server.mcp.call_tool("plaxis_connect", {})
        return await server.mcp.call_tool(
            "build_box_culvert", {"params": {"clear_width": 6.0, "clear_height": 4.5, "cover": 2.0}}
        )

    asyncio.run(run())
    assert len(g.Plates) == 10 and len(g.SurfaceLoads) == 6
    assert ("mesh", 0.06, True) in g.log

    async def bad():
        return await server.mcp.call_tool("build_box_culvert", {"params": {"span": 6}})

    with pytest.raises(Exception, match="Unknown parameters"):
        asyncio.run(bad())
