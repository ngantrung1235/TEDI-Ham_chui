import asyncio
import math

import pytest

from fake_plaxis import FakeOutput, FakeServer, factory
from plaxis3d_mcp.engineering import culvert, design, tunnel
from plaxis3d_mcp.ops import design_check, export, importers, water
from plaxis3d_mcp.session import PlaxisSession, Settings


@pytest.fixture
def sess():
    g, make = factory()
    s = PlaxisSession(Settings(password="x"), server_factory=make)
    s.connect_input()
    s.fake = g
    return s


@pytest.fixture
def out_sess(sess):
    sess.g_o = FakeOutput()
    sess.s_o = FakeServer(sess.fake)
    return sess


# -- tunnel ---------------------------------------------------------------------------------
def test_tunnel_build_and_sequence(sess):
    p = tunnel.TunnelParams(rounds=4, n_facets=8, face_pressure=100.0, unsupported_rounds=1, core_material=None)
    out = tunnel.build_tunnel(sess, p)
    g = sess.fake
    assert len(out["cores"]) == 4 and all(len(r) == 8 for r in out["lining_rounds"])
    assert len(out["face_loads"]) == 4
    # 1 initial + 4 rounds + closure
    assert len(out["phases"]) == 6
    # lining of round 1 is installed in round 2 (one unsupported round)
    first_ring = out["lining_rounds"][0][0]
    assert g.registry[first_ring].calls == [("activate", out["phases"][2]["name"])]
    # last ring only at closure
    last_ring = out["lining_rounds"][-1][0]
    assert g.registry[last_ring].calls == [("activate", out["phases"][-1]["name"])]
    # excavated cores are dry in their phase
    core = g.registry[out["cores"][0]]
    assert core.calls == [("deactivate", out["phases"][1]["name"])]
    assert core._props["WaterConditions"].Conditions[out["phases"][1]["name"]] == "Dry"
    # face pressure moves with the face
    f1 = g.registry[out["face_loads"][0]]
    assert f1.calls == [("activate", out["phases"][1]["name"]), ("deactivate", out["phases"][2]["name"])]
    assert f1._props["sigy"] == 100.0
    assert any("core_material" in w for w in out["warnings"])


def test_tunnel_lining_normals_point_outward(sess):
    out = tunnel.build_tunnel(sess, tunnel.TunnelParams(rounds=1, n_facets=12, auto_stage=False))
    p = tunnel.TunnelParams()
    for name in out["lining_rounds"][0]:
        pts = list(sess.fake.registry[name]._props["surface"]._props["points"])
        n = culvert._normal(pts)
        mid = [sum(c) / len(pts) for c in zip(*pts)]
        radial = (mid[0] - p.center_x, 0.0, mid[2] - p.center_z)
        assert sum(a * b for a, b in zip(n, radial)) > 0


# -- imports --------------------------------------------------------------------------------
def test_import_boreholes_csv(sess, tmp_path):
    from plaxis3d_mcp.ops import materials

    materials.create_material(sess, "soil", {"name": "Clay"})
    materials.create_material(sess, "soil", {"name": "Sand"})
    f = tmp_path / "bh.csv"
    f.write_text(
        "borehole;x;y;top;bottom;material;head\n"
        "BH1;0;0;0;-3;Clay;-1.5\nBH1;0;0;-3;-20;Sand;\n"
        "BH2;50;0;0;0;Clay;\nBH2;50;0;0;-20;Sand;\n",
        encoding="utf-8",
    )
    r = importers.import_boreholes(sess, str(f))
    assert [b["id"] for b in r["boreholes"]] == ["BH1", "BH2"]
    assert len(sess.fake.Soillayers) == 2
    assert sess.fake.Soillayers[0]._props["Soil"]._props["Material"] is sess.fake.registry["SoilMat_1"]


def test_import_boreholes_rejects_bad_sequence():
    rows = [
        {"borehole": "A", "x": 0, "y": 0, "top": 0, "bottom": -2, "material": "Clay"},
        {"borehole": "B", "x": 9, "y": 0, "top": 0, "bottom": -2, "material": "Sand"},
    ]
    with pytest.raises(RuntimeError, match="zero thickness"):
        importers.parse_boreholes(rows)
    gap = [
        {"borehole": "A", "x": 0, "y": 0, "top": 0, "bottom": -2, "material": "Clay"},
        {"borehole": "A", "x": 0, "y": 0, "top": -3, "bottom": -9, "material": "Sand"},
    ]
    with pytest.raises(RuntimeError, match="does not match"):
        importers.parse_boreholes(gap)


def test_import_dxf(sess, tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_3dface([(1000, 2000, 0), (1004, 2000, 0), (1004, 2000, 3), (1000, 2000, 3)], dxfattribs={"layer": "WALL"})
    msp.add_lwpolyline([(1000, 2000), (1010, 2000), (1010, 2010)], close=True, dxfattribs={"layer": "SLAB", "elevation": 5})
    msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "WALL"})
    path = tmp_path / "c3d.dxf"
    doc.saveas(path)
    faces = importers.read_dxf_faces(str(path), offset=(1000, 2000, 0))
    assert {f["layer"] for f in faces} == {"WALL", "SLAB"}
    assert faces[0]["points"][1] == [4.0, 0.0, 0.0]
    r = importers.import_dxf(sess, str(path), create="plate", layers=["wall"], offset=[1000, 2000, 0])
    assert r["faces"] == 1 and r["created"] == ["Plate_1"]


# -- water -----------------------------------------------------------------------------------
def test_water_tools(sess):
    wl = water.create_water_level(sess, [(0, 0, -2), (1, 0, -2), (0, 1, -2)])
    assert wl["water_level"] == "UserWaterLevel_1"
    r = water.set_phase_water(sess, "InitialPhase", "phreatic", "UserWaterLevel_1")
    assert sess.fake.registry["InitialPhase"]._props["PorePresCalcType"] == "Phreatic"
    # the fake has no setglobalwaterlevel command, so the property fallback is used
    assert not r["warnings"]
    assert sess.fake.registry["InitialPhase"]._props["GlobalWaterLevel"] is sess.fake.registry["UserWaterLevel_1"]
    sess.fake.rejected.add("GlobalWaterLevel")
    r = water.set_phase_water(sess, "InitialPhase", global_water_level="UserWaterLevel_1")
    assert "Could not set global water level" in r["warnings"][0]


# -- exports ----------------------------------------------------------------------------------
def test_exports(out_sess, tmp_path):
    r = export.export_results(out_sess, ["Plate.M11", "Plate.N1"], str(tmp_path / "m.csv"), "Phase_1", "Plate_1_1")
    assert r["rows"] == 9
    text = (tmp_path / "m.csv").read_text(encoding="utf-8-sig").splitlines()
    assert text[0] == "X,Y,Z,Plate.M11,Plate.N1"
    line = export.results_along_line(out_sess, [0, 0, 0], [20, 0, 0], ["Soil.Uz"], 3, "Phase_1")
    assert line["rows"][0][-1] == pytest.approx(-0.02) and line["rows"][-1][-1] is None
    hist = export.results_history(out_sess, [1, 0, 0], ["Soil.Uz"])
    assert [r[1] for r in hist["rows"]] == pytest.approx([-0.02, -0.04, -0.06])
    assert hist["rows"][1][0] == "Phase_1 (stage 1)"


def test_plot_image(out_sess, tmp_path):
    png = b"\x89PNG\r\n\x1a\nfake"
    plot = out_sess.g_o.Plots[0]
    plot.__dict__["export"] = lambda path, w, h: open(path, "wb").write(png)
    info, data = export.export_plot_image(out_sess, str(tmp_path / "p.png"), "Soil.Utot", "Phase_2")
    assert data == png and info["has_image"]
    assert plot._props["Phase"] is out_sess.g_o.Phases[2]


# -- design (TCVN 11823-5) -------------------------------------------------------------------
def test_flexure_hand_calc():
    # h 500, d = 440, As = 1340 mm2/m, f'c 30, fy 400, no compression steel, P = 0
    sec = design.Section(h=500, as_pos=1340, as_neg=0, cover=60, fc=30, fy=400)
    r = design.flexure_capacity(sec, 0.0, True)
    a = 1340 * 400 / (0.85 * 30 * 1000)
    mn = 1340 * 400 * (440 - a / 2) / 1e6
    assert r["Mn"] == pytest.approx(mn, rel=2e-3)
    assert r["phi"] == pytest.approx(0.9)
    assert design.beta1(30) == pytest.approx(0.85 - 0.05 * 2 / 7)


def test_flexure_axial_effects():
    sec = design.Section(h=400, as_pos=1000, as_neg=1000, cover=50)
    base = design.flexure_capacity(sec, 0.0, True)["phiMn"]
    assert design.flexure_capacity(sec, 500.0, True)["phiMn"] > base  # moderate compression helps
    assert design.flexure_capacity(sec, -200.0, True)["phiMn"] < base  # tension reduces
    assert not design.flexure_capacity(sec, -900.0, True)["ok_axial"]  # > (As+As') fy = 800 kN


def test_shear_and_crack():
    sec = design.Section(h=500, as_pos=1340, as_neg=1340, cover=60, fc=30)
    de = 440
    slab = design.shear_capacity(sec, 200, 100, "top_slab", 1.5)
    lo, hi = 0.25 * math.sqrt(30) * 1000 * de, 0.332 * math.sqrt(30) * 1000 * de
    assert 0.9 * lo / 1e3 <= slab["phiVc"] <= 0.9 * hi / 1e3 + 1e-6
    wall = design.shear_capacity(sec, 200, 100, "wall", 1.5)
    assert wall["phiVc"] == pytest.approx(0.9 * 0.166 * math.sqrt(30) * 1000 * max(0.9 * de, 360) / 1e3)
    cr = design.crack_control(sec, 150)
    assert 0 < cr["fss"] <= 240 and cr["s_max"] > 0


def test_combine():
    assert design.combine(100, 130, 1.35, 1.75) == pytest.approx(1.35 * 100 + 1.75 * 30)


def test_design_check_plates(out_sess, tmp_path):
    sections = {"Plate_1_1": {"h": 500, "as_pos": 1340, "as_neg": 1340, "cover": 60, "member": "top_slab",
                              "dir2": {"as_pos": 800, "as_neg": 800}}}
    r = design_check.design_check_plates(out_sess, "Phase_1", sections, "Phase_2", fill_depth=1.5,
                                         path=str(tmp_path / "chk.csv"))
    res = r["plates"]["Plate_1_1"]
    # max node: x = 2 -> M11 perm = 10*3 + 5 = 35, total = 40
    gov = res["dir1"]["governing"]["flexure"]
    assert gov["Mu"] == pytest.approx(1.35 * 35 + 1.75 * 5, abs=0.1)
    assert gov["Pu"] > 0  # PLAXIS tension-positive N converted to compression-positive
    assert r["all_ok"] is True
    assert (tmp_path / "chk.csv").exists()


def test_new_tools_registered():
    from plaxis3d_mcp import server

    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    for t in ("build_tunnel", "import_dxf", "import_boreholes", "water_soil_condition", "results_export",
              "results_along_line", "plot_image", "design_check_plates", "rc_section_check", "load_factors"):
        assert t in names
