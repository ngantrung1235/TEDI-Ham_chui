"""Parametric PLAXIS 3D model of a box culvert / underpass (hầm chui) under a road embankment.

Coordinate system
-----------------
* X - road axis (traffic direction). The culvert centre line is at x = 0.
* Y - culvert axis. The road centre line is at y = 0.
* Z - up. Natural ground surface at z = 0 (top of the boreholes).

Modelling assumptions (see README for the discussion)
-----------------------------------------------------
* Walls and slabs are plates on their mid-surfaces. The bottom-slab mid-plane
  is at ground level (z = 0), so the culvert opening lies entirely above the
  natural ground and no soil has to be excavated inside the box. This avoids
  overlapping soil volumes and keeps staged construction unambiguous.
* The embankment (crest width Bc, side slope 1:m) is built from three
  non-overlapping soil volumes: two blocks beside the culvert (|x| >= xw) and
  one block above the top slab (|x| <= xw), clipped at the culvert ends.
* Optional wing walls (plane x = +-xw, beyond the culvert ends) and headwalls
  (plane y = +-L/2, above the top slab) retain the embankment slopes.
* Traffic: HL-93 wheel loads on the tire contact areas at the pavement
  (TCVN 11823-3:2017), including m and IM; the soil spreads the load.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..ops import geometry, materials, staging
from . import traffic

Vec = tuple[float, float, float]


@dataclass
class BoxCulvertParams:
    # Culvert section (m)
    clear_width: float = 4.0
    clear_height: float = 3.2
    t_top: float = 0.45
    t_bottom: float = 0.50
    t_wall: float = 0.40
    concrete_grade: str = "B30"
    # Embankment (m)
    cover: float = 1.5  # fill above the top slab
    crest_width: float = 12.0
    side_slope: float = 1.5  # 1 : m
    culvert_length: float | None = None  # default: embankment width at the top-slab level
    wing_walls: bool = True
    # Ground
    layer_levels: list[float] = field(default_factory=lambda: [0.0, -20.0])
    layer_presets: list[str] = field(default_factory=lambda: ["stiff_clay"])
    layer_materials: list[str] | None = None  # existing SoilMat names; overrides presets
    water_head: float | None = None
    embankment_preset: str = "embankment_K95"
    # Model extent (m)
    margin_x: float | None = None
    margin_y: float = 10.0
    # Traffic
    traffic: str = "wheel_patches"  # wheel_patches | none
    vehicle: str = "truck"  # truck | tandem
    lanes: int = 1
    truck_x: float = 0.0  # position of the heaviest (2nd) axle along the road
    granular_fill: bool = True
    # Workflow
    generate_mesh: bool = True
    mesh_coarseness: float = 0.06
    auto_stage: bool = True


# -- small geometry helpers ------------------------------------------------------
def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _normal(pts: list[Vec]) -> Vec:
    """Newell normal of a planar polygon (right-hand rule of the point order)."""
    nx = ny = nz = 0.0
    for i, (x1, y1, z1) in enumerate(pts):
        x2, y2, z2 = pts[(i + 1) % len(pts)]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return (nx, ny, nz)


def oriented(pts: list[Vec], outward: Vec) -> list[Vec]:
    """Order points so that the positive side (interface side) faces ``outward``."""
    n = _normal(pts)
    return pts if sum(a * b for a, b in zip(n, outward)) >= 0 else list(reversed(pts))


def clip(poly: list[tuple[float, float]], axis: int, value: float, keep_above: bool) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a 2D polygon by the line coord[axis] = value."""

    def inside(p):
        return p[axis] >= value - 1e-9 if keep_above else p[axis] <= value + 1e-9

    out: list[tuple[float, float]] = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(_intersect(prev, cur, axis, value))
            out.append(cur)
        elif inside(prev):
            out.append(_intersect(prev, cur, axis, value))
    # drop consecutive duplicates
    dedup = [p for i, p in enumerate(out) if abs(p[0] - out[i - 1][0]) > 1e-9 or abs(p[1] - out[i - 1][1]) > 1e-9]
    return dedup if len(dedup) >= 3 else []


def _intersect(a, b, axis, value):
    t = (value - a[axis]) / (b[axis] - a[axis])
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _area2d(poly):
    return abs(sum(poly[i - 1][0] * p[1] - p[0] * poly[i - 1][1] for i, p in enumerate(poly))) / 2.0


# -- derived layout ------------------------------------------------------------------
def layout(p: BoxCulvertParams) -> dict[str, Any]:
    if min(p.clear_width, p.clear_height, p.t_top, p.t_bottom, p.t_wall, p.crest_width, p.side_slope) <= 0:
        raise RuntimeError("Dimensions, crest width and side slope must be positive.")
    if p.cover < 0:
        raise RuntimeError("cover must be >= 0.")
    xw = p.clear_width / 2 + p.t_wall / 2
    z_ts = p.t_bottom / 2 + p.clear_height + p.t_top / 2  # top slab mid-plane
    z_top_outer = z_ts + p.t_top / 2
    He = z_top_outer + p.cover

    def half_width(z):
        return p.crest_width / 2 + p.side_slope * (He - z)

    L = p.culvert_length or 2 * half_width(z_top_outer)
    toe = half_width(0.0)
    mx = p.margin_x or max(20.0, 3 * (2 * xw), 3 * He)
    extent = (-(xw + mx), -(max(toe, L / 2) + p.margin_y), xw + mx, max(toe, L / 2) + p.margin_y)

    trapezoid = [(-toe, 0.0), (toe, 0.0), (p.crest_width / 2, He), (-p.crest_width / 2, He)]  # (y, z)
    top_block = clip(trapezoid, 1, z_ts, keep_above=True)
    top_block = clip(top_block, 0, -L / 2, keep_above=True)
    top_block = clip(top_block, 0, L / 2, keep_above=False)
    wing = clip(trapezoid, 0, L / 2, keep_above=True)  # exposed face beyond +L/2 (mirror for -L/2)
    head_top = max((z for y, z in top_block if abs(abs(y) - L / 2) < 1e-6), default=z_ts)
    return {
        "xw": xw, "z_bottom_slab": 0.0, "z_top_slab": z_ts, "embankment_height": He,
        "culvert_length": L, "toe_half_width": toe, "extent": extent,
        "trapezoid": trapezoid, "top_block": top_block, "wing": wing, "headwall_top": head_top,
    }


def _yz(poly, x) -> list[Vec]:
    return [(x, y, z) for y, z in poly]


# -- builder ---------------------------------------------------------------------------
def build_box_culvert(sess, p: BoxCulvertParams) -> dict[str, Any]:
    lay = layout(p)
    n_given = len(p.layer_materials or p.layer_presets)
    if n_given != len(p.layer_levels) - 1:  # check before anything is created in PLAXIS
        raise RuntimeError(
            f"layer_levels defines {len(p.layer_levels) - 1} soil layers but {n_given} layer materials/presets were given."
        )
    xw, zb, zt, He, L = lay["xw"], lay["z_bottom_slab"], lay["z_top_slab"], lay["embankment_height"], lay["culvert_length"]
    warnings: list[str] = []
    out: dict[str, Any] = {"params": asdict(p), "layout": {k: v for k, v in lay.items() if not isinstance(v, list)}}
    if L < 2 * lay["toe_half_width"] - 1e-6 and not p.wing_walls:
        warnings.append("Culvert shorter than the embankment base and wing_walls=False: slope soil at the openings is unsupported.")

    # 1. Materials --------------------------------------------------------------------
    mats: dict[str, str] = {}
    for key, t in (("top", p.t_top), ("bottom", p.t_bottom), ("wall", p.t_wall)):
        r = materials.create_concrete_plate_material(sess, p.concrete_grade, t, f"Culvert_{key}_{p.concrete_grade}")
        mats[key] = r["material"]
        warnings += r["warnings"]
    r = materials.create_soil_material_from_preset(sess, p.embankment_preset, "Embankment")
    mats["embankment"] = r["material"]
    warnings += r["warnings"]
    layer_mats = list(p.layer_materials or [])
    if not layer_mats:
        for i, preset in enumerate(p.layer_presets):
            r = materials.create_soil_material_from_preset(sess, preset, f"Layer{i + 1}_{preset}")
            layer_mats.append(r["material"])
            warnings += r["warnings"]
        warnings.append("Ground layers use indicative presets - replace with the geotechnical report values.")
    out["materials"] = mats | {"layers": layer_mats}

    # 2. Soil ------------------------------------------------------------------------
    xmin, ymin, xmax, ymax = lay["extent"]
    geometry.set_soil_contour(sess, xmin, ymin, xmax, ymax)
    r = geometry.create_borehole(sess, 0.0, 0.0, p.layer_levels, p.water_head, layer_mats)
    warnings += r["warnings"]

    # 3. Culvert plates (positive side = soil side -> positive interfaces) -----------------
    y1, y2 = -L / 2, L / 2
    plates: dict[str, str] = {}
    interfaces: list[str] = []

    def plate(key, pts, outward, mat):
        res = geometry.create_plate(sess, oriented(pts, outward), mat, interfaces="positive")
        plates[key] = res["plate"]
        interfaces.extend(i for i in res["interfaces"] if i)
        warnings.extend(res["warnings"])

    plate("bottom_slab", [(-xw, y1, zb), (xw, y1, zb), (xw, y2, zb), (-xw, y2, zb)], (0, 0, -1), mats["bottom"])
    plate("top_slab", [(-xw, y1, zt), (xw, y1, zt), (xw, y2, zt), (-xw, y2, zt)], (0, 0, 1), mats["top"])
    plate("wall_left", [(-xw, y1, zb), (-xw, y2, zb), (-xw, y2, zt), (-xw, y1, zt)], (-1, 0, 0), mats["wall"])
    plate("wall_right", [(xw, y1, zb), (xw, y2, zb), (xw, y2, zt), (xw, y1, zt)], (1, 0, 0), mats["wall"])
    if p.wing_walls and lay["wing"] and _area2d(lay["wing"]) > 1e-6:
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts = [(sx * xw, sy * y, z) for y, z in lay["wing"]]
                plate(f"wing_{'LR'[sx > 0]}{'-+'[sy > 0]}", pts, (sx, 0, 0), mats["wall"])
    if p.wing_walls and lay["headwall_top"] > zt + 1e-6:
        for sy in (-1, 1):
            h = lay["headwall_top"]
            pts = [(-xw, sy * L / 2, zt), (xw, sy * L / 2, zt), (xw, sy * L / 2, h), (-xw, sy * L / 2, h)]
            plate(f"headwall_{'-+'[sy > 0]}", pts, (0, -sy, 0), mats["wall"])
    out["plates"] = plates
    out["interfaces"] = interfaces

    # 4. Embankment volumes --------------------------------------------------------------
    soils: dict[str, str] = {}
    for key, poly, x0, dx in (
        ("embankment_left", lay["trapezoid"], xmin, -xw - xmin),
        ("embankment_right", lay["trapezoid"], xw, xmax - xw),
        ("embankment_top", lay["top_block"], -xw, 2 * xw),
    ):
        if not poly:
            continue
        res = geometry.create_soil_volume(sess, _yz(poly, x0), (dx, 0.0, 0.0), mats["embankment"])
        soils[key] = res["soil"]
        warnings += res["warnings"]
    out["embankment_soils"] = soils

    # 5. Traffic: HL-93 wheel patches at the pavement ------------------------------------------
    loads: list[str] = []
    ll = traffic.hl93_through_fill(p.cover, p.granular_fill, max(1, p.lanes), p.clear_width)
    out["live_load"] = {k: ll[k] for k in ("IM_percent", "governing", "surface_patches", "warnings")}
    if p.traffic == "wheel_patches":
        factor = traffic.multiple_presence(p.lanes) * (1 + traffic.dynamic_allowance_buried(p.cover) / 100.0)
        axles = traffic.VEHICLES[p.vehicle]
        x_ref = max(axles, key=lambda a: a[1])[0]  # heaviest axle
        ex, ey = traffic.TIRE_LONGITUDINAL / 2, traffic.TIRE_TRANSVERSE / 2
        for w in traffic.wheels(p.vehicle, p.lanes):
            x = p.truck_x + w.x - x_ref
            if abs(w.y) + ey > p.crest_width / 2 or not (xmin < x - ex and x + ex < xmax):
                warnings.append(f"Wheel at x={x:.2f}, y={w.y:.2f} lies outside the crest/model and was skipped.")
                continue
            q = -w.load / (4 * ex * ey) * factor
            pts = [(x - ex, w.y - ey, He), (x + ex, w.y - ey, He), (x + ex, w.y + ey, He), (x - ex, w.y + ey, He)]
            res = geometry.create_surface_load(sess, pts, sigz=q)
            loads.append(res["load"])
            warnings += res["warnings"]
    out["traffic_loads"] = loads

    # 6. Mesh and staged construction ---------------------------------------------------------
    if p.generate_mesh:
        staging.generate_mesh(sess, p.mesh_coarseness)
        if p.auto_stage:
            out["phases"] = _stage(sess, list(plates.values()), interfaces, list(soils.values()), loads, warnings)
    out["warnings"] = warnings
    out["next_steps"] = [
        "Check plate/interface orientation and the phase activation in the PLAXIS GUI (Staged construction).",
        "Replace indicative soil parameters with the geotechnical report values; consider consolidation "
        "phases for soft ground.",
        "Run calculate, then plate_force_envelope for the culvert plates and compare the top-slab pressure "
        "with live_load.governing (hand check, TCVN 11823-3 §3.6.1.2.6).",
    ]
    return out


def _stage(sess, plates, interfaces, soils, loads, warnings) -> list[dict]:
    phases = []
    r = staging.configure_phase(sess, "InitialPhase", calc_type="k0", deactivate=soils)
    warnings += r["warnings"]
    phases.append({"name": r["phase"], "identification": "Initial (K0, natural ground)"})
    steps = [
        ("01 Culvert construction", plates + interfaces, False),
        ("02 Embankment fill", soils, False),
    ]
    if loads:
        steps.append(("03 HL-93 traffic", loads, True))
    previous = "InitialPhase"
    for ident, objs, reset in steps:
        r = staging.create_phase(sess, ident, previous, "plastic", activate=objs, reset_displacements=reset)
        warnings += r["warnings"]
        phases.append({"name": r["phase"], "identification": ident})
        previous = r["phase"]
    return phases
