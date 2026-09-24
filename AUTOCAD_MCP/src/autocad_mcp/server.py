"""MCP server linking Claude Code with AutoCAD (any release) or DXF files."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from dataclasses import fields
from typing import Any, Callable

import anyio

try:  # mcp >= 2
    from mcp.server.mcpserver import Image
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp import Image
    from mcp.server.fastmcp.exceptions import ToolError

from .backends.base import Backend
from .backends.com import ComBackend
from .backends.dxf import DxfBackend
from .com_worker import ComWorker
from .engineering import drawings
from .versions import RELEASES, SAVE_FORMATS

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("autocad_mcp")

INSTRUCTIONS = """\
Drives AutoCAD through COM (every release 2000-2026, Civil 3D and AutoCAD-based verticals,
BricsCAD/ZWCAD/GstarCAD) or, without AutoCAD, reads/writes DXF files headlessly (ezdxf).
Start with cad_connect (backend auto|com|dxf). Units are drawing units (normally mm);
angles in degrees. Entities are addressed by handle. Common props: layer, color (ACI 1-255,
256 = ByLayer), linetype, lineweight. For anything without a dedicated tool use cad_command
(command line) or cad_lisp (AutoLISP, COM only). Verify drawings with preview_image.
"""

mcp = _Server("autocad", instructions=INSTRUCTIONS)


class State:
    def __init__(self):
        self.worker = ComWorker(init_com=sys.platform == "win32")
        self.backend: Backend | None = None
        self.com_factory: Callable[[], ComBackend] = ComBackend
        self.dxf_factory: Callable[[], DxfBackend] = DxfBackend

    def be(self) -> Backend:
        if self.backend is None:
            self.connect("auto")
        assert self.backend is not None
        return self.backend

    def com(self) -> ComBackend:
        be = self.be()
        if not isinstance(be, ComBackend):
            raise RuntimeError("This tool needs a live AutoCAD (cad_connect backend='com').")
        return be

    def connect(self, backend: str = "auto", progid: str | None = None, start: bool = True) -> dict:
        backend = (backend or os.environ.get("AUTOCAD_BACKEND") or "auto").lower()
        progid = progid or os.environ.get("AUTOCAD_PROGID") or None
        errors = []
        if backend in ("auto", "com"):
            try:
                be = self.com_factory()
                info = be.connect(progid, start=start and backend == "com")
                self.backend = be
                return info
            except Exception as exc:
                errors.append(f"COM: {exc}")
                if backend == "com":
                    raise RuntimeError(errors[0]) from exc
        self.backend = self.dxf_factory()
        info = self.backend.info()
        if errors:
            info["note"] = "AutoCAD not available, using the headless DXF backend. " + errors[0][:300]
        return info


STATE = State()


async def _run(fn: Callable[[], Any]) -> Any:
    """Execute on the COM thread (all CAD work is serialised there)."""

    def call():
        return STATE.worker.call(fn)

    try:
        return await anyio.to_thread.run_sync(call)
    except Exception as exc:
        log.exception("CAD call failed")
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc


def _props(layer: str | None, color: int | None, linetype: str | None = None,
           lineweight: int | None = None) -> dict:
    return {"layer": layer, "color": color, "linetype": linetype, "lineweight": lineweight}


# ------------------------------------------------------------------------------------------------------------
# Connection & documents
# ------------------------------------------------------------------------------------------------------------
@mcp.tool()
async def cad_connect(backend: str = "auto", progid: str | None = None, start: bool = True) -> dict:
    """Connect. backend: auto (running AutoCAD via COM, else DXF) | com (attach or start AutoCAD)
    | dxf (no AutoCAD). progid forces a product, e.g. 'AutoCAD.Application.24' (2021-2024),
    'BricscadApp.AcadApplication', 'ZWCAD.Application'."""
    return await _run(lambda: STATE.connect(backend, progid, start))


@mcp.tool()
async def cad_status() -> dict:
    """Backend, product, release (e.g. 24.3 -> AutoCAD 2024) and open documents."""
    return await _run(lambda: STATE.be().info())


@mcp.tool()
async def cad_versions() -> dict:
    """Supported AutoCAD releases and SaveAs formats."""
    return {"releases": RELEASES, "save_formats": sorted(SAVE_FORMATS)}


@mcp.tool()
async def doc_new(template: str | None = None, version: str | None = None) -> dict:
    """New drawing. template = .dwt (COM) / .dxf (DXF backend); version (DXF): R12|2000|2004|2007|2010|2013|2018."""
    return await _run(lambda: STATE.be().new_document(template, version))


@mcp.tool()
async def doc_open(path: str, read_only: bool = False) -> dict:
    """Open a DWG/DXF (DXF backend opens DWG only with ODA File Converter installed)."""
    return await _run(lambda: STATE.be().open_document(path, read_only))


@mcp.tool()
async def doc_save(path: str | None = None, format: str | None = None) -> dict:
    """Save / Save as. format e.g. '2018_dwg', '2013_dwg', '2010_dwg', '2007_dwg', '2004_dwg', '2000_dwg',
    '2018_dxf', 'R12_dxf' - to deliver drawings readable by older AutoCAD releases."""
    return await _run(lambda: STATE.be().save_document(path, format))


@mcp.tool()
async def doc_close(save: bool = False) -> dict:
    """Close the active drawing (COM)."""
    return await _run(lambda: STATE.com().close_document(save))


@mcp.tool()
async def doc_activate(name: str) -> dict:
    """Switch the active drawing by file name (COM)."""
    return await _run(lambda: STATE.com().activate_document(name))


# ------------------------------------------------------------------------------------------------------------
# Layers
# ------------------------------------------------------------------------------------------------------------
@mcp.tool()
async def layer_list() -> list:
    """All layers with colour, linetype and on/frozen/locked state."""
    return await _run(lambda: STATE.be().list_layers())


@mcp.tool()
async def layer_create(name: str, color: int | None = None, linetype: str | None = None,
                       lineweight: int | None = None, current: bool = False) -> dict:
    """Create/update a layer. color = ACI index; linetype e.g. CENTER, DASHED, HIDDEN (loaded
    from acadiso.lin); lineweight in 1/100 mm (e.g. 35 = 0.35 mm); current = make it current."""
    return await _run(lambda: STATE.be().create_layer(name, color, linetype, lineweight, current))


# ------------------------------------------------------------------------------------------------------------
# Drawing
# ------------------------------------------------------------------------------------------------------------
@mcp.tool()
async def draw_line(p1: list[float], p2: list[float], layer: str | None = None, color: int | None = None,
                    linetype: str | None = None) -> dict:
    """Line from p1 to p2 ([x, y] or [x, y, z])."""
    return {"handle": await _run(lambda: STATE.be().add_line(p1, p2, _props(layer, color, linetype)))}


@mcp.tool()
async def draw_polyline(points: list[list[float]], closed: bool = False, layer: str | None = None,
                        color: int | None = None, linetype: str | None = None) -> dict:
    """Polyline (2D lightweight when all z are equal, otherwise 3D polyline)."""
    return {"handle": await _run(lambda: STATE.be().add_polyline(points, closed, _props(layer, color, linetype)))}


@mcp.tool()
async def draw_circle(center: list[float], radius: float, layer: str | None = None, color: int | None = None) -> dict:
    """Circle."""
    return {"handle": await _run(lambda: STATE.be().add_circle(center, radius, _props(layer, color)))}


@mcp.tool()
async def draw_arc(center: list[float], radius: float, start_angle: float, end_angle: float,
                   layer: str | None = None, color: int | None = None) -> dict:
    """Arc counter-clockwise from start_angle to end_angle (degrees)."""
    return {"handle": await _run(lambda: STATE.be().add_arc(center, radius, start_angle, end_angle,
                                                            _props(layer, color)))}


@mcp.tool()
async def draw_text(text: str, point: list[float], height: float = 250.0, rotation: float = 0.0,
                    layer: str | None = None, color: int | None = None) -> dict:
    """Single-line text (height in drawing units: 2.5 mm x scale, e.g. 125 at 1:50)."""
    return {"handle": await _run(lambda: STATE.be().add_text(text, point, height, rotation, _props(layer, color)))}


@mcp.tool()
async def draw_mtext(text: str, point: list[float], width: float, height: float = 250.0,
                     layer: str | None = None, color: int | None = None) -> dict:
    """Multiline text in a box of given width (point = top-left)."""
    return {"handle": await _run(lambda: STATE.be().add_mtext(text, point, width, height, _props(layer, color)))}


@mcp.tool()
async def draw_point(point: list[float], layer: str | None = None) -> dict:
    """Point entity."""
    return {"handle": await _run(lambda: STATE.be().add_point(point, _props(layer, None)))}


@mcp.tool()
async def draw_dimension(p1: list[float], p2: list[float], location: list[float], angle: float | None = None,
                         text_height: float | None = None, layer: str | None = None) -> dict:
    """Dimension between p1 and p2, dimension line through location. angle None = aligned;
    0 = horizontal, 90 = vertical (rotated/linear dimension)."""
    props = {**_props(layer, None), "text_height": text_height}
    return {"handle": await _run(lambda: STATE.be().add_dimension(p1, p2, location, angle, props))}


@mcp.tool()
async def draw_hatch(outer: list[list[float]], holes: list[list[list[float]]] | None = None,
                     pattern: str = "ANSI31", scale: float = 1.0, layer: str | None = None,
                     color: int | None = None) -> dict:
    """Hatch a closed boundary (with optional holes). pattern: ANSI31 (concrete section), AR-CONC,
    EARTH, GRAVEL, SOLID..."""
    return {"handle": await _run(lambda: STATE.be().add_hatch(outer, holes or [], pattern, scale,
                                                              _props(layer, color)))}


@mcp.tool()
async def block_insert(name: str, point: list[float], scale: float = 1.0, rotation: float = 0.0,
                       attributes: dict[str, str] | None = None, layer: str | None = None) -> dict:
    """Insert a block by name (or a .dwg/.dxf file path) and fill its attributes {TAG: value}."""
    return {"handle": await _run(lambda: STATE.be().insert_block(name, point, scale, rotation, attributes,
                                                                 _props(layer, None)))}


@mcp.tool()
async def draw_table(origin: list[float], rows: list[list[Any]], col_widths: list[float] | None = None,
                     row_height: float = 600.0, text_height: float = 250.0, layer: str = "KC_TEXT") -> dict:
    """Table drawn with lines + texts (every release, DXF R12). origin = top-left corner."""
    return await _run(lambda: drawings.draw_table(STATE.be(), origin, rows, col_widths or [], row_height,
                                                  text_height, layer))


# ------------------------------------------------------------------------------------------------------------
# Query & modify
# ------------------------------------------------------------------------------------------------------------
@mcp.tool()
async def entities_list(layers: list[str] | None = None, kinds: list[str] | None = None,
                        bbox: list[float] | None = None, limit: int = 500) -> dict:
    """Entities of the current space with geometry. kinds: line, polyline, polyline3d, circle, arc,
    text, mtext, insert, dimension, hatch, point... bbox = [xmin, ymin, xmax, ymax]."""
    items = await _run(lambda: STATE.be().list_entities(layers, kinds, bbox, limit))
    return {"count": len(items), "limit_reached": len(items) >= limit, "entities": items}


@mcp.tool()
async def entity_get(handle: str) -> dict:
    """Full description of one entity."""
    return await _run(lambda: STATE.be().get_entity(handle))


@mcp.tool()
async def entities_transform(handles: list[str], operation: str, base: list[float] | None = None,
                             to: list[float] | None = None, angle: float | None = None,
                             factor: float | None = None, base2: list[float] | None = None,
                             copy: bool = False) -> dict:
    """operation: move (base -> to) | rotate (base, angle deg) | scale (base, factor) |
    mirror (axis base -> base2). copy = keep the original."""
    kw = {"base": base or [0, 0, 0], "to": to, "angle": angle, "factor": factor, "base2": base2, "copy": copy}
    return {"handles": await _run(lambda: STATE.be().transform(handles, operation, **kw))}


@mcp.tool()
async def entity_offset(handle: str, distance: float) -> dict:
    """Offset a line/polyline/circle/arc (COM). Negative distance = other side."""
    return {"handles": await _run(lambda: STATE.com().offset(handle, distance))}


@mcp.tool()
async def entities_set_properties(handles: list[str], properties: dict[str, Any]) -> dict:
    """Set properties, e.g. {"layer": "KC_BETONG", "color": 1, "text": "B30"}; COM also accepts any
    ActiveX property name (e.g. "LinetypeScale", "ConstantWidth")."""
    return {"warnings": await _run(lambda: STATE.be().set_properties(handles, properties))}


@mcp.tool()
async def entities_delete(handles: list[str]) -> dict:
    """Delete entities."""
    return {"deleted": await _run(lambda: STATE.be().delete(handles))}


@mcp.tool()
async def block_list() -> list:
    """Block definitions with attribute tags."""
    return await _run(lambda: STATE.be().list_blocks())


@mcp.tool()
async def block_attributes_extract(block: str | None = None, path: str | None = None) -> dict:
    """Table of attribute values of all references (optionally of one block), optional CSV
    (title blocks, pile schedules, survey points)."""
    return await _run(lambda: drawings.extract_attributes(STATE.be(), block, path))


@mcp.tool()
async def texts_extract(layers: list[str] | None = None, bbox: list[float] | None = None) -> dict:
    """All TEXT/MTEXT with positions, sorted as read on paper."""
    return await _run(lambda: drawings.extract_texts(STATE.be(), layers, bbox))


@mcp.tool()
async def quantities_by_layer(layers: list[str] | None = None) -> dict:
    """Take-off per layer: entity count, total length, closed area, block counts (drawing units)."""
    return await _run(lambda: drawings.quantities_by_layer(STATE.be(), layers))


# ------------------------------------------------------------------------------------------------------------
# AutoCAD command line, LISP, variables, output
# ------------------------------------------------------------------------------------------------------------
@mcp.tool()
async def cad_command(command: str) -> dict:
    """Send a command line to AutoCAD, e.g. '_.ZOOM _E', '_.PURGE _A * _N', '_.-LAYER _S 0 '.
    Use underscore/English command names so it works in every language version. Runs asynchronously."""
    return await _run(lambda: STATE.com().send_command(command))


@mcp.tool()
async def cad_lisp(expression: str, wait: float = 10.0) -> dict:
    """Evaluate an AutoLISP expression and return its printed value, e.g. '(getvar "DWGNAME")',
    '(length (vla-get-layers (vla-get-activedocument (vlax-get-acad-object))))' (after (vl-load-com))."""
    return await _run(lambda: STATE.com().eval_lisp(expression, wait))


@mcp.tool()
async def sysvar_get(name: str) -> dict:
    """Read a system variable (COM), e.g. INSUNITS, DIMSCALE, LTSCALE, ACADVER."""
    return {"name": name, "value": await _run(lambda: STATE.com().get_variable(name))}


@mcp.tool()
async def sysvar_set(name: str, value: Any) -> dict:
    """Set a system variable (COM)."""
    await _run(lambda: STATE.com().set_variable(name, value))
    return {"name": name, "value": value}


@mcp.tool()
async def zoom_extents() -> dict:
    """Zoom to drawing extents (COM)."""
    await _run(lambda: STATE.com().zoom_extents())
    return {"ok": True}


@mcp.tool()
async def plot_pdf(path: str, device: str = "DWG To PDF.pc3") -> dict:
    """Plot the active layout with its page setup to PDF (COM)."""
    return await _run(lambda: STATE.com().plot_to_file(path, device))


@mcp.tool()
async def preview_image(path: str | None = None) -> list:
    """PNG preview of the drawing to inspect the result: DXF backend renders with matplotlib;
    COM plots the active layout through 'PublishToWeb PNG.pc3'."""
    target = path or os.path.join(tempfile.gettempdir(), "autocad_mcp_preview.png")

    def work():
        be = STATE.be()
        if isinstance(be, ComBackend):
            be.zoom_extents()
            be.plot_to_file(target, "PublishToWeb PNG.pc3")
        else:
            be.render_png(target)
        return target

    out = await _run(work)
    if os.path.exists(out):
        with open(out, "rb") as fh:
            return [Image(data=fh.read(), format="png"), {"path": out}]
    return [{"path": out, "warning": "No image produced."}]


# ------------------------------------------------------------------------------------------------------------
# Engineering drawings
# ------------------------------------------------------------------------------------------------------------
@mcp.tool()
async def draw_box_culvert_section(params: dict[str, Any] | None = None) -> dict:
    """Cross-section of a box culvert / underpass (mm): outline with 45 deg haunches, concrete hatch,
    axis, chained dimensions, title and scale, on layers KC_*. params: clear_width, clear_height,
    t_top, t_bottom, t_wall, haunch, origin [x, y], scale (1:scale), hatch, title.
    Same parameters as the PLAXIS build_box_culvert tool (there in metres)."""
    params = dict(params or {})
    known = {f.name for f in fields(drawings.CulvertSection)}
    if set(params) - known:
        raise ToolError(f"Unknown parameters {sorted(set(params) - known)}; valid: {sorted(known)}")
    if "origin" in params:
        params["origin"] = tuple(params["origin"])
    s = drawings.CulvertSection(**params)
    return await _run(lambda: drawings.draw_culvert_section(STATE.be(), s))


def main() -> None:
    if "--check" in sys.argv:
        try:
            info = STATE.worker.call(lambda: STATE.connect("auto", start=False))
            print("[OK]", info)
            raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as exc:
            print("[FAIL]", exc)
            raise SystemExit(1)
    mcp.run()


if __name__ == "__main__":
    main()
