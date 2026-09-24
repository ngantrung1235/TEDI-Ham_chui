"""Soil stratigraphy, structural elements and loads (PLAXIS 3D Input)."""

from __future__ import annotations

from typing import Any, Sequence

from ..plx import flatten, get_by_name, name_of, pick, plx_type, set_properties

Point = Sequence[float]


def _pts(points: Sequence[Point], n_min: int) -> list[tuple[float, float, float]]:
    pts = [tuple(float(c) for c in p) for p in points]
    if len(pts) < n_min or any(len(p) != 3 for p in pts):
        raise RuntimeError(f"Need at least {n_min} points given as [x, y, z].")
    return pts  # type: ignore[return-value]


def _created(result: Any) -> list[dict]:
    return [{"name": name_of(o), "type": plx_type(o)} for o in flatten(result)]


def _assign_material(g_i: Any, obj: Any, material: str | None) -> list[str]:
    if not material:
        return []
    try:
        obj.Material = get_by_name(g_i, material)
        return []
    except Exception as exc:
        return [f"Could not assign material '{material}' to {name_of(obj)}: {exc}"]


# -- Soil mode -------------------------------------------------------------------
def set_soil_contour(sess, xmin: float, ymin: float, xmax: float, ymax: float) -> dict:
    _, g_i = sess.input()
    g_i.gotosoil()
    g_i.SoilContour.initializerectangular(xmin, ymin, xmax, ymax)
    return {"ok": True, "contour": [xmin, ymin, xmax, ymax]}


def create_borehole(
    sess,
    x: float,
    y: float,
    layer_levels: list[float],
    head: float | None = None,
    materials: list[str] | None = None,
) -> dict:
    """Create a borehole and its soil layers.

    ``layer_levels`` are the layer boundary elevations from top to bottom,
    e.g. [0, -3, -12, -30] gives three layers. Layers are shared by all
    boreholes; for extra boreholes pass the same number of levels.
    """
    _, g_i = sess.input()
    levels = [float(z) for z in layer_levels]
    if len(levels) < 2 or any(a <= b for a, b in zip(levels, levels[1:])):
        raise RuntimeError("layer_levels must be >= 2 strictly decreasing elevations (top to bottom).")
    g_i.gotosoil()
    borehole = g_i.borehole(x, y)
    warnings: list[str] = []
    if head is not None:
        warnings += set_properties(borehole, {"Head": head})
    n_layers = len(levels) - 1
    existing = len(list(g_i.Soillayers))
    for _ in range(max(0, n_layers - existing)):
        g_i.soillayer(0)
    for i, z in enumerate(levels):
        g_i.setsoillayerlevel(borehole, i, z)
    if materials:
        for i, mat in enumerate(materials[:n_layers]):
            warnings += assign_layer_material(sess, i, mat)["warnings"]
    return {"ok": True, "borehole": name_of(borehole), "layers": n_layers, "warnings": warnings}


def assign_layer_material(sess, layer_index: int, material: str) -> dict:
    _, g_i = sess.input()
    layer = list(g_i.Soillayers)[layer_index]
    mat = get_by_name(g_i, material)
    try:
        layer.Soil.Material = mat
    except Exception:
        g_i.setmaterial(layer, mat)
    return {"ok": True, "layer": name_of(layer), "material": material, "warnings": []}


# -- Structures mode ---------------------------------------------------------------
def create_surface(sess, points: list[Point]) -> dict:
    _, g_i = sess.input()
    g_i.gotostructures()
    res = g_i.surface(*_pts(points, 3))
    return {"surface": name_of(pick(res, "Surface")), "created": _created(res)}


def create_soil_volume(sess, points: list[Point], extrusion: Point, material: str | None = None) -> dict:
    """Extrude a planar polygon into a soil volume (e.g. embankment, backfill block)."""
    _, g_i = sess.input()
    g_i.gotostructures()
    srf = pick(g_i.surface(*_pts(points, 3)), "Surface")
    res = g_i.extrude(srf, tuple(float(c) for c in extrusion))
    soil = pick(res, "Soil", required=False)
    warnings = _assign_material(g_i, soil, material) if soil is not None else ["No Soil object returned by extrude."]
    try:
        g_i.delete(srf)  # keep only the volume, not the generating surface
    except Exception as exc:
        warnings.append(f"Generating surface {name_of(srf)} not deleted: {exc}")
    return {
        "volume": name_of(pick(res, "Volume", required=False)),
        "soil": name_of(soil),
        "created": _created(res),
        "warnings": warnings,
    }


def create_plate(
    sess,
    points: list[Point],
    material: str | None = None,
    interfaces: str = "none",
) -> dict:
    """Plate on a planar polygon. ``interfaces``: none | positive | negative | both.

    The positive side follows the right-hand rule of the point order.
    """
    _, g_i = sess.input()
    g_i.gotostructures()
    srf = pick(g_i.surface(*_pts(points, 3)), "Surface")
    plate = pick(g_i.plate(srf), "Plate")
    warnings = _assign_material(g_i, plate, material)
    created_if = []
    if interfaces in ("positive", "both"):
        created_if.append(name_of(pick(g_i.posinterface(srf), "PositiveInterface", required=False)))
    if interfaces in ("negative", "both"):
        created_if.append(name_of(pick(g_i.neginterface(srf), "NegativeInterface", required=False)))
    return {"surface": name_of(srf), "plate": name_of(plate), "interfaces": created_if, "warnings": warnings}


def _line_element(sess, command: str, type_name: str, p1: Point, p2: Point, material: str | None) -> dict:
    _, g_i = sess.input()
    g_i.gotostructures()
    res = getattr(g_i, command)(*_pts([p1, p2], 2))
    el = pick(res, type_name)
    return {type_name.lower(): name_of(el), "created": _created(res), "warnings": _assign_material(g_i, el, material)}


def create_beam(sess, p1: Point, p2: Point, material: str | None = None) -> dict:
    return _line_element(sess, "beam", "Beam", p1, p2, material)


def create_embedded_beam(sess, p1: Point, p2: Point, material: str | None = None) -> dict:
    """Embedded beam (pile). p1 is the pile head, p2 the pile toe."""
    return _line_element(sess, "embeddedbeam", "EmbeddedBeam", p1, p2, material)


def create_node_to_node_anchor(sess, p1: Point, p2: Point, material: str | None = None) -> dict:
    return _line_element(sess, "n2nanchor", "NodeToNodeAnchor", p1, p2, material)


# -- Loads ---------------------------------------------------------------------------
def create_surface_load(sess, points: list[Point], sigx: float = 0.0, sigy: float = 0.0, sigz: float = 0.0) -> dict:
    """Uniform surface load [kN/m2]; sigz < 0 acts downward."""
    _, g_i = sess.input()
    g_i.gotostructures()
    res = g_i.surfload(*_pts(points, 3))
    load = pick(res, "SurfaceLoad")
    warnings = set_properties(load, {"sigx": sigx, "sigy": sigy, "sigz": sigz})
    return {"load": name_of(load), "created": _created(res), "warnings": warnings}


def create_line_load(sess, p1: Point, p2: Point, qx: float = 0.0, qy: float = 0.0, qz: float = 0.0) -> dict:
    """Uniform line load [kN/m]; qz < 0 acts downward."""
    _, g_i = sess.input()
    g_i.gotostructures()
    res = g_i.lineload(*_pts([p1, p2], 2))
    load = pick(res, "LineLoad")
    return {"load": name_of(load), "warnings": set_properties(load, {"qx": qx, "qy": qy, "qz": qz})}


def create_point_load(sess, point: Point, Fx: float = 0.0, Fy: float = 0.0, Fz: float = 0.0) -> dict:
    """Point load [kN]; Fz < 0 acts downward."""
    _, g_i = sess.input()
    g_i.gotostructures()
    res = g_i.pointload(*_pts([point], 1))
    load = pick(res, "PointLoad")
    return {"load": name_of(load), "warnings": set_properties(load, {"Fx": Fx, "Fy": Fy, "Fz": Fz})}


def delete_objects(sess, names: list[str]) -> dict:
    _, g_i = sess.input()
    errors = []
    for n in names:
        try:
            g_i.delete(get_by_name(g_i, n))
        except Exception as exc:
            errors.append(f"{n}: {exc}")
    return {"ok": not errors, "errors": errors}
