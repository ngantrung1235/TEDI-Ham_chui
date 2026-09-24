"""Live AutoCAD backend over COM/ActiveX (pywin32, late binding).

Only members that exist since AutoCAD 2000 are used on the main path; newer
members (EffectiveName, TrueColor, PlotToFile with a PC3) are tried and fall
back gracefully, so the same code drives AutoCAD 2000 ... 2026, Civil 3D and
AutoCAD-compatible CADs (BricsCAD, ZWCAD, GstarCAD).
"""

from __future__ import annotations

import math
import os
import time
from typing import Any, Callable

from ..versions import PROGIDS, SAVE_FORMATS, release_name
from .base import Backend, bbox_contains, p3, rad

KIND = {
    "AcDbLine": "line", "AcDbPolyline": "polyline", "AcDb2dPolyline": "polyline", "AcDb3dPolyline": "polyline3d",
    "AcDbCircle": "circle", "AcDbArc": "arc", "AcDbEllipse": "ellipse", "AcDbSpline": "spline",
    "AcDbText": "text", "AcDbMText": "mtext", "AcDbBlockReference": "insert", "AcDbHatch": "hatch",
    "AcDbPoint": "point", "AcDbFace": "3dface", "AcDbTrace": "solid", "AcDbSolid": "solid", "AcDbLeader": "leader",
}


def _win32_variants():
    import pythoncom
    from win32com.client import VARIANT

    def doubles(values):
        return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])

    def objects(values):
        return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(values))

    return doubles, objects


def _win32_connect(progid: str | None, start: bool, visible: bool):
    import win32com.client

    candidates = [progid] if progid else PROGIDS
    errors = []
    for pid in candidates:  # attach to a running instance first
        try:
            return win32com.client.GetActiveObject(pid), pid, False
        except Exception as exc:
            errors.append(f"{pid}: {exc}")
    if start:
        for pid in candidates:
            try:
                app = win32com.client.dynamic.Dispatch(pid)
                app.Visible = visible
                return app, pid, True
            except Exception as exc:
                errors.append(f"start {pid}: {exc}")
    raise RuntimeError("No AutoCAD found. Start AutoCAD (any release) or install it. Tried: " + "; ".join(errors[-4:]))


class ComBackend(Backend):
    name = "com"

    def __init__(self, connector: Callable | None = None, variants: tuple[Callable, Callable] | None = None):
        self._connector = connector or _win32_connect
        self._variants = variants
        self.app: Any = None
        self.progid: str | None = None

    # -- connection -------------------------------------------------------------------------------
    def connect(self, progid: str | None = None, start: bool = True, visible: bool = True) -> dict:
        self.app, self.progid, started = self._connector(progid, start, visible)
        if self._variants is None:
            self._variants = _win32_variants()
        if started:  # AutoCAD needs a moment before its object model answers
            for _ in range(60):
                try:
                    _ = self.app.Documents.Count
                    break
                except Exception:
                    time.sleep(0.5)
        return self.info()

    def _app(self):
        if self.app is None:
            self.connect()
        return self.app

    def _doc(self):
        app = self._app()
        if app.Documents.Count == 0:
            app.Documents.Add()
        return app.ActiveDocument

    def _pt(self, p):
        return self._variants[0](p3(p))

    def _arr(self, values):
        return self._variants[0](values)

    def _space(self):
        doc = self._doc()
        try:
            return doc.PaperSpace if doc.ActiveSpace == 0 else doc.ModelSpace  # acPaperSpace = 0
        except Exception:
            return doc.ModelSpace

    # -- documents -----------------------------------------------------------------------------------
    def info(self) -> dict:
        app = self._app()
        version = str(app.Version)
        docs = []
        for i in range(app.Documents.Count):
            d = app.Documents.Item(i)
            docs.append({"name": d.Name, "path": _safe(lambda: d.FullName)})
        return {
            "backend": "com", "progid": self.progid, "product": _safe(lambda: app.Name), "version": version,
            "release": release_name(version), "documents": docs,
            "active": _safe(lambda: app.ActiveDocument.Name) if docs else None,
        }

    def new_document(self, template: str | None = None, version: str | None = None) -> dict:
        docs = self._app().Documents
        doc = docs.Add(template) if template else docs.Add()
        return {"name": doc.Name}

    def open_document(self, path: str, read_only: bool = False) -> dict:
        doc = self._app().Documents.Open(path, read_only)
        return {"name": doc.Name, "path": path}

    def activate_document(self, name: str) -> dict:
        app = self._app()
        for i in range(app.Documents.Count):
            d = app.Documents.Item(i)
            if d.Name.lower() == name.lower():
                d.Activate()
                return {"active": d.Name}
        raise RuntimeError(f"Document {name} is not open.")

    def save_document(self, path: str | None = None, fmt: str | None = None) -> dict:
        doc = self._doc()
        if path:
            if fmt:
                if fmt not in SAVE_FORMATS:
                    raise RuntimeError(f"Unknown format {fmt}; use one of {sorted(SAVE_FORMATS)}")
                doc.SaveAs(path, SAVE_FORMATS[fmt])
            else:
                doc.SaveAs(path)
        else:
            doc.Save()
        return {"ok": True, "path": _safe(lambda: doc.FullName)}

    def close_document(self, save: bool = False) -> dict:
        doc = self._doc()
        name = doc.Name
        doc.Close(save)
        return {"closed": name}

    # -- layers -----------------------------------------------------------------------------------------
    def list_layers(self) -> list[dict]:
        out = []
        for layer in _items(self._doc().Layers):
            out.append({"name": layer.Name, "color": _safe(lambda: layer.Color), "linetype": layer.Linetype,
                        "on": layer.LayerOn, "frozen": layer.Freeze, "locked": layer.Lock})
        return out

    def create_layer(self, name, color=None, linetype=None, lineweight=None, current=False) -> dict:
        doc = self._doc()
        layer = doc.Layers.Add(name)  # returns the existing layer if present
        warnings = []
        if color is not None:
            layer.Color = int(color)
        if linetype:
            warnings += self._ensure_linetype(linetype)
            try:
                layer.Linetype = linetype
            except Exception as exc:
                warnings.append(f"linetype {linetype}: {exc}")
        if lineweight is not None:
            try:
                layer.Lineweight = int(lineweight)
            except Exception as exc:
                warnings.append(f"lineweight: {exc}")
        if current:
            doc.ActiveLayer = layer
        return {"layer": name, "warnings": warnings}

    def _ensure_linetype(self, name: str) -> list[str]:
        doc = self._doc()
        if any(lt.Name.upper() == name.upper() for lt in _items(doc.Linetypes)):
            return []
        for lin in ("acadiso.lin", "acad.lin"):
            try:
                doc.Linetypes.Load(name, lin)
                return []
            except Exception:
                continue
        return [f"Linetype {name} not found in acadiso.lin/acad.lin"]

    # -- drawing -----------------------------------------------------------------------------------------
    def _apply(self, ent, props: dict) -> str:
        for key, attr in (("layer", "Layer"), ("color", "Color"), ("linetype", "Linetype"),
                          ("lineweight", "Lineweight")):
            if props.get(key) is not None:
                if key == "linetype":
                    self._ensure_linetype(props[key])
                setattr(ent, attr, props[key])
        return ent.Handle

    def add_line(self, p1, p2, props) -> str:
        return self._apply(self._space().AddLine(self._pt(p1), self._pt(p2)), props)

    def add_polyline(self, points, closed, props) -> str:
        pts = [p3(p) for p in points]
        space = self._space()
        if len({round(p[2], 9) for p in pts}) == 1:
            ent = space.AddLightWeightPolyline(self._arr([c for x, y, _ in pts for c in (x, y)]))
            if pts[0][2]:
                ent.Elevation = pts[0][2]
        else:
            ent = space.Add3DPoly(self._arr([c for p in pts for c in p]))
        if closed:
            ent.Closed = True
        return self._apply(ent, props)

    def add_circle(self, center, radius, props) -> str:
        return self._apply(self._space().AddCircle(self._pt(center), float(radius)), props)

    def add_arc(self, center, radius, start_deg, end_deg, props) -> str:
        return self._apply(self._space().AddArc(self._pt(center), float(radius), rad(start_deg), rad(end_deg)), props)

    def add_text(self, text, point, height, rotation, props) -> str:
        ent = self._space().AddText(text, self._pt(point), float(height))
        if rotation:
            ent.Rotation = rad(rotation)
        return self._apply(ent, props)

    def add_mtext(self, text, point, width, height, props) -> str:
        ent = self._space().AddMText(self._pt(point), float(width), text)
        ent.Height = float(height)
        return self._apply(ent, props)

    def add_point(self, point, props) -> str:
        return self._apply(self._space().AddPoint(self._pt(point)), props)

    def add_dimension(self, p1, p2, location, angle, props) -> str:
        space = self._space()
        if angle is None:
            ent = space.AddDimAligned(self._pt(p1), self._pt(p2), self._pt(location))
        else:
            ent = space.AddDimRotated(self._pt(p1), self._pt(p2), self._pt(location), rad(angle))
        th = props.get("text_height")
        if th:
            for attr, value in (("TextHeight", th), ("ArrowheadSize", th), ("ExtensionLineExtend", 0.5 * th),
                                ("ExtensionLineOffset", 0.5 * th), ("TextGap", 0.3 * th)):
                _safe(lambda: setattr(ent, attr, value))
        return self._apply(ent, props)

    def add_hatch(self, outer, holes, pattern, scale, props) -> str:
        space = self._space()
        objs = self._variants[1]
        # boundaries are real closed polylines, kept so the hatch stays associative
        loops = [self.add_polyline(outer, True, props)] + [self.add_polyline(h, True, props) for h in holes]
        doc = self._doc()
        hatch = space.AddHatch(1, pattern.upper(), True)  # 1 = acHatchPatternTypePreDefined (incl. SOLID)
        hatch.AppendOuterLoop(objs([doc.HandleToObject(loops[0])]))
        for h in loops[1:]:
            hatch.AppendInnerLoop(objs([doc.HandleToObject(h)]))
        if pattern.upper() != "SOLID":
            hatch.PatternScale = float(scale)
        hatch.Evaluate()
        return self._apply(hatch, props)

    def insert_block(self, name, point, scale, rotation, attributes, props) -> str:
        ref = self._space().InsertBlock(self._pt(point), name, float(scale), float(scale), float(scale), rad(rotation))
        if attributes and _safe(lambda: ref.HasAttributes):
            wanted = {k.upper(): v for k, v in attributes.items()}
            for att in _items_array(ref.GetAttributes()):
                if att.TagString.upper() in wanted:
                    att.TextString = str(wanted[att.TagString.upper()])
        return self._apply(ref, props)

    # -- query ---------------------------------------------------------------------------------------------
    def _describe(self, e) -> dict:
        on = e.ObjectName
        kind = KIND.get(on, "dimension" if "Dimension" in on else "other")
        d: dict[str, Any] = {"handle": e.Handle, "kind": kind, "type": on, "layer": e.Layer,
                             "color": _safe(lambda: e.Color)}
        get = lambda attr: _safe(lambda: _plain(getattr(e, attr)))  # noqa: E731
        if kind == "line":
            d.update(start=get("StartPoint"), end=get("EndPoint"), length=get("Length"))
        elif kind in ("polyline", "polyline3d"):
            coords = get("Coordinates") or []
            step = 2 if on == "AcDbPolyline" else 3
            d.update(points=[list(coords[i:i + step]) for i in range(0, len(coords), step)], closed=get("Closed"),
                     length=get("Length"), area=get("Area") if get("Closed") else None)
        elif kind == "circle":
            d.update(center=get("Center"), radius=get("Radius"), length=get("Circumference"), area=get("Area"))
        elif kind == "arc":
            d.update(center=get("Center"), radius=get("Radius"), start_angle=_deg(get("StartAngle")),
                     end_angle=_deg(get("EndAngle")), length=get("ArcLength"))
        elif kind in ("text", "mtext"):
            d.update(text=get("TextString"), insert=get("InsertionPoint"), height=get("Height"))
        elif kind == "insert":
            d.update(block=_safe(lambda: e.EffectiveName) or e.Name, insert=get("InsertionPoint"),
                     rotation=_deg(get("Rotation")))
            if _safe(lambda: e.HasAttributes):
                d["attributes"] = {a.TagString: a.TextString for a in _items_array(e.GetAttributes())}
        elif kind == "dimension":
            d.update(measurement=get("Measurement"), text=get("TextOverride"))
        elif kind == "hatch":
            d.update(pattern=get("PatternName"), area=get("Area"))
        elif kind == "point":
            d.update(location=get("Coordinates"))
        return d

    def list_entities(self, layers, kinds, bbox, limit) -> list[dict]:
        wanted = {l.upper() for l in layers} if layers else None
        out = []
        space = self._space()
        for i in range(space.Count):
            e = space.Item(i)
            if wanted and e.Layer.upper() not in wanted:
                continue
            on = e.ObjectName
            kind = KIND.get(on, "dimension" if "Dimension" in on else "other")
            if kinds and kind not in kinds and not (kind == "polyline3d" and "polyline" in kinds):
                continue
            if bbox:
                ext = _safe(lambda: e.GetBoundingBox())
                if not ext or not bbox_contains(bbox, *ext):
                    continue
            out.append(self._describe(e))
            if len(out) >= limit:
                break
        return out

    def _entity(self, handle: str):
        try:
            return self._doc().HandleToObject(handle)
        except Exception as exc:
            raise RuntimeError(f"No entity with handle {handle}: {exc}") from exc

    def get_entity(self, handle: str) -> dict:
        return self._describe(self._entity(handle))

    # -- modify -----------------------------------------------------------------------------------------
    def transform(self, handles, op, **kw) -> list[str]:
        out = []
        for h in handles:
            e = self._entity(h)
            if kw.get("copy"):
                e = e.Copy()
            if op == "move":
                e.Move(self._pt(kw["base"]), self._pt(kw["to"]))
            elif op == "rotate":
                e.Rotate(self._pt(kw["base"]), rad(kw["angle"]))
            elif op == "scale":
                e.ScaleEntity(self._pt(kw["base"]), float(kw["factor"]))
            elif op == "mirror":
                m = e.Mirror(self._pt(kw["base"]), self._pt(kw["base2"]))
                if not kw.get("copy"):
                    e.Delete()
                e = m
            else:
                raise RuntimeError(f"Unknown operation {op}; use move | rotate | scale | mirror (+copy).")
            out.append(e.Handle)
        return out

    def offset(self, handle: str, distance: float) -> list[str]:
        return [o.Handle for o in _items_array(self._entity(handle).Offset(float(distance)))]

    def set_properties(self, handles, props) -> list[str]:
        warnings = []
        for h in handles:
            e = self._entity(h)
            for k, v in props.items():
                attr = {"layer": "Layer", "color": "Color", "linetype": "Linetype", "text": "TextString",
                        "height": "Height", "lineweight": "Lineweight"}.get(k, k)
                try:
                    setattr(e, attr, v)
                except Exception as exc:
                    warnings.append(f"{h}.{attr}: {exc}")
        return warnings

    def delete(self, handles) -> int:
        for h in handles:
            self._entity(h).Delete()
        return len(handles)

    def list_blocks(self) -> list[dict]:
        out = []
        for b in _items(self._doc().Blocks):
            name = b.Name
            if name.startswith("*"):
                continue
            atts = []
            for i in range(b.Count):
                ent = b.Item(i)
                if ent.ObjectName == "AcDbAttributeDefinition":
                    atts.append(ent.TagString)
            out.append({"name": name, "entities": b.Count, "attributes": atts,
                        "xref": _safe(lambda: b.IsXRef)})
        return out

    # -- AutoCAD-only extras ---------------------------------------------------------------------------------
    def send_command(self, command: str) -> dict:
        """Queue a command line (asynchronous in AutoCAD: it runs when AutoCAD is idle)."""
        cmd = command if command.endswith(("\n", " ")) else command + "\n"
        self._doc().SendCommand(cmd)
        return {"sent": command}

    def eval_lisp(self, expression: str, wait: float = 10.0) -> dict:
        """Evaluate AutoLISP and read the result back through the USERS5 system variable."""
        doc = self._doc()
        doc.SetVariable("USERS5", "")
        doc.SendCommand(f'(setvar "USERS5" (vl-princ-to-string {expression})) ')
        deadline = time.time() + wait
        value = ""
        while time.time() < deadline:
            value = doc.GetVariable("USERS5")
            if value:
                break
            time.sleep(0.2)
        return {"expression": expression, "result": value, "complete": bool(value)}

    def get_variable(self, name: str) -> Any:
        return _plain(self._doc().GetVariable(name))

    def set_variable(self, name: str, value: Any) -> None:
        self._doc().SetVariable(name, value)

    def zoom_extents(self) -> None:
        self._app().ZoomExtents()

    def plot_to_file(self, path: str, device: str = "DWG To PDF.pc3") -> dict:
        """Plot the active layout (current page setup) to PDF/PNG through a PC3 device."""
        doc = self._doc()
        old = _safe(lambda: doc.GetVariable("BACKGROUNDPLOT"))
        _safe(lambda: doc.SetVariable("BACKGROUNDPLOT", 0))  # synchronous plot
        try:
            ok = doc.Plot.PlotToFile(path, device)
        finally:
            if old is not None:
                _safe(lambda: doc.SetVariable("BACKGROUNDPLOT", old))
        return {"ok": bool(ok) if ok is not None else os.path.exists(path), "path": path, "device": device}


# -- helpers ------------------------------------------------------------------------------------------------
def _safe(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception:
        return None


def _items(collection) -> list:
    return [collection.Item(i) for i in range(collection.Count)]


def _items_array(value) -> list:
    return list(value) if value is not None else []


def _plain(v: Any) -> Any:
    if isinstance(v, (tuple, list)):
        return [_plain(x) for x in v]
    return v


def _deg(v: Any) -> float | None:
    return None if v is None else math.degrees(v)
