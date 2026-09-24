"""Geometry and borehole import (Civil 3D / Revit / Excel workflows).

* ``import_geometry_native`` - PLAXIS' own importer (DXF, DWG, IFC, STEP, 3DS...
  depending on the PLAXIS version) via the ``importgeometry`` command.
* ``import_dxf`` - reads 3DFACE, closed (LW)POLYLINE, POLYFACE/MESH entities with
  ezdxf and recreates them as surfaces, plates or soil volumes. Use it when the
  native importer brings in unwanted objects or you need layer filtering,
  unit scaling and a coordinate shift (e.g. VN-2000 -> local model origin).
* ``import_boreholes`` - borehole logs from CSV/XLSX.
"""

from __future__ import annotations

import csv
import os
from collections import OrderedDict
from typing import Any

from ..plx import flatten, name_of, plx_type
from . import geometry, materials


def import_geometry_native(sess, path: str) -> dict:
    _, g_i = sess.input()
    g_i.gotostructures()
    res = g_i.importgeometry(path)
    created = [{"name": name_of(o), "type": plx_type(o)} for o in flatten(res)]
    return {"path": path, "created": created, "count": len(created)}


# -- DXF ---------------------------------------------------------------------------------
def read_dxf_faces(
    path: str,
    layers: list[str] | None = None,
    scale: float = 1.0,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[dict[str, Any]]:
    """Planar faces from a DXF: [{'layer': ..., 'points': [[x, y, z], ...]}]."""
    try:
        import ezdxf
    except ImportError as exc:  # optional dependency
        raise RuntimeError("DXF import needs ezdxf: pip install ezdxf") from exc
    doc = ezdxf.readfile(path)
    wanted = {name.upper() for name in layers} if layers else None
    ox, oy, oz = offset

    def tr(p):
        return [round((p[0] - ox) * scale, 6), round((p[1] - oy) * scale, 6), round((p[2] - oz) * scale, 6)]

    faces: list[dict[str, Any]] = []
    for e in doc.modelspace():
        layer = e.dxf.layer
        if wanted and layer.upper() not in wanted:
            continue
        kind = e.dxftype()
        polys: list[list] = []
        if kind == "3DFACE":
            pts = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3]
            if pts[3] == pts[2]:
                pts = pts[:3]
            polys.append([tuple(p) for p in pts])
        elif kind == "LWPOLYLINE" and e.closed:
            z = e.dxf.elevation
            polys.append([(x, y, z) for x, y, *_ in e.get_points()])
        elif kind == "POLYLINE":
            if e.is_poly_face_mesh or e.is_polygon_mesh:
                for f in e.virtual_entities():
                    if f.dxftype() == "3DFACE":
                        pts = [f.dxf.vtx0, f.dxf.vtx1, f.dxf.vtx2, f.dxf.vtx3]
                        polys.append([tuple(p) for p in (pts[:3] if pts[3] == pts[2] else pts)])
            elif e.is_closed:
                polys.append([tuple(v.dxf.location) for v in e.vertices])
        elif kind == "MESH":
            verts = [tuple(v) for v in e.vertices]
            for face in e.faces:
                polys.append([verts[i] for i in face])
        for poly in polys:
            if len(poly) >= 3:
                faces.append({"layer": layer, "points": [tr(p) for p in poly]})
    return faces


def import_dxf(
    sess,
    path: str,
    create: str = "surface",
    layers: list[str] | None = None,
    material: str | None = None,
    scale: float = 1.0,
    offset: list[float] | None = None,
    extrusion: list[float] | None = None,
    max_faces: int = 2000,
) -> dict:
    """create: surface | plate | soil_volume (needs extrusion vector)."""
    faces = read_dxf_faces(path, layers, scale, tuple(offset or (0.0, 0.0, 0.0)))
    if len(faces) > max_faces:
        raise RuntimeError(f"{len(faces)} faces found (> max_faces={max_faces}); filter by layers or raise max_faces.")
    if create == "soil_volume" and not extrusion:
        raise RuntimeError("create='soil_volume' needs an extrusion vector [dx, dy, dz].")
    created, warnings = [], []
    for f in faces:
        try:
            if create == "plate":
                r = geometry.create_plate(sess, f["points"], material)
                created.append(r["plate"])
            elif create == "soil_volume":
                r = geometry.create_soil_volume(sess, f["points"], extrusion, material)
                created.append(r["soil"])
            else:
                r = geometry.create_surface(sess, f["points"])
                created.append(r["surface"])
            warnings += r.get("warnings", [])
        except Exception as exc:
            warnings.append(f"layer {f['layer']} face {f['points'][:2]}...: {exc}")
    layers_found = sorted({f["layer"] for f in faces})
    return {"faces": len(faces), "created": created, "layers": layers_found, "warnings": warnings}


# -- Boreholes -------------------------------------------------------------------------------
def _read_table(path: str) -> list[dict[str, Any]]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("Excel import needs openpyxl: pip install openpyxl") from exc
        ws = openpyxl.load_workbook(path, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        header = [str(h).strip().lower() for h in rows[0]]
        return [dict(zip(header, r)) for r in rows[1:] if any(v is not None for v in r)]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return [{k.strip().lower(): v for k, v in row.items()} for row in csv.DictReader(fh, dialect=dialect)]


def parse_boreholes(rows: list[dict[str, Any]]) -> "OrderedDict[str, dict]":
    """Rows: borehole, x, y, top, bottom, material[, head]; one row per layer, top->bottom."""
    required = {"borehole", "x", "y", "top", "bottom", "material"}
    if rows and not required <= set(rows[0]):
        raise RuntimeError(f"Columns required: {sorted(required)} (+ optional 'head'); got {sorted(rows[0])}")
    holes: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        bh = holes.setdefault(
            str(r["borehole"]),
            {"x": float(r["x"]), "y": float(r["y"]), "layers": [], "head": None},
        )
        bh["layers"].append((str(r["material"]).strip(), float(r["top"]), float(r["bottom"])))
        if r.get("head") not in (None, ""):
            bh["head"] = float(r["head"])
    sequence = None
    for name, bh in holes.items():
        lay = bh["layers"]
        for (_, t1, b1), (_, t2, _) in zip(lay, lay[1:]):
            if abs(b1 - t2) > 1e-6:
                raise RuntimeError(f"Borehole {name}: layer bottom {b1} does not match next top {t2}.")
        seq = [m for m, _, _ in lay]
        if sequence is None:
            sequence = seq
        elif seq != sequence:
            raise RuntimeError(
                f"Borehole {name} has layer sequence {seq}, first borehole {sequence}. PLAXIS boreholes share "
                "one layer sequence: add missing layers with zero thickness (top = bottom)."
            )
        bh["levels"] = [lay[0][1]] + [b for _, _, b in lay]
    return holes


def import_boreholes(sess, path: str, create_missing_materials: bool = False) -> dict:
    holes = parse_boreholes(_read_table(path))
    if not holes:
        raise RuntimeError("No borehole rows found.")
    first = next(iter(holes.values()))
    layer_mats = [m for m, _, _ in first["layers"]]
    by_label = {}
    for m in materials.list_materials(sess)["materials"]:
        by_label[m["name"]] = m["name"]
        if m["label"]:
            by_label[m["label"]] = m["name"]
    warnings: list[str] = []
    resolved = []
    for m in layer_mats:
        if m in by_label:
            resolved.append(by_label[m])
        elif create_missing_materials:
            r = materials.create_soil_material_from_preset(sess, "medium_dense_sand", m)
            resolved.append(r["material"])
            warnings.append(f"Material '{m}' created from a placeholder preset - set its parameters.")
        else:
            raise RuntimeError(f"Soil material '{m}' not found; create it first or pass create_missing_materials.")
    created = []
    for i, (name, bh) in enumerate(holes.items()):
        r = geometry.create_borehole(sess, bh["x"], bh["y"], bh["levels"], bh["head"], resolved if i == 0 else None)
        created.append({"id": name, "borehole": r["borehole"]})
        warnings += r["warnings"]
    return {"boreholes": created, "layers": layer_mats, "warnings": warnings}

