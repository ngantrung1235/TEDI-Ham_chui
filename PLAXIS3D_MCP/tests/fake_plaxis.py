"""A minimal in-memory stand-in for plxscripting's (s_i, g_i) used by the tests."""

from __future__ import annotations

from collections import defaultdict


class FakeProp:
    def __init__(self, value):
        self._property_name = "prop"
        self.value = value


class FakeObj:
    def __init__(self, g, plx_type, name):
        self.__dict__.update(_g=g, _plx_type=plx_type, _props={"Name": name}, calls=[])

    # PLAXIS properties
    def __getattr__(self, key):
        props = self.__dict__["_props"]
        if key in props:
            return FakeProp(props[key])
        raise AttributeError(key)

    def __setattr__(self, key, value):
        self._props[key] = value

    def __dir__(self):
        return list(self._props) + ["Identification"]

    def setproperties(self, *flat):
        pairs = dict(zip(flat[::2], flat[1::2]))
        bad = [k for k in pairs if k in self._g.rejected]
        if bad:
            raise RuntimeError(f"unknown property {bad}")
        self._props.update(pairs)

    def activate(self, phase):
        self.calls.append(("activate", phase.Name.value))

    def deactivate(self, phase):
        self.calls.append(("deactivate", phase.Name.value))

    def initializerectangular(self, *args):
        self._props["rect"] = args


class FakeGlobal:
    def __init__(self):
        self.__dict__.update(
            counters=defaultdict(int), registry={}, log=[], rejected=set(),
            Soillayers=[], Phases=[], SoilMat=[], PlateMat=[], Plates=[], Soils=[], SurfaceLoads=[],
        )
        self.SoilContour = self._new("SoilContour", name="SoilContour")
        self.Project = self._new("Project", name="Project")
        self.Phases.append(self._new("Phase", name="InitialPhase"))

    def __getattr__(self, key):
        reg = self.__dict__["registry"]
        if key in reg:
            return reg[key]
        raise AttributeError(key)

    def __setattr__(self, key, value):
        self.__dict__[key] = value

    def _new(self, plx_type, name=None):
        if name is None:
            self.counters[plx_type] += 1
            name = f"{plx_type}_{self.counters[plx_type]}"
        obj = FakeObj(self, plx_type, name)
        self.registry[name] = obj
        return obj

    # modes
    def gotosoil(self): self.log.append("gotosoil")
    def gotostructures(self): self.log.append("gotostructures")
    def gotomesh(self): self.log.append("gotomesh")
    def gotostages(self): self.log.append("gotostages")

    # soil
    def borehole(self, x, y):
        return self._new("Borehole")

    def soillayer(self, thickness):
        layer = self._new("Soillayer")
        layer._props["Soil"] = self._new("Soil")
        self.Soillayers.append(layer)
        return layer

    def setsoillayerlevel(self, borehole, index, z):
        self.log.append(("level", index, z))

    # materials
    def soilmat(self):
        m = self._new("SoilMat"); self.SoilMat.append(m); return m

    def platemat(self):
        m = self._new("PlateMat"); self.PlateMat.append(m); return m

    # structures
    def surface(self, *pts):
        s = self._new("Surface")
        s._props["points"] = pts
        return [self._new("Point") for _ in pts] + [s]

    def plate(self, srf):
        p = self._new("Plate"); p._props["surface"] = srf; self.Plates.append(p); return p

    def posinterface(self, srf):
        return self._new("PositiveInterface")

    def neginterface(self, srf):
        return self._new("NegativeInterface")

    def extrude(self, srf, vec):
        soil = self._new("Soil"); soil._props["extrusion"] = vec; self.Soils.append(soil)
        return [self._new("Volume"), soil]

    def surfload(self, *pts):
        load = self._new("SurfaceLoad"); load._props["points"] = pts; self.SurfaceLoads.append(load)
        return [self._new("Surface"), load]

    def delete(self, obj):
        self.log.append(("delete", obj.Name.value))

    def mesh(self, *args):
        self.log.append(("mesh",) + args)
        return "OK"

    # stages
    def phase(self, prev):
        ph = self._new("Phase"); ph._props["PreviousPhase"] = prev; self.Phases.append(ph); return ph

    def calculate(self):
        for ph in self.Phases:
            ph._props["CalculationResult"] = "OK"


class FakeServer:
    name = "PLAXIS 3D Input"
    major_version = 25
    minor_version = 1
    is_3d = True

    def __init__(self, g):
        self.g = g

    def new(self):
        return True

    def call_and_handle_command(self, cmd):
        self.g.log.append(("cmd", cmd))
        return "OK"


def factory():
    g = FakeGlobal()

    def make(host, port, password, timeout):
        return FakeServer(g), g

    return g, make
