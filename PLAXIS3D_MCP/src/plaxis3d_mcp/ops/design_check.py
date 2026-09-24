"""Combine PLAXIS plate forces (TCVN 11823-3) and check RC sections (TCVN 11823-5)."""

from __future__ import annotations

import math
from typing import Any

from ..engineering.design import Section, check_point, combine
from ..plx import get_by_name, list_group, name_of
from .export import write_table
from .results import _output_phase, _result_type, _values

DIRECTIONS = {1: ("M11", "N1", "Q13"), 2: ("M22", "N2", "Q23")}


def _plate_arrays(g_o: Any, plate: Any, phase: Any, quantities: list[str]) -> dict[tuple, dict[str, float]]:
    """{rounded (x, y, z): {quantity: value}} so phases can be matched node by node."""
    xyz = [_values(g_o, plate, phase, _result_type(g_o, f"Plate.{c}"), "node") for c in "XYZ"]
    vals = {q: _values(g_o, plate, phase, _result_type(g_o, f"Plate.{q}"), "node") for q in quantities}
    out: dict[tuple, dict[str, float]] = {}
    for i, p in enumerate(zip(*xyz)):
        key = tuple(round(c, 3) for c in p)
        row = {q: v[i] for q, v in vals.items()}
        prev = out.get(key)
        # nodes shared by several elements: keep the governing (largest |M|) value
        if prev is None or abs(row[quantities[0]]) > abs(prev[quantities[0]]):
            out[key] = row
    return out


def design_check_plates(
    sess,
    permanent_phase: str,
    sections: dict[str, dict[str, Any]],
    live_phase: str | None = None,
    gamma_p_max: float = 1.35,
    gamma_p_min: float = 0.90,
    gamma_ll: float = 1.75,
    eta: float = 1.0,
    fill_depth: float | None = None,
    path: str | None = None,
) -> dict:
    """Strength I + Service I checks of plates.

    ``sections``: {output plate name or '*': {h, as_pos, as_neg, cover, fc, fy, spacing,
    gamma_e, member ('top_slab'|'bottom_slab'|'wall'), 'dir2': {overrides for direction 2}}}.
    Axial forces from PLAXIS are tension-positive; they are converted to compression-positive.
    """
    _, g_o = sess.output()
    ph_p = _output_phase(g_o, permanent_phase)
    ph_l = _output_phase(g_o, live_phase) if live_phase else None
    plates = [get_by_name(g_o, n) for n in sections if n != "*"] or list_group(g_o, "Plates")
    if "*" in sections:
        named = {name_of(p) for p in plates}
        plates += [p for p in list_group(g_o, "Plates") if name_of(p) not in named]

    summary, rows = {}, []
    for plate in plates:
        pname = name_of(plate)
        spec = dict(sections.get(pname) or sections.get("*") or {})
        if not spec:
            continue
        member = spec.pop("member", "wall")
        dir2 = spec.pop("dir2", {})
        result: dict[str, Any] = {}
        for d, (qm, qn, qv) in DIRECTIONS.items():
            sec = Section(**({**spec, **dir2} if d == 2 else spec))
            perm = _plate_arrays(g_o, plate, ph_p, [qm, qn, qv])
            total = _plate_arrays(g_o, plate, ph_l, [qm, qn, qv]) if ph_l is not None else perm
            worst = {"flexure": 0.0, "shear": 0.0, "crack": 0.0}
            where: dict[str, Any] = {}
            for key, p in perm.items():
                t = total.get(key, p)
                ms = combine(p[qm], t[qm], 1.0, 1.0)
                for gp in (gamma_p_max, gamma_p_min):
                    mu = combine(p[qm], t[qm], gp, gamma_ll, eta)
                    pu = -combine(p[qn], t[qn], gp, gamma_ll, eta)
                    vu = combine(p[qv], t[qv], gp, gamma_ll, eta)
                    chk = check_point(sec, mu, pu, vu, ms, member, fill_depth)
                    for k in worst:
                        if chk[k] > worst[k]:
                            worst[k] = chk[k]
                            where[k] = {"xyz": key, "Mu": round(mu, 1), "Pu": round(pu, 1), "Vu": round(vu, 1),
                                        "Ms": round(ms, 1), **{x: chk[x] for x in ("phiMn", "phiVc", "s_max")}}
                    rows.append([pname, d, *key, gp, round(mu, 2), round(pu, 2), round(vu, 2), round(ms, 2),
                                 chk["flexure"], chk["shear"], chk["crack"]])
            result[f"dir{d}"] = {
                "utilisation": worst,
                "ok": all(v <= 1.0 for v in worst.values() if not math.isinf(v)) and not any(
                    math.isinf(v) for v in worst.values()),
                "governing": where,
            }
        summary[pname] = {"member": member, **result}
    out: dict[str, Any] = {
        "permanent_phase": name_of(ph_p),
        "live_phase": name_of(ph_l) if ph_l is not None else None,
        "factors": {"gamma_p": [gamma_p_max, gamma_p_min], "gamma_LL": gamma_ll, "eta": eta},
        "plates": summary,
        "all_ok": all(v[k]["ok"] for v in summary.values() for k in ("dir1", "dir2")),
    }
    if path:
        header = ["plate", "dir", "X", "Y", "Z", "gamma_p", "Mu", "Pu", "Vu", "Ms", "U_flex", "U_shear", "U_crack"]
        out["path"] = write_table(path, header, rows)
    return out
