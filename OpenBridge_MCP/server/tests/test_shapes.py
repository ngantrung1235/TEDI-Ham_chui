import math

import pytest

from bentley_mcp_core.sections import section_properties
from obd_mcp.shapes import (
    DeckSlab,
    IGirderSection,
    MultiColumnPier,
    axis_info,
    composite_properties,
    lateral_offsets_m,
    offset_axis,
)

# AASHTO Type IV (inch) - so lieu PCI Bridge Design Manual: A = 789 in2, yb = 24.73 in, I = 260,741 in4
TYPE_IV = IGirderSection(height_mm=54, top_flange_width_mm=20, top_flange_thickness_mm=8, top_haunch_height_mm=6,
                         web_thickness_mm=8, bottom_flange_width_mm=26, bottom_flange_thickness_mm=8,
                         bottom_haunch_height_mm=9)


def test_aashto_type_iv_matches_published_properties():
    TYPE_IV.validate()
    p = TYPE_IV.properties_mm()          # "mm" chi la nhan; toa do dang nhap bang inch
    assert p["area_mm2"] == pytest.approx(789, rel=1e-6)
    assert p["yb_mm"] == pytest.approx(24.73, abs=0.01)
    assert p["Ix_mm4"] == pytest.approx(260741, rel=1e-4)


def test_composite_section_matches_parallel_axis_theorem():
    beff, ts, haunch, n = 96.0, 8.0, 2.0, 0.8
    c = composite_properties(TYPE_IV, beff, ts, haunch, n)
    g = TYPE_IV.properties_mm()
    a_s, y_s = beff * n * ts, 54 + haunch + ts / 2
    a = g["area_mm2"] + a_s
    yc = (g["area_mm2"] * g["yb_mm"] + a_s * y_s) / a
    i = g["Ix_mm4"] + g["area_mm2"] * (yc - g["yb_mm"]) ** 2 + beff * n * ts ** 3 / 12 + a_s * (y_s - yc) ** 2
    assert c["area_mm2"] == pytest.approx(a)
    assert c["centroid_mm"][1] == pytest.approx(yc)
    assert c["Ix_mm4"] == pytest.approx(i)
    assert c["St_girder_mm3"] == pytest.approx(i / (54 - yc))


def test_t_girder_without_bottom_flange_is_valid_polygon():
    t = IGirderSection(height_mm=1200, top_flange_width_mm=1800, top_flange_thickness_mm=180, top_haunch_height_mm=0,
                       web_thickness_mm=400, bottom_flange_width_mm=400, bottom_flange_thickness_mm=0,
                       bottom_haunch_height_mm=0)
    t.validate()
    assert len(t.outline_mm()) == 8
    assert t.properties_mm()["area_mm2"] == pytest.approx(1800 * 180 + 400 * 1020)


@pytest.mark.parametrize("kw", [
    dict(web_thickness_mm=30),                      # bung day hon canh
    dict(height_mm=30),                             # canh + vut >= H
    dict(top_flange_width_mm=-1),
])
def test_invalid_girder(kw):
    base = dict(height_mm=54, top_flange_width_mm=20, top_flange_thickness_mm=8, top_haunch_height_mm=6,
                web_thickness_mm=8, bottom_flange_width_mm=26, bottom_flange_thickness_mm=8, bottom_haunch_height_mm=9)
    base.update(kw)
    with pytest.raises(ValueError):
        IGirderSection(**base).validate()


def test_deck_slab_crown_geometry_and_area():
    d = DeckSlab(width_mm=12000, thickness_mm=200, left_slope_pct=2, right_slope_pct=2)
    d.validate()
    pts = d.outline_mm()
    assert (6000, -120) in pts and (-6000, -120) in pts and (0, 0) in pts        # 2% x 6 m = 120 mm
    p = section_properties([{"role": "outer", "points": pts}])
    assert p["area_mm2"] == pytest.approx(12000 * 200)
    assert d.area_m2() == pytest.approx(2.4)


def test_deck_slab_superelevation_one_way():
    d = DeckSlab(width_mm=10000, thickness_mm=250, left_slope_pct=-4, right_slope_pct=4, crown_offset_mm=0)
    pts = d.outline_mm()
    assert (5000, 200) in pts and (-5000, -200) in pts            # trai cao 200, phai thap 200
    assert len(pts) == 4                                          # dinh crown thang hang -> da bo


def test_pier_quantities_and_layout():
    pier = MultiColumnPier(footing_length_mm=9000, footing_width_mm=4000, footing_thickness_mm=2000,
                           column_count=3, column_height_mm=6000, column_spacing_mm=3200,
                           cap_length_mm=10000, cap_width_mm=1800, cap_depth_mm=1500,
                           column_shape="circle", column_diameter_mm=1200)
    pier.validate()
    q = pier.quantities([100, 200, 5])
    assert q["footing_volume_m3"] == pytest.approx(72.0)
    assert q["columns_volume_m3"] == pytest.approx(round(3 * math.pi * 0.36 * 6, 4))
    assert q["cap_volume_m3"] == pytest.approx(27.0)
    assert q["elevation_top_cap_m"] == pytest.approx(5 + 2 + 6 + 1.5)
    assert q["column_offsets_mm"] == [-3200, 0, 3200]

    comps = pier.components([100, 200, 5], orientation_deg=90)
    assert [c["name"] for c in comps] == ["be_tru", "cot_1", "cot_2", "cot_3", "xa_mu"]
    assert comps[1]["origin"][2] == pytest.approx(7) and comps[1]["end"][2] == pytest.approx(13)
    # truc ngang tru quay 90 deg -> cot 1 (offset -3.2 m) nam o Y = -3.2 m so voi diem chen
    xs = [p[0] for p in comps[1]["loops"][0]["points"]]
    ys = [p[1] for p in comps[1]["loops"][0]["points"]]
    assert sum(xs) / len(xs) == pytest.approx(0, abs=1e-6)
    assert sum(ys) / len(ys) == pytest.approx(-3.2, abs=1e-6)
    footing = section_properties(comps[0]["loops"], "m")
    assert footing["area_m2"] == pytest.approx(36.0)
    assert footing["bbox_m"][2] - footing["bbox_m"][0] == pytest.approx(4.0)   # quay 90: dai 9 m nam theo Y


@pytest.mark.parametrize("kw", [
    dict(column_spacing_mm=1000),                      # cot chong nhau
    dict(footing_length_mm=6000),                      # cot vuot ngoai be
    dict(column_diameter_mm=None),                     # thieu D
    dict(column_shape="hexagon"),
])
def test_invalid_pier(kw):
    base = dict(footing_length_mm=9000, footing_width_mm=4000, footing_thickness_mm=2000, column_count=3,
                column_height_mm=6000, column_spacing_mm=3200, cap_length_mm=10000, cap_width_mm=1800,
                cap_depth_mm=1500, column_shape="circle", column_diameter_mm=1200)
    base.update(kw)
    with pytest.raises(ValueError):
        MultiColumnPier(**base).validate()


def test_girder_offsets_left_of_axis():
    axis = axis_info([0, 0, 10], [30, 0, 10.6])
    assert axis["slope_pct"] == pytest.approx(2.0)
    offs = lateral_offsets_m(3, 2400)
    assert offs == pytest.approx([-2.4, 0, 2.4])
    s, e = offset_axis(axis, 2.4)
    assert s == pytest.approx([0, 2.4, 10]) and e == pytest.approx([30, 2.4, 10.6])   # trai cua +X la +Y
    with pytest.raises(ValueError):
        lateral_offsets_m(2, None)
