import math

import pytest

from bentley_mcp_core.sections import section_properties


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_rectangle_matches_closed_form():
    b, h = 300.0, 600.0
    p = section_properties([{"role": "outer", "points": rect(-b / 2, 0, b / 2, h)}])
    assert p["area_mm2"] == pytest.approx(b * h)
    assert p["yb_mm"] == pytest.approx(h / 2)
    assert p["Ix_mm4"] == pytest.approx(b * h ** 3 / 12)
    assert p["Iy_mm4"] == pytest.approx(h * b ** 3 / 12)
    assert p["Sb_mm3"] == pytest.approx(b * h ** 2 / 6)
    assert p["Ixy_mm4"] == pytest.approx(0, abs=1e-6)


def test_orientation_and_closing_point_do_not_matter():
    pts = rect(0, 0, 2, 1)
    cw_closed = list(reversed(pts)) + [list(reversed(pts))[0]]
    a = section_properties([{"role": "outer", "points": pts}])
    b = section_properties([{"role": "outer", "points": cw_closed}])
    assert a["Ix_mm4"] == pytest.approx(b["Ix_mm4"]) and a["area_mm2"] == pytest.approx(b["area_mm2"])


def test_hollow_box_subtracts_hole():
    # Hop rong 1000x800, thanh 100 -> I = (B H^3 - b h^3)/12
    p = section_properties([
        {"role": "outer", "points": rect(-500, 0, 500, 800)},
        {"role": "hole", "points": list(reversed(rect(-400, 100, 400, 700)))},
    ])
    assert p["area_mm2"] == pytest.approx(1000 * 800 - 800 * 600)
    assert p["Ix_mm4"] == pytest.approx((1000 * 800 ** 3 - 800 * 600 ** 3) / 12)


def test_l_section_product_of_inertia_and_principal_axes():
    # Thep goc L 100x100x10 (mm): Ixy khac 0, I1 + I2 = Ix + Iy
    pts = [[0, 0], [100, 0], [100, 10], [10, 10], [10, 100], [0, 100]]
    p = section_properties([{"role": "outer", "points": pts}])
    assert p["area_mm2"] == pytest.approx(1900)
    assert p["centroid_mm"][0] == pytest.approx(p["centroid_mm"][1])     # doi xung qua duong cheo
    assert p["Ixy_mm4"] < 0
    assert p["I1_mm4"] + p["I2_mm4"] == pytest.approx(p["Ix_mm4"] + p["Iy_mm4"])
    assert p["I1_mm4"] == pytest.approx(p["Ix_mm4"] - p["Ixy_mm4"])      # Ix = Iy -> I1,2 = Ix -/+ Ixy


def test_invalid_input():
    with pytest.raises(ValueError):
        section_properties([{"role": "hole", "points": rect(0, 0, 1, 1)}])
    with pytest.raises(ValueError):
        section_properties([{"role": "outer", "points": [[0, 0], [1, 1]]}])
