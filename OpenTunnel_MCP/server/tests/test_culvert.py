import math

import pytest

from otd_mcp.culvert import BoxCulvertSection, quantities


def shoelace(points):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def section(**kw):
    base = dict(clear_width_mm=3500, clear_height_mm=3000, top_slab_mm=400, bottom_slab_mm=450,
                wall_mm=400, chamfer_top_mm=200, chamfer_bottom_mm=200)
    base.update(kw)
    s = BoxCulvertSection(**base)
    s.validate()
    return s


def test_single_cell_area_matches_hand_calc():
    s = section()
    # (3500+2*400) x (3000+400+450) - [3500*3000 - 200^2 - 200^2]
    expected_mm2 = 4300 * 3850 - (3500 * 3000 - 2 * 200 ** 2)
    assert s.outer_width_mm == 4300
    assert s.outer_height_mm == 3850
    assert math.isclose(s.concrete_area_m2(), expected_mm2 * 1e-6)


def test_loops_area_equals_formula_area():
    for s in (section(), section(cells=2, mid_wall_mm=350), section(cells=3, mid_wall_mm=300, chamfer_bottom_mm=0)):
        loops = s.loops_m()
        outer = shoelace(loops[0]["points"])
        holes = sum(shoelace(l["points"]) for l in loops[1:])
        assert math.isclose(outer - holes, s.concrete_area_m2(), rel_tol=1e-9)
        assert [l["role"] for l in loops] == ["outer"] + ["hole"] * s.cells


def test_multi_cell_layout_symmetric_and_walls_correct():
    s = section(cells=2, mid_wall_mm=350, chamfer_top_mm=0, chamfer_bottom_mm=0)
    assert s.outer_width_mm == 2 * 3500 + 2 * 400 + 350
    left, right = s.cell_loops_mm()
    assert min(x for x, _ in left) == pytest.approx(-s.outer_width_mm / 2 + 400)
    assert max(x for x, _ in right) == pytest.approx(s.outer_width_mm / 2 - 400)
    assert min(x for x, _ in right) - max(x for x, _ in left) == pytest.approx(350)


def test_zero_chamfer_gives_rectangle_without_duplicate_points():
    s = section(chamfer_top_mm=0, chamfer_bottom_mm=0)
    assert len(s.cell_loops_mm()[0]) == 4


@pytest.mark.parametrize("kw", [
    dict(clear_width_mm=0),
    dict(cells=2),                                   # thieu tuong giua
    dict(chamfer_top_mm=2000),                       # 2c > B
    dict(chamfer_top_mm=1600, chamfer_bottom_mm=1600, clear_width_mm=5000),  # ct+cb > H
])
def test_invalid_sections_rejected(kw):
    base = dict(clear_width_mm=3500, clear_height_mm=3000, top_slab_mm=400, bottom_slab_mm=450, wall_mm=400)
    base.update(kw)
    with pytest.raises(ValueError):
        BoxCulvertSection(**base).validate()


def test_volume_uses_plan_length_for_vertical_section():
    s = section()
    start, end = [0, 0, 10], [30, 40, 11]          # chieu dai bang 50 m, doc 2 %
    q_v = quantities(s, start, end, "vertical")
    q_p = quantities(s, start, end, "perpendicular")
    assert q_v["axis_length_plan_m"] == 50
    assert q_v["longitudinal_slope_pct"] == pytest.approx(2.0)
    assert q_v["concrete_volume_m3"] == pytest.approx(round(s.concrete_area_m2() * 50, 4))
    assert q_p["concrete_volume_m3"] == pytest.approx(round(s.concrete_area_m2() * math.sqrt(2501), 4))


def test_2d_points_accepted():
    q = quantities(section(), [0, 0], [10, 0], "vertical")
    assert q["axis_length_3d_m"] == 10
