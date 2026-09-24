"""Project, mode and generic object operations."""

from __future__ import annotations

import contextlib
import io
from typing import Any

from ..plx import get_by_name, list_group, name_of, plx_type, set_properties, to_jsonable
from ..session import PlaxisSession

MODES = {
    "soil": "gotosoil",
    "structures": "gotostructures",
    "mesh": "gotomesh",
    "flow": "gotoflow",
    "stages": "gotostages",
}


def new_project(sess: PlaxisSession, title: str | None = None) -> dict:
    s_i, g_i = sess.input()
    s_i.new()
    warnings = set_properties(g_i.Project, {"Title": title}) if title else []
    return {"ok": True, "title": title, "warnings": warnings}


def open_project(sess: PlaxisSession, path: str) -> dict:
    s_i, _ = sess.input()
    return {"ok": bool(s_i.open(path)), "path": path}


def save_project(sess: PlaxisSession, path: str | None = None) -> dict:
    _, g_i = sess.input()
    g_i.save(path) if path else g_i.save()
    return {"ok": True, "path": path}


def goto_mode(sess: PlaxisSession, mode: str) -> dict:
    _, g_i = sess.input()
    try:
        cmd = MODES[mode.lower()]
    except KeyError as exc:
        raise RuntimeError(f"Unknown mode '{mode}'. Use one of {sorted(MODES)}.") from exc
    getattr(g_i, cmd)()
    return {"ok": True, "mode": mode.lower()}


def list_objects(sess: PlaxisSession, group: str, output: bool = False) -> dict:
    _, g = sess.output() if output else sess.input()
    objs = list_group(g, group)
    return {"group": group, "count": len(objs), "objects": [{"name": name_of(o), "type": plx_type(o)} for o in objs]}


def get_object(sess: PlaxisSession, name: str, properties: list[str] | None = None, phase: str | None = None) -> dict:
    """Read properties of an object. Staged properties are read for ``phase``."""
    _, g_i = sess.input()
    obj = get_by_name(g_i, name)
    ph = get_by_name(g_i, phase) if phase else None
    if properties is None:
        try:
            properties = sorted(k for k in dir(obj) if k[:1].isupper())
        except Exception:
            properties = []
    values: dict[str, Any] = {}
    for p in properties:
        try:
            prop = getattr(obj, p)
            if callable(prop) and not hasattr(prop, "value"):
                continue  # method, not a property
            values[p] = to_jsonable(prop[ph] if ph is not None else prop, depth=1)
        except Exception as exc:
            values[p] = f"<error: {exc}>"
    return {"name": name, "type": plx_type(obj), "phase": phase, "properties": values}


def set_object_properties(sess: PlaxisSession, name: str, properties: dict[str, Any], phase: str | None = None) -> dict:
    """Set properties; with ``phase`` they are set as staged values (``obj.prop[phase] = value``)."""
    _, g_i = sess.input()
    obj = get_by_name(g_i, name)
    resolved = {k: _resolve_value(g_i, v) for k, v in properties.items()}
    if phase is None:
        warnings = set_properties(obj, resolved)
    else:
        ph = get_by_name(g_i, phase)
        warnings = []
        for k, v in resolved.items():
            try:
                getattr(obj, k)[ph] = v
            except Exception as exc:
                warnings.append(f"{name}.{k} @ {phase} = {v!r} rejected: {exc}")
    return {"ok": not warnings, "name": name, "warnings": warnings}


def _resolve_value(g_i: Any, value: Any) -> Any:
    """Strings like '@PlateMat_1' refer to PLAXIS objects (materials, phases...)."""
    if isinstance(value, str) and value.startswith("@"):
        return get_by_name(g_i, value[1:])
    return value


def run_command(sess: PlaxisSession, command: str, output: bool = False) -> dict:
    """Run a raw PLAXIS command-line command (same syntax as the command bar)."""
    s, _ = sess.output() if output else sess.input()
    result = s.call_and_handle_command(command)
    return {"command": command, "result": to_jsonable(result)}


def run_python(sess: PlaxisSession, code: str) -> dict:
    if not sess.settings.allow_python:
        raise RuntimeError("run_python is disabled. Set PLAXIS_MCP_ALLOW_PYTHON=1 in the MCP server env to enable it.")
    s_i, g_i = sess.input()
    ns: dict[str, Any] = {"s_i": s_i, "g_i": g_i, "s_o": sess.s_o, "g_o": sess.g_o, "session": sess}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<plaxis_mcp>", "exec"), ns)
    return {"stdout": buf.getvalue()[-20000:], "result": to_jsonable(ns.get("result"))}
