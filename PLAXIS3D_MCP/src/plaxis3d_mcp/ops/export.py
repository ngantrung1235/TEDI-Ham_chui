"""Result tables, profiles, histories and plot images from PLAXIS 3D Output."""

from __future__ import annotations

import csv
import os
from typing import Any, Sequence

from ..plx import get_by_name, list_group, name_of, set_properties
from .results import _output_phase, _result_type, _values


def write_table(path: str, header: list[str], rows: list[list[Any]]) -> str:
    """CSV (UTF-8 with BOM so Excel shows Vietnamese correctly) or XLSX by extension."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    if path.lower().endswith(".xlsx"):
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("XLSX export needs openpyxl (pip install openpyxl); use .csv instead.") from exc
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(header)
        for r in rows:
            ws.append(r)
        wb.save(path)
    else:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
    return os.path.abspath(path)


def export_results(
    sess,
    result_types: list[str],
    path: str,
    phase: str | None = None,
    object_name: str | None = None,
    location: str = "node",
) -> dict:
    """Export X, Y, Z and several quantities of one result group ('Soil.Ux', 'Soil.Uz'...)."""
    _, g_o = sess.output()
    groups = {rt.split(".")[0] for rt in result_types}
    if len(groups) != 1:
        raise RuntimeError("All result_types must belong to the same group (e.g. all 'Plate.*').")
    group = groups.pop()
    ph = _output_phase(g_o, phase)
    obj = get_by_name(g_o, object_name) if object_name else None
    cols = [f"{group}.{c}" for c in "XYZ"] + list(result_types)
    data = [_values(g_o, obj, ph, _result_type(g_o, c), location) for c in cols]
    n = min(len(d) for d in data)
    rows = [[d[i] for d in data] for i in range(n)]
    out = write_table(path, ["X", "Y", "Z"] + list(result_types), rows)
    return {"path": out, "rows": n, "phase": name_of(ph)}


def _single(g_o: Any, ph: Any, rtype: Any, point: Sequence[float]) -> float | None:
    v = g_o.getsingleresult(ph, rtype, tuple(point))
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # 'not found' outside the mesh


def results_along_line(
    sess,
    p1: list[float],
    p2: list[float],
    result_types: list[str],
    n_points: int = 51,
    phase: str | None = None,
    path: str | None = None,
) -> dict:
    """Sample results on a straight line (settlement trough, profile under a footing...)."""
    _, g_o = sess.output()
    ph = _output_phase(g_o, phase)
    rtypes = [_result_type(g_o, rt) for rt in result_types]
    n = max(2, n_points)
    rows = []
    length = sum((b - a) ** 2 for a, b in zip(p1, p2)) ** 0.5
    for i in range(n):
        t = i / (n - 1)
        pt = [a + t * (b - a) for a, b in zip(p1, p2)]
        rows.append([round(t * length, 4)] + pt + [_single(g_o, ph, rt, pt) for rt in rtypes])
    header = ["s", "X", "Y", "Z"] + list(result_types)
    out: dict[str, Any] = {"phase": name_of(ph), "header": header, "rows": rows}
    if path:
        out["path"] = write_table(path, header, rows)
    return out


def results_history(
    sess, point: list[float], result_types: list[str], phases: list[str] | None = None, path: str | None = None
) -> dict:
    """One point through all (or selected) phases - e.g. settlement vs construction stage."""
    _, g_o = sess.output()
    phs = [_output_phase(g_o, p) for p in phases] if phases else list_group(g_o, "Phases")
    rtypes = [_result_type(g_o, rt) for rt in result_types]
    rows = []
    for ph in phs:
        label = name_of(ph)
        try:
            label = f"{label} ({ph.Identification.value})"
        except Exception:
            pass
        rows.append([label] + [_single(g_o, ph, rt, point) for rt in rtypes])
    header = ["phase"] + list(result_types)
    out: dict[str, Any] = {"point": point, "header": header, "rows": rows}
    if path:
        out["path"] = write_table(path, header, rows)
    return out


def export_plot_image(
    sess,
    path: str,
    result_type: str | None = None,
    phase: str | None = None,
    width: int = 1600,
    height: int = 1000,
) -> tuple[dict, bytes | None]:
    """Export the active Output plot to PNG (optionally switching result type / phase first)."""
    s_o, g_o = sess.output()
    warnings: list[str] = []
    plot = list_group(g_o, "Plots")[-1]
    if phase:
        warnings += set_properties(plot, {"Phase": _output_phase(g_o, phase)})
    if result_type:
        warnings += set_properties(plot, {"ResultType": _result_type(g_o, result_type)})
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    result, last = None, None
    for attempt in (
        lambda: plot.export(path, width, height),
        lambda: plot.export(path),
        lambda: s_o.call_and_handle_command(f'export {name_of(plot)} "{path}" {width} {height}'),
    ):
        try:
            result = attempt()
            last = None
            break
        except Exception as exc:
            last = exc
    if last is not None:
        raise RuntimeError(f"Plot export failed: {last}")
    data = _image_bytes(result)
    if data is None and os.path.exists(path):
        with open(path, "rb") as fh:
            data = fh.read()
    elif data is not None and not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(data)
    return {"path": path, "plot": name_of(plot), "warnings": warnings, "has_image": data is not None}, data


def _image_bytes(result: Any) -> bytes | None:
    """plxscripting may return an image wrapper; with Pillow ``.bytes`` is raw pixels, so re-encode."""
    if result is None or isinstance(result, (str, bool)):
        return None
    img = getattr(result, "_image", None)
    if img is not None:
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    raw = getattr(result, "bytes", None)
    return raw if isinstance(raw, (bytes, bytearray)) else None
