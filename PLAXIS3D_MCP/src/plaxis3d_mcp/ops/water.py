"""Groundwater: water levels, phase pore-pressure settings, cluster water conditions."""

from __future__ import annotations

from typing import Any, Sequence

from ..plx import get_by_name, name_of, pick, set_properties
from .staging import _phase_by_label, _resolve_stage_object

PORE_PRESSURE_TYPES = {
    "phreatic": "Phreatic",
    "steady": "Steady state groundwater flow",
    "previous": "Use pressures from previous phase",
}
WATER_CONDITIONS = ("Dry", "Head", "Interpolate", "User-defined", "Global level", "Cluster phreatic level")


def set_borehole_head(sess, borehole: str, head: float) -> dict:
    _, g_i = sess.input()
    g_i.gotosoil()
    return {"borehole": borehole, "warnings": set_properties(get_by_name(g_i, borehole), {"Head": head})}


def create_water_level(sess, points: Sequence[Sequence[float]]) -> dict:
    """User water level through >= 3 points (Flow conditions mode)."""
    _, g_i = sess.input()
    g_i.gotoflow()
    res = g_i.waterlevel(*[tuple(float(c) for c in p) for p in points])
    wl = pick(res, "UserWaterLevel", required=False)
    return {"water_level": name_of(wl) if wl is not None else None}


def set_phase_water(
    sess, phase: str, pore_pressure: str | None = None, global_water_level: str | None = None
) -> dict:
    """Pore pressure calculation type and global water level of a phase."""
    _, g_i = sess.input()
    g_i.gotoflow()
    ph = _phase_by_label(g_i, phase)
    warnings: list[str] = []
    if pore_pressure:
        value = PORE_PRESSURE_TYPES.get(pore_pressure.lower(), pore_pressure)
        warnings += set_properties(ph, {"PorePresCalcType": value})
    if global_water_level:
        level = get_by_name(g_i, global_water_level)
        def as_property():
            rejected = set_properties(ph, {"GlobalWaterLevel": level})
            if rejected:
                raise RuntimeError(rejected[0])

        attempts = (
            lambda: g_i.setglobalwaterlevel(level, ph),
            lambda: g_i.setglobalwaterlevel(ph, level),
            as_property,
        )
        last: Exception | None = None
        for attempt in attempts:
            try:
                attempt()
                break
            except Exception as exc:
                last = exc
        else:
            warnings.append(f"Could not set global water level {global_water_level} for {phase}: {last}")
    return {"phase": name_of(ph), "warnings": warnings}


def set_soil_water_condition(
    sess, soils: list[str], phase: str, condition: str = "Dry", head: float | None = None
) -> dict:
    """Water condition of soil clusters in a phase (e.g. 'Dry' for excavated tunnel cores,
    'Head' with a head value for a dewatered pit)."""
    _, g_i = sess.input()
    g_i.gotoflow()
    ph = _phase_by_label(g_i, phase)
    warnings: list[str] = []
    for name in soils:
        try:
            objs = _resolve_stage_object(g_i, name)
        except RuntimeError as exc:
            warnings.append(str(exc))
            continue
        for obj in objs:
            values: dict[str, Any] = {"Conditions": condition}
            if head is not None:
                values["h"] = head
            for key, value in values.items():
                try:
                    getattr(obj.WaterConditions, key)[ph] = value
                except Exception as exc:
                    warnings.append(f"{name_of(obj)}.WaterConditions.{key} @ {phase}: {exc}")
    return {"phase": name_of(ph), "condition": condition, "warnings": warnings}
