"""Headless backend on ezdxf: reads/writes DXF R12-2018 without AutoCAD.

DWG files are handled through the free ODA File Converter when it is installed
(ezdxf.addons.odafc); otherwise save/open as DXF, which every AutoCAD release
and every AutoCAD-compatible CAD can open.
"""

from __future__ import annotations

import math
import os
from typing import Any

from ..versions import DXF_VERSIONS
from .base import Backend, bbox_contains, p3, polygon_area, polyline_length

KIND = {
    "LINE": "line", "LWPOLYLINE": "polyline", "POLYLINE": "polyline", "CIRCLE": "circle", "ARC": "arc",
    "ELLIPSE": "ellipse", "SPLINE": "spline", "TEXT": "text", "MTEXT": "mtext", "INSERT": "insert",
    "DIMENSION": "dimension", "HATCH": "hatch", "POINT": "point", "3DFACE": "3dface", "SOLID": "solid",
    "LEADER": "leader",
}


def _ezdxf():
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("DXF backend needs ezdxf: pip install ezdxf") from exc
    return ezdxf


class DxfBackend(Backend):
    name = "dxf"

    def __init__(self):
        self.doc = None
        self.path: str | None = None

    # -- documents ----------------------------------------------------------------------------
    def _msp(self):
        if self.doc is None:
            self.new_document()
        return self.doc.modelspace()

    def info(self) -> dict:
        ez = _ezdxf()
        return {
            "backend": "dxf", "ezdxf": ez.__version__, "document": self.path,
            "dxfversion": self.doc.dxfversion if self.doc else None,
            "dwg_support": self._odafc() is not None,
        }

    def new_document(self, template: str | None = None, version: str | None = None) -> dict:
        ez = _ezdxf()
        if template:
            self.doc = ez.readfile(template)
        else:
            self.doc = ez.new(DXF_VERSIONS.get(version or "2018", version or "R2018"), setup=True)
        self.path = None
        return {"ok": True, "dxfversion": self.doc.dxfversion}

    def _odafc(self):
        try:
            from ezdxf.addons import odafc

            return odafc if odafc.is_installed() else None
        except Exception:
            return None

    def open_document(self, path: str, read_only: bool = False) -> dict:
        if path.lower().endswith(".dwg"):
            odafc = self._odafc()
            if odafc is None:
                raise RuntimeError("Opening DWG without AutoCAD needs the free ODA File Converter "
                                   "(https://www.opendesign.com/guestfiles/oda_file_converter).")
            self.doc = odafc.readfile(path)
        else:
            self.doc = _ezdxf().readfile(path)
        self.path = path
        return {"ok": True, "path": path, "dxfversion": self.doc.dxfversion,
                "entities": len(self.doc.modelspace())}

    def save_document(self, path: str | None = None, fmt: str | None = None) -> dict:
        if self.doc is None:
            raise RuntimeError("No document.")
        target = path or self.path
        if not target:
            raise RuntimeError("Give a path for a new drawing.")
        folder = os.path.dirname(os.path.abspath(target))
        os.makedirs(folder, exist_ok=True)
        version = None
        if fmt:
            year = fmt.split("_")[0]
            version = DXF_VERSIONS.get(year)
        if target.lower().endswith(".dwg"):
            odafc = self._odafc()
            if odafc is None:
                raise RuntimeError("Saving DWG without AutoCAD needs the ODA File Converter; save as .dxf instead.")
            odafc.export_dwg(self.doc, target, version=version or self.doc.dxfversion, replace=True)
        else:
            if version and version != self.doc.dxfversion:
                self._saveas_version(target, version)
            else:
                self.doc.saveas(target)
        self.path = target
        return {"ok": True, "path": os.path.abspath(target)}

    def _saveas_version(self, target: str, version: str) -> None:
        # ezdxf writes the document's own version; R12 needs the dedicated exporter
        if version == "R12":
            from ezdxf.addons import r12export

            r12export.saveas(self.doc, target)
        else:
            self.doc.dxfversion = version
            self.doc.saveas(target)

    # -- layers ----------------------------------------------------------------------------------
    def list_layers(self) -> list[dict]:
        self._msp()
        return [
            {"name": l.dxf.name, "color": l.color, "linetype": l.dxf.linetype, "on": l.is_on(),
             "frozen": l.is_frozen(), "locked": l.is_locked()}
            for l in self.doc.layers
        ]

    def create_layer(self, name, color=None, linetype=None, lineweight=None, current=False) -> dict:
        self._msp()
        layers = self.doc.layers
        layer = layers.get(name) if name in layers else layers.add(name)
        if color is not None:
            layer.color = int(color)
        if linetype:
            if linetype not in self.doc.linetypes:
                raise RuntimeError(f"Linetype {linetype} not defined (ezdxf setup=True provides the standard set).")
            layer.dxf.linetype = linetype
        if lineweight is not None:
            layer.dxf.lineweight = int(lineweight)
        if current:
            self.doc.header["$CLAYER"] = name
        return {"layer": name}

    # -- drawing ---------------------------------------------------------------------------------
    @staticmethod
    def _attribs(props: dict) -> dict:
        a = {}
        for key, dxf in (("layer", "layer"), ("color", "color"), ("linetype", "linetype"),
                         ("lineweight", "lineweight")):
            if props.get(key) is not None:
                a[dxf] = props[key]
        return a

    def add_line(self, p1, p2, props) -> str:
        return self._msp().add_line(p3(p1), p3(p2), dxfattribs=self._attribs(props)).dxf.handle

    def add_polyline(self, points, closed, props) -> str:
        pts = [p3(p) for p in points]
        if len({round(p[2], 9) for p in pts}) == 1:
            e = self._msp().add_lwpolyline([(x, y) for x, y, _ in pts], close=closed,
                                           dxfattribs={**self._attribs(props), "elevation": pts[0][2]})
        else:
            e = self._msp().add_polyline3d(pts, close=closed, dxfattribs=self._attribs(props))
        return e.dxf.handle

    def add_circle(self, center, radius, props) -> str:
        return self._msp().add_circle(p3(center), radius, dxfattribs=self._attribs(props)).dxf.handle

    def add_arc(self, center, radius, start_deg, end_deg, props) -> str:
        return self._msp().add_arc(p3(center), radius, start_deg, end_deg, dxfattribs=self._attribs(props)).dxf.handle

    def add_text(self, text, point, height, rotation, props) -> str:
        e = self._msp().add_text(text, height=height, rotation=rotation, dxfattribs=self._attribs(props))
        e.set_placement(p3(point))
        return e.dxf.handle

    def add_mtext(self, text, point, width, height, props) -> str:
        e = self._msp().add_mtext(text, dxfattribs={**self._attribs(props), "char_height": height, "width": width,
                                                    "insert": p3(point)})
        return e.dxf.handle

    def add_point(self, point, props) -> str:
        return self._msp().add_point(p3(point), dxfattribs=self._attribs(props)).dxf.handle

    def add_dimension(self, p1, p2, location, angle, props) -> str:
        msp = self._msp()
        th = props.get("text_height")
        # ezdxf's default EZDXF dimstyle scales measurements by 100 (m -> cm); drawings here are in mm
        override: dict[str, Any] = {"dimlfac": 1.0, "dimdec": 0, "dimtad": 1}
        if th:
            override.update(dimtxt=th, dimasz=th, dimexe=0.5 * th, dimexo=0.5 * th, dimgap=0.3 * th)
        if angle is None:
            dim = msp.add_aligned_dim(p1=p3(p1)[:2], p2=p3(p2)[:2], distance=_offset(p1, p2, location),
                                      override=override, dxfattribs=self._attribs(props))
        else:
            dim = msp.add_linear_dim(base=p3(location)[:2], p1=p3(p1)[:2], p2=p3(p2)[:2], angle=angle,
                                     override=override, dxfattribs=self._attribs(props))
        dim.render()
        return dim.dimension.dxf.handle

    def add_hatch(self, outer, holes, pattern, scale, props) -> str:
        h = self._msp().add_hatch(dxfattribs=self._attribs(props))
        if pattern.upper() == "SOLID":
            h.set_solid_fill()
        else:
            h.set_pattern_fill(pattern.upper(), scale=scale)
        h.paths.add_polyline_path([p3(p)[:2] for p in outer], is_closed=True, flags=1)  # external
        for hole in holes:
            h.paths.add_polyline_path([p3(p)[:2] for p in hole], is_closed=True, flags=16)  # outermost
        return h.dxf.handle

    def insert_block(self, name, point, scale, rotation, attributes, props) -> str:
        msp = self._msp()
        if os.path.isfile(name):
            name = self._import_block_file(name)
        if name not in self.doc.blocks:
            raise RuntimeError(f"Block '{name}' is not defined in this drawing.")
        ref = msp.add_blockref(name, p3(point), dxfattribs={**self._attribs(props), "xscale": scale,
                                                            "yscale": scale, "zscale": scale, "rotation": rotation})
        if attributes is not None or any(True for _ in self.doc.blocks[name].attdefs()):
            ref.add_auto_attribs(attributes or {})
        return ref.dxf.handle

    def _import_block_file(self, path: str) -> str:
        from ezdxf.addons import importer

        src = _ezdxf().readfile(path)
        name = os.path.splitext(os.path.basename(path))[0]
        if name not in self.doc.blocks:
            blk = self.doc.blocks.new(name)
            imp = importer.Importer(src, self.doc)
            imp.import_entities(src.modelspace(), blk)
            imp.finalize()
        return name

    # -- query / modify -------------------------------------------------------------------------
    def _describe(self, e) -> dict:
        t = e.dxftype()
        d: dict[str, Any] = {"handle": e.dxf.handle, "kind": KIND.get(t, "other"), "type": t,
                             "layer": e.dxf.get("layer", "0"), "color": e.dxf.get("color", 256)}
        try:
            if t == "LINE":
                d.update(start=list(e.dxf.start), end=list(e.dxf.end), length=math.dist(e.dxf.start, e.dxf.end))
            elif t == "LWPOLYLINE":
                pts = [(x, y) for x, y, *_ in e.get_points()]
                d.update(points=[list(p) for p in pts], closed=e.closed, elevation=e.dxf.elevation,
                         length=polyline_length(pts, e.closed), area=polygon_area(pts) if e.closed else None)
            elif t == "POLYLINE":
                pts = [tuple(v.dxf.location) for v in e.vertices]
                d.update(points=[list(p) for p in pts], closed=e.is_closed, kind="polyline3d" if e.is_3d_polyline
                         else "polyline", length=polyline_length(pts, e.is_closed))
            elif t == "CIRCLE":
                r = e.dxf.radius
                d.update(center=list(e.dxf.center), radius=r, length=2 * math.pi * r, area=math.pi * r * r)
            elif t == "ARC":
                r, a0, a1 = e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle
                d.update(center=list(e.dxf.center), radius=r, start_angle=a0, end_angle=a1,
                         length=r * math.radians((a1 - a0) % 360))
            elif t in ("TEXT", "MTEXT"):
                d.update(text=e.dxf.text if t == "TEXT" else e.text, insert=list(e.dxf.insert),
                         height=e.dxf.height if t == "TEXT" else e.dxf.char_height)
            elif t == "INSERT":
                d.update(block=e.dxf.name, insert=list(e.dxf.insert), rotation=e.dxf.rotation,
                         attributes={a.dxf.tag: a.dxf.text for a in e.attribs})
            elif t == "DIMENSION":
                d.update(measurement=e.get_measurement() if hasattr(e, "get_measurement") else None,
                         text=e.dxf.get("text", ""))
            elif t == "HATCH":
                d.update(pattern=e.dxf.pattern_name)
            elif t == "POINT":
                d.update(location=list(e.dxf.location))
        except Exception as exc:  # malformed entity: keep what we have
            d["error"] = str(exc)
        return d

    def _extents(self, e):
        from ezdxf import bbox

        box = bbox.extents([e])
        if not box.has_data:
            return None
        return box.extmin, box.extmax

    def list_entities(self, layers, kinds, bbox, limit) -> list[dict]:
        out = []
        wanted_layers = {l.upper() for l in layers} if layers else None
        for e in self._msp():
            if wanted_layers and e.dxf.get("layer", "0").upper() not in wanted_layers:
                continue
            d = self._describe(e)
            if kinds and d["kind"] not in kinds:
                continue
            if bbox:
                ext = self._extents(e)
                if ext is None or not bbox_contains(bbox, *ext):
                    continue
            out.append(d)
            if len(out) >= limit:
                break
        return out

    def _entity(self, handle: str):
        self._msp()
        e = self.doc.entitydb.get(handle.upper())
        if e is None or not e.is_alive:
            raise RuntimeError(f"No entity with handle {handle}.")
        return e

    def get_entity(self, handle: str) -> dict:
        return self._describe(self._entity(handle))

    def transform(self, handles, op, **kw) -> list[str]:
        from ezdxf.math import Matrix44

        if op == "move":
            v = [b - a for a, b in zip(p3(kw["base"]), p3(kw["to"]))]
            m = Matrix44.translate(*v)
        elif op in ("rotate", "scale", "mirror"):
            bx, by, bz = p3(kw["base"])
            if op == "rotate":
                core = Matrix44.z_rotate(math.radians(kw["angle"]))
            elif op == "scale":
                core = Matrix44.scale(kw["factor"])
            else:  # mirror about the line base -> base2
                x2, y2, _ = p3(kw["base2"])
                ang = math.atan2(y2 - by, x2 - bx)
                core = Matrix44.chain(Matrix44.z_rotate(-ang), Matrix44.scale(1, -1, 1), Matrix44.z_rotate(ang))
            m = Matrix44.chain(Matrix44.translate(-bx, -by, -bz), core, Matrix44.translate(bx, by, bz))
        else:
            raise RuntimeError(f"Unknown operation {op}; use move | copy | rotate | scale | mirror.")
        out = []
        for h in handles:
            e = self._entity(h)
            if kw.get("copy"):
                e = e.copy()
                self._msp().add_entity(e)
            e.transform(m)
            out.append(e.dxf.handle)
        return out

    def set_properties(self, handles, props) -> list[str]:
        warnings = []
        for h in handles:
            e = self._entity(h)
            for k, v in props.items():
                key = {"Layer": "layer", "Color": "color", "Linetype": "linetype", "TextString": "text",
                       "Height": "height", "Lineweight": "lineweight"}.get(k, k)
                try:
                    if key == "text" and e.dxftype() == "MTEXT":
                        e.text = v
                    else:
                        e.dxf.set(key, v)
                except Exception as exc:
                    warnings.append(f"{h}.{k}: {exc}")
        return warnings

    def delete(self, handles) -> int:
        for h in handles:
            self._msp().delete_entity(self._entity(h))
        return len(handles)

    def list_blocks(self) -> list[dict]:
        self._msp()
        return [
            {"name": b.name, "entities": len(b), "attributes": [a.dxf.tag for a in b.attdefs()],
             "xref": b.block.is_xref}
            for b in self.doc.blocks if not b.name.startswith("*")
        ]

    # -- extras ------------------------------------------------------------------------------------
    def render_png(self, path: str) -> str:
        try:
            from ezdxf.addons.drawing import matplotlib as draw
        except ImportError as exc:
            raise RuntimeError("Preview needs matplotlib: pip install matplotlib") from exc
        draw.qsave(self._msp(), path, bg="#212830", dpi=150)  # AutoCAD-like dark model space
        return os.path.abspath(path)


def _offset(p1, p2, loc) -> float:
    """Signed distance of the dimension line location from the measured line p1-p2."""
    (x1, y1, _), (x2, y2, _), (x, y, _) = p3(p1), p3(p2), p3(loc)
    length = math.hypot(x2 - x1, y2 - y1) or 1.0
    return ((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) / length
