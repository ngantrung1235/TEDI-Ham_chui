"""Material creation and editing."""

from __future__ import annotations

from typing import Any

from ..engineering.presets import concrete_plate_props, soil_props
from ..plx import get_by_name, list_group, material_name_key, name_of, plx_type, set_properties, to_jsonable

MATERIAL_COMMANDS = {
    "soil": "soilmat",
    "plate": "platemat",
    "beam": "beammat",
    "embeddedbeam": "embeddedbeammat",
    "anchor": "anchormat",
    "geogrid": "geogridmat",
}
MATERIAL_GROUPS = ["SoilMat", "PlateMat", "BeamMat", "EmbeddedBeamMat", "AnchorMat", "GeogridMat"]


def create_material(sess, kind: str, properties: dict[str, Any]) -> dict:
    """Create a material. Give the name under 'Identification' (or 'name')."""
    _, g_i = sess.input()
    try:
        cmd = MATERIAL_COMMANDS[kind.lower()]
    except KeyError as exc:
        raise RuntimeError(f"Unknown material kind '{kind}'. Use one of {sorted(MATERIAL_COMMANDS)}.") from exc
    mat = getattr(g_i, cmd)()
    props = dict(properties)
    label = props.pop("name", None) or props.pop("Identification", None) or props.pop("MaterialName", None)
    if label:
        props = {material_name_key(mat): label, **props}
    warnings = set_properties(mat, props)
    return {"material": name_of(mat), "label": label, "kind": kind, "warnings": warnings}


def create_concrete_plate_material(sess, grade: str, thickness: float, name: str | None = None) -> dict:
    return create_material(sess, "plate", concrete_plate_props(grade, thickness, name))


def create_soil_material_from_preset(sess, preset: str, name: str | None = None, overrides: dict | None = None) -> dict:
    return create_material(sess, "soil", soil_props(preset, name, overrides))


def list_materials(sess) -> dict:
    _, g_i = sess.input()
    out = []
    for group in MATERIAL_GROUPS:
        try:
            mats = list_group(g_i, group)
        except RuntimeError:
            continue
        for m in mats:
            label = None
            for key in ("Identification", "MaterialName"):
                try:
                    label = to_jsonable(getattr(m, key))
                    break
                except Exception:
                    continue
            out.append({"name": name_of(m), "label": label, "type": plx_type(m)})
    return {"count": len(out), "materials": out}


def set_material_properties(sess, material: str, properties: dict[str, Any]) -> dict:
    _, g_i = sess.input()
    mat = get_by_name(g_i, material)
    return {"material": material, "warnings": set_properties(mat, properties)}
