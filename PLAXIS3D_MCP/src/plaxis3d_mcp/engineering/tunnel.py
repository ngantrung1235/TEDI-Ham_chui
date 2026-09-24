"""Parametric circular tunnel with step-by-step excavation (NATM / shield-type sequence).

The tunnel is built from primitives rather than the Tunnel Designer so that every
excavation round is a separate, named object and staged construction can be
scripted without picking clusters in the GUI:

* core_i   - soil volume of round i (polygon with ``n_facets`` sides, extruded
             over ``round_length`` along +Y);
* lining_i - ``n_facets`` plates on the lining mid-surface of round i;
* face_i   - optional face-support pressure at the face after round i.

Phase k (k = 1..N): excavate core_k (deactivate, set dry), apply the face
pressure at face k, install the lining of rounds <= k - unsupported_rounds.
A final phase closes the remaining lining and removes the face pressure.

Axis along +Y from ``y_start``; the cross-section lies in the XZ plane.
Limitations: a single material is used for the core volumes (it only affects
the initial stresses before excavation); ground relaxation ahead of the lining
(volume loss) is represented only by the unsupported length.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from ..ops import geometry, materials, staging, water
from .culvert import oriented


@dataclass
class TunnelParams:
    center_x: float = 0.0
    center_z: float = -15.0
    y_start: float = 0.0
    radius: float = 5.0  # lining mid-surface radius (m)
    rounds: int = 10
    round_length: float = 2.0  # m, excavation step
    n_facets: int = 16
    lining_grade: str = "B40"
    lining_thickness: float = 0.35
    lining_material: str | None = None  # existing PlateMat overrides grade/thickness
    core_material: str | None = None  # SoilMat for the core volumes (surrounding layer)
    unsupported_rounds: int = 1  # rounds between face and last installed lining ring
    face_pressure: float = 0.0  # kPa, 0 = no face support
    interfaces: bool = False
    dry_core: bool = True
    auto_stage: bool = True
    generate_mesh: bool = True
    mesh_coarseness: float = 0.06


def ring(p: TunnelParams, y: float) -> list[tuple[float, float, float]]:
    """Polygon of the lining mid-surface at station y (counter-clockwise seen from +Y)."""
    pts = []
    for j in range(p.n_facets):
        t = 2 * math.pi * j / p.n_facets
        pts.append((p.center_x + p.radius * math.cos(t), y, p.center_z + p.radius * math.sin(t)))
    return pts


def build_tunnel(sess, p: TunnelParams) -> dict[str, Any]:
    if p.rounds < 1 or p.round_length <= 0 or p.radius <= 0 or p.n_facets < 8:
        raise RuntimeError("rounds >= 1, round_length > 0, radius > 0 and n_facets >= 8 are required.")
    if not 0 <= p.unsupported_rounds <= p.rounds:
        raise RuntimeError("unsupported_rounds must be between 0 and rounds.")
    warnings: list[str] = []
    out: dict[str, Any] = {"params": asdict(p)}

    lining_mat = p.lining_material
    if not lining_mat:
        r = materials.create_concrete_plate_material(sess, p.lining_grade, p.lining_thickness, "Tunnel_lining")
        lining_mat, warnings = r["material"], warnings + r["warnings"]
    if not p.core_material:
        warnings.append(
            "core_material not given: assign the surrounding layer's material to the core volumes "
            "before meshing (they carry the initial stresses)."
        )

    cores, linings, faces = [], [], []
    for i in range(p.rounds):
        y0 = p.y_start + i * p.round_length
        y1 = y0 + p.round_length
        res = geometry.create_soil_volume(sess, ring(p, y0), (0.0, p.round_length, 0.0), p.core_material)
        cores.append(res["soil"])
        warnings += res["warnings"]

        a0, a1 = ring(p, y0), ring(p, y1)
        plates = []
        for j in range(p.n_facets):
            k = (j + 1) % p.n_facets
            t = 2 * math.pi * (j + 0.5) / p.n_facets
            facet = oriented([a0[j], a0[k], a1[k], a1[j]], (math.cos(t), 0.0, math.sin(t)))  # + side = soil
            r = geometry.create_plate(sess, facet, lining_mat, "positive" if p.interfaces else "none")
            plates.append(r["plate"])
            plates += [i for i in r["interfaces"] if i]
            warnings += r["warnings"]
        linings.append(plates)

        if p.face_pressure > 0:
            # support pressure on the ground ahead of the face (+Y direction)
            r = geometry.create_surface_load(sess, ring(p, y1), sigy=p.face_pressure)
            faces.append(r["load"])
            warnings += r["warnings"]
    out.update(cores=cores, lining_rounds=linings, face_loads=faces, lining_material=lining_mat)

    if p.generate_mesh:
        staging.generate_mesh(sess, p.mesh_coarseness)
        if p.auto_stage:
            out["phases"] = _stage(sess, p, cores, linings, faces, warnings)
    out["warnings"] = warnings
    return out


def _stage(sess, p: TunnelParams, cores, linings, faces, warnings) -> list[dict]:
    r = staging.configure_phase(sess, "InitialPhase", calc_type="k0")
    warnings += r["warnings"]
    phases = [{"name": r["phase"], "identification": "Initial (K0)"}]
    previous = "InitialPhase"
    installed = 0
    for k in range(1, p.rounds + 1):
        activate, deactivate = [], [cores[k - 1]]
        if faces:
            activate.append(faces[k - 1])
            if k > 1:
                deactivate.append(faces[k - 2])
        while installed < k - p.unsupported_rounds:
            activate += linings[installed]
            installed += 1
        ident = f"Excavation round {k:02d}"
        r = staging.create_phase(sess, ident, previous, "plastic", activate, deactivate)
        warnings += r["warnings"]
        if p.dry_core:
            warnings += water.set_soil_water_condition(sess, [cores[k - 1]], r["phase"], "Dry")["warnings"]
        phases.append({"name": r["phase"], "identification": ident})
        previous = r["phase"]
    remaining = [x for ring_ in linings[installed:] for x in ring_]
    if remaining or faces:
        r = staging.create_phase(
            sess, "Lining closure", previous, "plastic", remaining, [faces[-1]] if faces else []
        )
        warnings += r["warnings"]
        phases.append({"name": r["phase"], "identification": "Lining closure"})
    return phases
