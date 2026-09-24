"""Backend-independent drafting helpers for bridge / road / culvert drawings.

Drawing units are millimetres (Vietnamese drafting practice, TCVN 8-20:2002 /
TCVN 5570:2012 for construction drawings). Text heights follow the paper size:
model height = paper height x drawing scale (2.5 mm at 1:50 -> 125 mm).
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from ..backends.base import Backend, p3

LAYERS = {
    # name: (ACI colour, linetype)
    "KC_BETONG": (7, "Continuous"),
    "KC_HATCH": (8, "Continuous"),
    "KC_KICHTHUOC": (3, "Continuous"),
    "KC_TEXT": (2, "Continuous"),
    "KC_TRUC": (1, "CENTER"),
}


def ensure_layers(be: Backend) -> list[str]:
    warnings = []
    for name, (color, lt) in LAYERS.items():
        try:
            r = be.create_layer(name, color=color, linetype=None if lt == "Continuous" else lt)
            warnings += r.get("warnings", []) if isinstance(r, dict) else []
        except Exception as exc:
            warnings.append(f"layer {name}: {exc}")
    return warnings


# -- culvert section ---------------------------------------------------------------------------------
@dataclass
class CulvertSection:
    clear_width: float = 4000.0  # mm
    clear_height: float = 3200.0
    t_top: float = 450.0
    t_bottom: float = 500.0
    t_wall: float = 400.0
    haunch: float = 200.0  # 45 degree haunch (vát nách) leg length
    origin: tuple[float, float] = (0.0, 0.0)  # bottom-left outer corner
    scale: float = 50.0  # drawing scale 1:scale
    hatch: bool = True
    title: str | None = None


def culvert_outline(s: CulvertSection) -> tuple[list[tuple], list[tuple]]:
    x0, y0 = s.origin
    bo = s.clear_width + 2 * s.t_wall
    ho = s.clear_height + s.t_top + s.t_bottom
    outer = [(x0, y0), (x0 + bo, y0), (x0 + bo, y0 + ho), (x0, y0 + ho)]
    xl, xr = x0 + s.t_wall, x0 + s.t_wall + s.clear_width
    yb, yt = y0 + s.t_bottom, y0 + s.t_bottom + s.clear_height
    c = s.haunch
    if c > 0:
        inner = [(xl + c, yb), (xr - c, yb), (xr, yb + c), (xr, yt - c), (xr - c, yt), (xl + c, yt),
                 (xl, yt - c), (xl, yb + c)]
    else:
        inner = [(xl, yb), (xr, yb), (xr, yt), (xl, yt)]
    return outer, inner


def draw_culvert_section(be: Backend, s: CulvertSection) -> dict[str, Any]:
    if min(s.clear_width, s.clear_height, s.t_top, s.t_bottom, s.t_wall) <= 0:
        raise RuntimeError("Dimensions must be positive (mm).")
    if 2 * s.haunch >= min(s.clear_width, s.clear_height):
        raise RuntimeError("Haunch too large for the opening.")
    warnings = ensure_layers(be)
    th = 2.5 * s.scale  # text height on paper 2.5 mm
    gap = 8.0 * s.scale  # distance between dimension rows
    dim = {"layer": "KC_KICHTHUOC", "text_height": th}
    outer, inner = culvert_outline(s)
    x0, y0 = s.origin
    bo = outer[1][0] - x0
    ho = outer[2][1] - y0
    xl, xr = x0 + s.t_wall, x0 + s.t_wall + s.clear_width
    yb, yt = y0 + s.t_bottom, y0 + s.t_bottom + s.clear_height

    h: dict[str, Any] = {}
    h["outer"] = be.add_polyline(outer, True, {"layer": "KC_BETONG"})
    h["inner"] = be.add_polyline(inner, True, {"layer": "KC_BETONG"})
    if s.hatch:
        try:
            h["hatch"] = be.add_hatch(outer, [inner], "ANSI31", s.scale * 0.5, {"layer": "KC_HATCH"})
        except Exception as exc:
            warnings.append(f"hatch: {exc}")
    cx = x0 + bo / 2
    h["axis"] = be.add_line((cx, y0 - gap), (cx, y0 + ho + gap), {"layer": "KC_TRUC"})

    dims = []
    # bottom chain: wall | clear | wall, then overall
    for a, b in ((x0, xl), (xl, xr), (xr, x0 + bo)):
        dims.append(be.add_dimension((a, y0), (b, y0), (a, y0 - gap), 0.0, dim))
    dims.append(be.add_dimension((x0, y0), (x0 + bo, y0), (x0, y0 - 2 * gap), 0.0, dim))
    # right chain: bottom slab | clear | top slab, then overall
    for a, b in ((y0, yb), (yb, yt), (yt, y0 + ho)):
        dims.append(be.add_dimension((x0 + bo, a), (x0 + bo, b), (x0 + bo + gap, a), 90.0, dim))
    dims.append(be.add_dimension((x0 + bo, y0), (x0 + bo, y0 + ho), (x0 + bo + 2 * gap, y0), 90.0, dim))
    if s.haunch > 0:
        # haunch legs (c x c)
        dims.append(be.add_dimension((xl, yb + s.haunch), (xl + s.haunch, yb), (xl, yb + s.haunch + 0.5 * gap),
                                     0.0, dim))
        dims.append(be.add_dimension((xl, yb + s.haunch), (xl + s.haunch, yb), (xl + s.haunch + 0.5 * gap, yb),
                                     90.0, dim))
    h["dimensions"] = dims

    title = s.title or (f"MẶT CẮT NGANG CỐNG HỘP {s.clear_width / 1000:g}x{s.clear_height / 1000:g} m")
    h["title"] = be.add_text(title, (x0, y0 + ho + 2 * gap), 1.4 * th, 0.0, {"layer": "KC_TEXT"})
    h["scale_text"] = be.add_text(f"TL 1:{s.scale:g}", (x0, y0 + ho + 2 * gap - 2.2 * th), th, 0.0,
                                  {"layer": "KC_TEXT"})
    area = (bo * ho - _area(inner)) / 1e6  # m2 per metre length
    return {"handles": h, "concrete_area_m2_per_m": round(area, 4), "params": asdict(s), "warnings": warnings}


def _area(pts):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2.0


# -- tables --------------------------------------------------------------------------------------------------
def draw_table(
    be: Backend,
    origin: list[float],
    rows: list[list[Any]],
    col_widths: list[float],
    row_height: float,
    text_height: float,
    layer: str = "KC_TEXT",
) -> dict:
    """Grid of lines + TEXT (works in every AutoCAD release and DXF R12). origin = top-left."""
    if not rows:
        raise RuntimeError("rows is empty.")
    ncol = max(len(r) for r in rows)
    widths = (list(col_widths) + [col_widths[-1]] * ncol)[:ncol] if col_widths else [30 * text_height] * ncol
    x0, y0, _ = p3(origin)
    total_w = sum(widths)
    props = {"layer": layer}
    handles = []
    for i in range(len(rows) + 1):
        y = y0 - i * row_height
        handles.append(be.add_line((x0, y), (x0 + total_w, y), props))
    x = x0
    for w in [0.0] + widths:
        x += w
        handles.append(be.add_line((x, y0), (x, y0 - len(rows) * row_height), props))
    for i, row in enumerate(rows):
        x = x0
        for j, cell in enumerate(row):
            ty = y0 - (i + 1) * row_height + (row_height - text_height) / 2
            handles.append(be.add_text("" if cell is None else str(cell), (x + 0.5 * text_height, ty),
                                       text_height, 0.0, props))
            x += widths[j]
    return {"handles": handles, "size": [total_w, len(rows) * row_height]}


# -- take-off ----------------------------------------------------------------------------------------------
def quantities_by_layer(be: Backend, layers: list[str] | None = None, limit: int = 100000) -> dict:
    """Total length (lines, arcs, polylines, circles), closed area and block counts per layer."""
    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "length": 0.0, "area": 0.0,
                                                          "blocks": defaultdict(int)})
    for e in be.list_entities(layers, None, None, limit):
        a = agg[e["layer"]]
        a["count"] += 1
        if isinstance(e.get("length"), (int, float)):
            a["length"] += e["length"]
        if isinstance(e.get("area"), (int, float)):
            a["area"] += e["area"]
        if e["kind"] == "insert":
            a["blocks"][e.get("block")] += 1
    out = {}
    for layer, a in sorted(agg.items()):
        out[layer] = {"count": a["count"], "length": round(a["length"], 3), "area": round(a["area"], 3),
                      "blocks": dict(a["blocks"])}
    return out


def extract_attributes(be: Backend, block: str | None = None, path: str | None = None, limit: int = 100000) -> dict:
    """Attribute values of all block references (title blocks, pile tables, survey points...)."""
    rows = []
    for e in be.list_entities(None, ["insert"], None, limit):
        if block and (e.get("block") or "").upper() != block.upper():
            continue
        rows.append({"handle": e["handle"], "block": e.get("block"), "layer": e["layer"],
                     "x": (e.get("insert") or [None])[0], "y": (e.get("insert") or [None, None])[1],
                     **(e.get("attributes") or {})})
    out: dict[str, Any] = {"count": len(rows), "rows": rows[:500], "truncated": len(rows) > 500}
    if path and rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        out["path"] = os.path.abspath(path)
    return out


def extract_texts(be: Backend, layers: list[str] | None = None, bbox: list[float] | None = None,
                  limit: int = 5000) -> dict:
    """All TEXT/MTEXT with insertion points, sorted top-to-bottom, left-to-right."""
    items = be.list_entities(layers, ["text", "mtext"], bbox, limit)
    rows = [{"text": e.get("text"), "x": (e.get("insert") or [0])[0], "y": (e.get("insert") or [0, 0])[1],
             "layer": e["layer"], "handle": e["handle"]} for e in items]
    rows.sort(key=lambda r: (-round(r["y"] or 0, 1), r["x"] or 0))
    return {"count": len(rows), "texts": rows}

