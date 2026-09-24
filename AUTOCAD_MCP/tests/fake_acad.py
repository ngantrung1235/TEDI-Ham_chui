"""Minimal stand-in for the AutoCAD ActiveX object model (enough for the COM backend tests)."""

from __future__ import annotations

import itertools
import math

_handles = itertools.count(0x100)


class Coll:
    def __init__(self, items=None):
        self.items = list(items or [])

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        if isinstance(i, str):
            for it in self.items:
                if it.Name.upper() == i.upper():
                    return it
            raise KeyError(i)
        return self.items[i]


class Layer:
    def __init__(self, name):
        self.Name, self.Color, self.Linetype = name, 7, "Continuous"
        self.LayerOn, self.Freeze, self.Lock, self.Lineweight = True, False, False, -3


class Layers(Coll):
    def Add(self, name):
        for it in self.items:
            if it.Name.upper() == name.upper():
                return it
        layer = Layer(name)
        self.items.append(layer)
        return layer


class Linetype:
    def __init__(self, name):
        self.Name = name


class Linetypes(Coll):
    def Load(self, name, file):
        if name.upper() not in {"CENTER", "DASHED", "HIDDEN"}:
            raise RuntimeError("not in lin file")
        self.items.append(Linetype(name))


class Ent:
    def __init__(self, space, object_name, **props):
        base = {"Layer": "0", "Color": 256, "Linetype": "ByLayer", "Lineweight": -1}
        self.__dict__.update(_space=space, calls=[], ObjectName=object_name, Handle=f"{next(_handles):X}",
                             **{**base, **props})

    def Move(self, a, b):
        self.calls.append(("Move", a, b))

    def Rotate(self, base, ang):
        self.calls.append(("Rotate", base, ang))

    def ScaleEntity(self, base, f):
        self.calls.append(("Scale", base, f))

    def Copy(self):
        c = Ent(self._space, self.ObjectName, **{k: v for k, v in self.__dict__.items()
                                                 if k[0].isupper() and k not in ("ObjectName", "Handle")})
        self._space.items.append(c)
        return c

    def Delete(self):
        self._space.items.remove(self)

    def GetBoundingBox(self):
        pts = self.__dict__.get("_bbox")
        if pts is None:
            raise RuntimeError("no extents")
        return pts


class Space(Coll):
    def _add(self, name, bbox=None, **props):
        e = Ent(self, name, **props)
        e.__dict__["_bbox"] = bbox
        self.items.append(e)
        return e

    def AddLine(self, a, b):
        return self._add("AcDbLine", (tuple(min(x, y) for x, y in zip(a, b)), tuple(max(x, y) for x, y in zip(a, b))),
                         StartPoint=a, EndPoint=b, Length=math.dist(a, b))

    def AddLightWeightPolyline(self, flat):
        pts = list(zip(flat[::2], flat[1::2]))
        length = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        return self._add("AcDbPolyline", Coordinates=tuple(flat), Closed=False, Length=length, Area=0.0, Elevation=0.0)

    def Add3DPoly(self, flat):
        return self._add("AcDb3dPolyline", Coordinates=tuple(flat), Closed=False)

    def AddCircle(self, c, r):
        return self._add("AcDbCircle", Center=c, Radius=r, Circumference=2 * math.pi * r, Area=math.pi * r * r)

    def AddArc(self, c, r, a0, a1):
        return self._add("AcDbArc", Center=c, Radius=r, StartAngle=a0, EndAngle=a1, ArcLength=r * ((a1 - a0) % (2 * math.pi)))

    def AddText(self, s, p, h):
        return self._add("AcDbText", TextString=s, InsertionPoint=p, Height=h, Rotation=0.0)

    def AddMText(self, p, w, s):
        return self._add("AcDbMText", TextString=s, InsertionPoint=p, Width=w, Height=2.5)

    def AddPoint(self, p):
        return self._add("AcDbPoint", Coordinates=p)

    def AddDimAligned(self, a, b, loc):
        return self._add("AcDbAlignedDimension", Measurement=math.dist(a, b), TextOverride="")

    def AddDimRotated(self, a, b, loc, ang):
        return self._add("AcDbRotatedDimension", Measurement=abs((b[0] - a[0]) * math.cos(ang) + (b[1] - a[1]) * math.sin(ang)),
                         TextOverride="", rotation=ang)

    def AddHatch(self, ptype, name, assoc):
        h = self._add("AcDbHatch", PatternName=name, Area=0.0, PatternScale=1.0, PatternType=ptype)
        h.__dict__["AppendOuterLoop"] = lambda objs: h.calls.append(("outer", objs))
        h.__dict__["AppendInnerLoop"] = lambda objs: h.calls.append(("inner", objs))
        h.__dict__["Evaluate"] = lambda: h.calls.append(("evaluate",))
        return h

    def InsertBlock(self, p, name, xs, ys, zs, rot):
        atts = [Ent(self, "AcDbAttribute", TagString=t, TextString="") for t in ("SO_HIEU", "TEN_BV")]
        ref = self._add("AcDbBlockReference", Name=name, EffectiveName=name, InsertionPoint=p, Rotation=rot,
                        HasAttributes=True)
        ref.__dict__["GetAttributes"] = lambda: tuple(atts)
        return ref


class Doc:
    def __init__(self, name):
        self.Name, self.FullName = name, f"C:\\\\Drawings\\\\{name}"
        self.Layers = Layers([Layer("0")])
        self.Linetypes = Linetypes([Linetype("Continuous"), Linetype("ByLayer")])
        self.ModelSpace = Space()
        self.PaperSpace = Space()
        self.ActiveSpace = 1
        self.ActiveLayer = self.Layers.items[0]
        self.Blocks = Coll()
        self.vars = {"USERS5": "", "BACKGROUNDPLOT": 2}
        self.commands = []
        self.saved = []

    def HandleToObject(self, h):
        for e in self.ModelSpace.items + self.PaperSpace.items:
            if e.Handle == h:
                return e
        raise RuntimeError("bad handle")

    def SendCommand(self, cmd):
        self.commands.append(cmd)
        if cmd.startswith('(setvar "USERS5"'):
            self.vars["USERS5"] = "42"

    def GetVariable(self, n):
        return self.vars.get(n)

    def SetVariable(self, n, v):
        self.vars[n] = v

    def SaveAs(self, path, fmt=None):
        self.saved.append((path, fmt))

    def Save(self):
        self.saved.append((self.FullName, None))


class Docs(Coll):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def Add(self, template=None):
        d = Doc(f"Drawing{len(self.items) + 1}.dwg")
        self.items.append(d)
        self.app.ActiveDocument = d
        return d

    def Open(self, path, ro=False):
        d = Doc(path.split("\\\\")[-1])
        self.items.append(d)
        self.app.ActiveDocument = d
        return d


class App:
    Name = "AutoCAD"

    def __init__(self, version="24.3s (LMS Tech)"):
        self.Version = version
        self.Documents = Docs(self)
        self.ActiveDocument = None
        self.zoomed = False

    def ZoomExtents(self):
        self.zoomed = True


def connector(app):
    def connect(progid, start, visible):
        return app, progid or "AutoCAD.Application", False

    return connect


VARIANTS = (lambda values: tuple(values), lambda objs: list(objs))
