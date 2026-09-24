"""Low-level helpers around plxscripting proxy objects.

Everything here uses duck typing (``_plx_type``, ``.value``, ``Name``) so the
same code runs against the real plxscripting proxies and the fake objects used
in the unit tests.
"""

from __future__ import annotations

from typing import Any, Iterable

PRIMITIVES = (str, int, float, bool, type(None))


def plx_type(obj: Any) -> str | None:
    """PLAXIS type name of a proxy object (e.g. 'Plate', 'Surface', 'Soil')."""
    t = getattr(obj, "_plx_type", None)
    if t is None:
        return None
    # staged-construction proxies are prefixed, e.g. 'staged.Plate'
    return t[len("staged."):] if t.startswith("staged.") else t


def is_property(obj: Any) -> bool:
    """True for PlxProxyObjectProperty-like values (they expose ``.value``)."""
    return "_property_name" in getattr(obj, "__dict__", {})


def name_of(obj: Any) -> str | None:
    try:
        n = obj.Name
        return n.value if hasattr(n, "value") else str(n)
    except Exception:
        return None


def to_jsonable(obj: Any, depth: int = 2) -> Any:
    """Convert proxies/values returned by PLAXIS into JSON friendly data."""
    if isinstance(obj, PRIMITIVES):
        return obj
    if is_property(obj):
        try:
            return to_jsonable(obj.value, depth)
        except Exception as exc:  # property that cannot be read in this mode
            return f"<unreadable: {exc}>"
    if plx_type(obj) is not None and not _is_listable(obj):
        return {"name": name_of(obj), "type": plx_type(obj)}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v, depth - 1) for k, v in obj.items()}
    if depth <= 0:
        return repr(obj)
    try:
        return [to_jsonable(x, depth - 1) for x in obj]
    except TypeError:
        return repr(obj)


def _is_listable(obj: Any) -> bool:
    return hasattr(obj, "__iter__") and hasattr(obj, "__len__") and not isinstance(obj, (str, bytes))


def flatten(result: Any) -> list[Any]:
    """PLAXIS commands return one object or (nested) lists of created objects."""
    if result is None:
        return []
    if plx_type(result) is not None and not _is_listable(result):
        return [result]
    if isinstance(result, (list, tuple)) or _is_listable(result):
        out: list[Any] = []
        for item in result:
            out.extend(flatten(item))
        return out
    return [result]


def pick(result: Any, type_name: str, required: bool = True) -> Any:
    """Pick the first object of ``type_name`` from a command result."""
    for obj in flatten(result):
        if plx_type(obj) == type_name:
            return obj
    if required:
        found = [plx_type(o) for o in flatten(result)]
        raise RuntimeError(f"Command did not return a '{type_name}' object (got {found}).")
    return None


def get_by_name(g: Any, name: str) -> Any:
    """Resolve 'Plate_1', 'Phase_2', 'InitialPhase', 'Plate_1.Material' ... on g_i/g_o."""
    obj = g
    for part in name.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError as exc:
            raise RuntimeError(f"PLAXIS object '{name}' not found (failed at '{part}').") from exc
    return obj


def material_name_key(mat: Any) -> str:
    """CONNECT Edition V20+ uses 'Identification'; older versions 'MaterialName'."""
    try:
        attrs = dir(mat)
    except Exception:
        attrs = []
    return "MaterialName" if "MaterialName" in attrs and "Identification" not in attrs else "Identification"


def set_properties(obj: Any, props: dict[str, Any]) -> list[str]:
    """Set properties through PLAXIS' own ``setproperties`` command.

    A batch call is tried first (it respects dependencies such as SoilModel
    before Eref); if PLAXIS rejects it, each property is set separately so one
    wrong name does not lose the rest. Returns warnings for rejected keys.
    Plain ``setattr`` is avoided because plxscripting silently creates a
    Python attribute when the PLAXIS property does not exist.
    """
    if not props:
        return []
    flat: list[Any] = []
    for k, v in props.items():
        flat += [k, v]
    try:
        obj.setproperties(*flat)
        return []
    except Exception:
        pass
    warnings = []
    for k, v in props.items():
        try:
            obj.setproperties(k, v)
        except Exception as exc:
            warnings.append(f"{name_of(obj) or plx_type(obj)}.{k} = {v!r} rejected: {exc}")
    return warnings


def list_group(g: Any, group: str) -> list[Any]:
    try:
        return list(getattr(g, group))
    except AttributeError as exc:
        raise RuntimeError(f"Group '{group}' does not exist in this PLAXIS mode.") from exc


def names(objs: Iterable[Any]) -> list[str | None]:
    return [name_of(o) for o in objs]
