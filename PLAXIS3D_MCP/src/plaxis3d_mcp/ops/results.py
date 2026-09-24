"""Result extraction from PLAXIS 3D Output."""

from __future__ import annotations

import math
from typing import Any

from ..plx import get_by_name, list_group, name_of

PLATE_FORCES = ["N1", "N2", "Q13", "Q23", "M11", "M22", "M12", "Utot"]


def _result_type(g_o: Any, path: str) -> Any:
    """'Soil.Uz' -> g_o.ResultTypes.Soil.Uz"""
    return get_by_name(g_o.ResultTypes, path)


def _output_phase(g_o: Any, label: str | None) -> Any:
    phases = list_group(g_o, "Phases")
    if label is None:
        return phases[-1]
    for ph in phases:
        if name_of(ph) == label:
            return ph
        try:
            if ph.Identification.value == label:
                return ph
        except Exception:
            continue
    raise RuntimeError(f"Phase '{label}' not found in Output (known: {[name_of(p) for p in phases]}).")


def _values(g_o: Any, obj: Any, phase: Any, rtype: Any, location: str) -> list[float]:
    args = ([obj] if obj is not None else []) + [phase, rtype, location]
    return [float(v) for v in g_o.getresults(*args)]


def _stats(vals: list[float], xyz: list[list[float]] | None) -> dict:
    finite = [(i, v) for i, v in enumerate(vals) if not math.isnan(v)]
    if not finite:
        return {"count": 0}
    i_min, v_min = min(finite, key=lambda t: t[1])
    i_max, v_max = max(finite, key=lambda t: t[1])
    i_abs, v_abs = max(finite, key=lambda t: abs(t[1]))
    out: dict[str, Any] = {"count": len(finite), "min": v_min, "max": v_max, "abs_max": v_abs}
    if xyz:
        out.update(at_min=xyz[i_min], at_max=xyz[i_max], at_abs_max=xyz[i_abs])
    return out


def get_results(
    sess,
    result_type: str,
    phase: str | None = None,
    object_name: str | None = None,
    location: str = "node",
    include_values: bool = False,
    max_values: int = 500,
) -> dict:
    """Statistics (min/max/|max| + coordinates) of one result quantity.

    ``result_type`` is a path under ResultTypes, e.g. 'Soil.Uz', 'Soil.Utot',
    'Plate.M11', 'Plate.Q13', 'EmbeddedBeam.N', 'Interface.SigN'.
    """
    _, g_o = sess.output()
    rtype = _result_type(g_o, result_type)
    ph = _output_phase(g_o, phase)
    obj = get_by_name(g_o, object_name) if object_name else None
    vals = _values(g_o, obj, ph, rtype, location)
    group = result_type.split(".")[0]
    xyz = None
    try:
        coords = [_values(g_o, obj, ph, _result_type(g_o, f"{group}.{c}"), location) for c in "XYZ"]
        xyz = [list(p) for p in zip(*coords)]
    except Exception:
        pass
    out = {"result_type": result_type, "phase": name_of(ph), "object": object_name, **_stats(vals, xyz)}
    if include_values:
        n = min(len(vals), max_values)
        out["values"] = [{"xyz": xyz[i] if xyz else None, "v": vals[i]} for i in range(n)]
        out["truncated"] = len(vals) > n
    return out


def get_result_at_point(sess, result_type: str, x: float, y: float, z: float, phase: str | None = None) -> dict:
    _, g_o = sess.output()
    ph = _output_phase(g_o, phase)
    value = g_o.getsingleresult(ph, _result_type(g_o, result_type), (x, y, z))
    return {"result_type": result_type, "phase": name_of(ph), "point": [x, y, z], "value": value}


def plate_force_envelope(
    sess, phase: str | None = None, plates: list[str] | None = None, quantities: list[str] | None = None
) -> dict:
    """Min/max of plate forces per plate (kN/m, kNm/m). Sign convention: PLAXIS local axes."""
    _, g_o = sess.output()
    ph = _output_phase(g_o, phase)
    objs = [get_by_name(g_o, p) for p in plates] if plates else list_group(g_o, "Plates")
    table = {}
    for obj in objs:
        row = {}
        for q in quantities or PLATE_FORCES:
            try:
                row[q] = _stats(_values(g_o, obj, ph, _result_type(g_o, f"Plate.{q}"), "node"), None)
            except Exception as exc:
                row[q] = {"error": str(exc)}
        table[name_of(obj)] = row
    return {"phase": name_of(ph), "plates": table}
