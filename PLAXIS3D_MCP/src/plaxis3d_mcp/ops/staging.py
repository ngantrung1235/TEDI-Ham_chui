"""Mesh, staged construction phases and calculation."""

from __future__ import annotations

from typing import Any

from ..plx import get_by_name, list_group, name_of, set_properties, to_jsonable

CALC_TYPES = {
    "k0": "K0 procedure",
    "gravity": "Gravity loading",
    "plastic": "Plastic",
    "consolidation": "Consolidation",
    "safety": "Safety",
    "dynamic": "Dynamic",
}


def generate_mesh(sess, coarseness: float = 0.06, enhanced_refinements: bool = True) -> dict:
    """Relative element size factor: smaller = finer (0.06 ~ 'Medium')."""
    _, g_i = sess.input()
    g_i.gotomesh()
    try:
        result = g_i.mesh(coarseness, enhanced_refinements)
    except Exception:
        result = g_i.mesh(coarseness)
    return {"ok": True, "coarseness": coarseness, "result": to_jsonable(result)}


def _calc_type(value: str) -> str:
    return CALC_TYPES.get(value.lower().replace(" ", "").replace("procedure", "").replace("loading", ""), value)


def _phase_by_label(g_i: Any, label: str) -> Any:
    """Find a phase by PLAXIS name ('Phase_2', 'InitialPhase') or by Identification."""
    try:
        return get_by_name(g_i, label)
    except RuntimeError:
        pass
    for ph in list_group(g_i, "Phases"):
        try:
            if ph.Identification.value == label:
                return ph
        except Exception:
            continue
    raise RuntimeError(f"Phase '{label}' not found.")


def _resolve_stage_object(g_i: Any, name: str) -> list[Any]:
    """Objects keep their parent name in Staged construction; if the parent is not
    addressable, fall back to all intersected children ('Plate_1' -> 'Plate_1_1', ...)."""
    try:
        return [get_by_name(g_i, name)]
    except RuntimeError:
        pass
    children = []
    for group in ("Soils", "Plates", "Beams", "EmbeddedBeams", "Interfaces", "SurfaceLoads", "LineLoads", "PointLoads"):
        try:
            children += [o for o in list_group(g_i, group) if (name_of(o) or "").startswith(name + "_")]
        except RuntimeError:
            continue
    if not children:
        raise RuntimeError(f"Object '{name}' not found in Staged construction.")
    return children


def _toggle(g_i: Any, names: list[str], phase: Any, activate: bool) -> list[str]:
    warnings = []
    verb = "activate" if activate else "deactivate"
    for n in names:
        try:
            for obj in _resolve_stage_object(g_i, n):
                try:
                    getattr(obj, verb)(phase)
                except Exception:
                    getattr(g_i, verb)(obj, phase)
        except Exception as exc:
            warnings.append(f"{verb} {n}: {exc}")
    return warnings


def configure_phase(
    sess,
    phase: str,
    calc_type: str | None = None,
    activate: list[str] | None = None,
    deactivate: list[str] | None = None,
    settings: dict[str, Any] | None = None,
    identification: str | None = None,
) -> dict:
    _, g_i = sess.input()
    g_i.gotostages()
    ph = _phase_by_label(g_i, phase)
    props: dict[str, Any] = {}
    if identification:
        props["Identification"] = identification
    if calc_type:
        props["DeformCalcType"] = _calc_type(calc_type)
    props.update(settings or {})
    warnings = set_properties(ph, props)
    warnings += _toggle(g_i, activate or [], ph, True)
    warnings += _toggle(g_i, deactivate or [], ph, False)
    return {"phase": name_of(ph), "warnings": warnings}


def create_phase(
    sess,
    identification: str,
    previous: str = "InitialPhase",
    calc_type: str = "plastic",
    activate: list[str] | None = None,
    deactivate: list[str] | None = None,
    reset_displacements: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict:
    """Add a phase after ``previous`` and (de)activate objects by name."""
    _, g_i = sess.input()
    g_i.gotostages()
    prev = _phase_by_label(g_i, previous)
    ph = g_i.phase(prev)
    extra = dict(settings or {})
    if reset_displacements:
        extra.setdefault("Deform.ResetDisplacementsToZero", True)
    nested = {k: extra.pop(k) for k in list(extra) if "." in k}
    res = configure_phase(sess, name_of(ph), calc_type, activate, deactivate, extra, identification)
    for path, value in nested.items():
        owner, attr = path.rsplit(".", 1)
        try:
            res["warnings"] += set_properties(get_by_name(ph, owner), {attr: value})
        except Exception as exc:
            res["warnings"].append(f"{path}: {exc}")
    res["previous"] = name_of(prev)
    return res


def list_phases(sess) -> dict:
    _, g_i = sess.input()
    out = []
    for ph in list_group(g_i, "Phases"):
        row: dict[str, Any] = {"name": name_of(ph)}
        for key in ("Identification", "DeformCalcType", "ShouldCalculate", "CalculationResult", "LogInfo"):
            try:
                row[key] = to_jsonable(getattr(ph, key))
            except Exception:
                pass
        try:
            row["previous"] = name_of(ph.PreviousPhase.value)
        except Exception:
            pass
        out.append(row)
    return {"count": len(out), "phases": out}


def calculate(sess, phases: list[str] | None = None) -> dict:
    """Calculate. With ``phases`` only those are flagged; otherwise all flagged phases run."""
    _, g_i = sess.input()
    g_i.gotostages()
    if phases:
        wanted = {name_of(_phase_by_label(g_i, p)) for p in phases}
        for ph in list_group(g_i, "Phases"):
            try:
                ph.ShouldCalculate = name_of(ph) in wanted
            except Exception:
                pass
    g_i.calculate()
    status = list_phases(sess)
    failed = [p["name"] for p in status["phases"] if str(p.get("CalculationResult", "")).lower() in {"failed", "2"}]
    return {"ok": not failed, "failed_phases": failed, **status}
