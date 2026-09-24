"""MCP server exposing PLAXIS 3D (Input + Output remote scripting) to Claude."""

from __future__ import annotations

import logging
import sys
from dataclasses import fields
from typing import Any, Callable

import anyio

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

from .engineering import culvert, presets, traffic
from .ops import geometry, materials, project, results, staging
from .session import PlaxisSession

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("plaxis3d_mcp")

INSTRUCTIONS = """\
Controls PLAXIS 3D (Bentley) through its Remote Scripting server (plxscripting).
Units: kN, m, kPa, kN/m3. Z is up; loads acting downward are negative (sigz < 0).
Typical workflow: plaxis_connect -> project_new -> materials -> soil contour + boreholes
-> structures/loads -> mesh_generate -> phase_create/phase_configure -> calculate
-> output_connect -> results_* tools. For a box culvert / underpass under an embankment
use build_box_culvert, which does all of this parametrically.
Object names are PLAXIS names ('Plate_1', 'Phase_2', 'PlateMat_1'); in property values
a string starting with '@' refers to an object (e.g. {"Material": "@PlateMat_1"}).
When a dedicated tool is missing, use plaxis_command with PLAXIS command-line syntax.
Every tool returns 'warnings' for properties PLAXIS rejected - read them.
"""

mcp = _Server("plaxis3d", instructions=INSTRUCTIONS)
SESSION = PlaxisSession()


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking plxscripting call in a worker thread, one at a time."""

    def run():
        with SESSION.lock:
            return fn(SESSION, *args, **kwargs)

    try:
        return await anyio.to_thread.run_sync(run)
    except Exception as exc:
        log.exception("PLAXIS call %s failed", getattr(fn, "__name__", fn))
        # ToolError keeps the PLAXIS message visible to the model (other exceptions are masked)
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc


async def _pure(fn: Callable[..., Any], *args: Any) -> Any:
    """Calculation helpers that do not touch PLAXIS."""
    try:
        return fn(*args)
    except Exception as exc:
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------------------
# Connection & project
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def plaxis_connect(host: str | None = None, port: int | None = None, password: str | None = None) -> dict:
    """Connect to PLAXIS 3D Input remote scripting server (default localhost:10000,
    password from env PLAXIS_PASSWORD). In PLAXIS Input: Expert > Configure remote scripting server."""
    return await _call(lambda s: s.connect_input(host, port, password))


@mcp.tool()
async def plaxis_status() -> dict:
    """Connection status and PLAXIS version."""
    return await _call(lambda s: s.describe())


@mcp.tool()
async def project_new(title: str | None = None) -> dict:
    """Start a new, empty PLAXIS 3D project (unsaved changes in the open project are lost)."""
    return await _call(project.new_project, title)


@mcp.tool()
async def project_open(path: str) -> dict:
    """Open an existing .p3d project (absolute Windows path)."""
    return await _call(project.open_project, path)


@mcp.tool()
async def project_save(path: str | None = None) -> dict:
    """Save the project; with path = 'Save as' (e.g. D:/Projects/HamChui.p3d)."""
    return await _call(project.save_project, path)


@mcp.tool()
async def goto_mode(mode: str) -> dict:
    """Switch Input mode: soil | structures | mesh | flow | stages."""
    return await _call(project.goto_mode, mode)


# ---------------------------------------------------------------------------------------
# Generic object access
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def list_objects(group: str, output: bool = False) -> dict:
    """List a PLAXIS object group, e.g. Plates, Soillayers, Soils, Boreholes, Phases,
    Interfaces, SurfaceLoads, EmbeddedBeams, Materials. output=True reads from Output."""
    return await _call(project.list_objects, group, output)


@mcp.tool()
async def get_object(name: str, properties: list[str] | None = None, phase: str | None = None) -> dict:
    """Read properties of an object (all public ones when properties is omitted).
    With phase, staged values (e.g. Active, Material) are read for that phase."""
    return await _call(project.get_object, name, properties, phase)


@mcp.tool()
async def set_object_properties(name: str, properties: dict[str, Any], phase: str | None = None) -> dict:
    """Set properties of any object. Use '@Name' to reference objects, e.g.
    {"Material": "@PlateMat_2"}. With phase, values are set for that phase only."""
    return await _call(project.set_object_properties, name, properties, phase)


@mcp.tool()
async def delete_objects(names: list[str]) -> dict:
    """Delete objects by name."""
    return await _call(geometry.delete_objects, names)


@mcp.tool()
async def plaxis_command(command: str, output: bool = False) -> dict:
    """Run a raw PLAXIS command (command-line syntax), e.g.
    'cuboid 5 (0 0 0)', 'set Phase_1.MaxSteps 500', 'tabulate Plates "Name"'."""
    return await _call(project.run_command, command, output)


@mcp.tool()
async def plaxis_python(code: str) -> dict:
    """Execute Python with g_i, s_i, g_o, s_o in scope; assign to `result` to return data.
    Disabled unless the server runs with PLAXIS_MCP_ALLOW_PYTHON=1."""
    return await _call(project.run_python, code)


# ---------------------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def material_create(kind: str, properties: dict[str, Any]) -> dict:
    """Create a material. kind: soil | plate | beam | embeddedbeam | anchor | geogrid.
    properties use PLAXIS names, e.g. soil MC: {"name": "Sand", "SoilModel": 2,
    "gammaUnsat": 18, "gammaSat": 20, "Eref": 30000, "nu": 0.3, "cref": 1, "phi": 32, "psi": 2};
    plate: {"name": "Wall", "IsIsotropic": true, "d": 0.4, "Gamma": 25, "E1": 3.25e7, "nu12": 0.2}."""
    return await _call(materials.create_material, kind, properties)


@mcp.tool()
async def material_concrete_plate(grade: str, thickness: float, name: str | None = None) -> dict:
    """Create an elastic RC plate material, Eb per TCVN 5574:2018 (grade B15..B50)."""
    return await _call(materials.create_concrete_plate_material, grade, thickness, name)


@mcp.tool()
async def material_soil_preset(preset: str, name: str | None = None, overrides: dict[str, Any] | None = None) -> dict:
    """Create a Mohr-Coulomb soil from an indicative preset (preliminary models only):
    embankment_K95, backfill_granular_K98, soft_clay, stiff_clay, medium_dense_sand."""
    return await _call(materials.create_soil_material_from_preset, preset, name, overrides)


@mcp.tool()
async def material_list() -> dict:
    """List all materials in the project."""
    return await _call(materials.list_materials)


@mcp.tool()
async def material_set(material: str, properties: dict[str, Any]) -> dict:
    """Change properties of an existing material."""
    return await _call(materials.set_material_properties, material, properties)


# ---------------------------------------------------------------------------------------
# Soil & geometry
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def soil_contour(xmin: float, ymin: float, xmax: float, ymax: float) -> dict:
    """Set the rectangular model contour (plan extent)."""
    return await _call(geometry.set_soil_contour, xmin, ymin, xmax, ymax)


@mcp.tool()
async def borehole_create(
    x: float, y: float, layer_levels: list[float], head: float | None = None, materials: list[str] | None = None
) -> dict:
    """Create a borehole. layer_levels = layer boundaries top->bottom, e.g. [0, -3, -12, -30]
    (3 layers). head = groundwater head (m). materials = soil material names per layer."""
    return await _call(geometry.create_borehole, x, y, layer_levels, head, materials)


@mcp.tool()
async def soil_layer_material(layer_index: int, material: str) -> dict:
    """Assign a soil material to soil layer #layer_index (0 = top)."""
    return await _call(geometry.assign_layer_material, layer_index, material)


@mcp.tool()
async def soil_volume_create(points: list[list[float]], extrusion: list[float], material: str | None = None) -> dict:
    """Soil volume by extruding a planar polygon [[x,y,z],...] along vector [dx,dy,dz]
    (embankments, backfill zones, replacement layers)."""
    return await _call(geometry.create_soil_volume, points, extrusion, material)


@mcp.tool()
async def surface_create(points: list[list[float]]) -> dict:
    """Create a geometric surface from >= 3 coplanar points."""
    return await _call(geometry.create_surface, points)


@mcp.tool()
async def plate_create(points: list[list[float]], material: str | None = None, interfaces: str = "none") -> dict:
    """Plate (wall/slab/lining) on a planar polygon. interfaces: none|positive|negative|both
    (positive side by right-hand rule of the point order)."""
    return await _call(geometry.create_plate, points, material, interfaces)


@mcp.tool()
async def beam_create(p1: list[float], p2: list[float], material: str | None = None) -> dict:
    """Beam between two points."""
    return await _call(geometry.create_beam, p1, p2, material)


@mcp.tool()
async def embedded_beam_create(p1: list[float], p2: list[float], material: str | None = None) -> dict:
    """Embedded beam (pile): p1 = head, p2 = toe."""
    return await _call(geometry.create_embedded_beam, p1, p2, material)


@mcp.tool()
async def anchor_create(p1: list[float], p2: list[float], material: str | None = None) -> dict:
    """Node-to-node anchor between two points."""
    return await _call(geometry.create_node_to_node_anchor, p1, p2, material)


@mcp.tool()
async def surface_load_create(points: list[list[float]], sigx: float = 0, sigy: float = 0, sigz: float = 0) -> dict:
    """Uniform surface load (kPa) on a polygon; sigz < 0 = downward."""
    return await _call(geometry.create_surface_load, points, sigx, sigy, sigz)


@mcp.tool()
async def line_load_create(p1: list[float], p2: list[float], qx: float = 0, qy: float = 0, qz: float = 0) -> dict:
    """Uniform line load (kN/m); qz < 0 = downward."""
    return await _call(geometry.create_line_load, p1, p2, qx, qy, qz)


@mcp.tool()
async def point_load_create(point: list[float], Fx: float = 0, Fy: float = 0, Fz: float = 0) -> dict:
    """Point load (kN); Fz < 0 = downward."""
    return await _call(geometry.create_point_load, point, Fx, Fy, Fz)


# ---------------------------------------------------------------------------------------
# Mesh, phases, calculation
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def mesh_generate(coarseness: float = 0.06, enhanced_refinements: bool = True) -> dict:
    """Generate the 3D mesh. coarseness = relative element size (smaller = finer; 0.06 ~ Medium)."""
    return await _call(staging.generate_mesh, coarseness, enhanced_refinements)


@mcp.tool()
async def phase_create(
    identification: str,
    previous: str = "InitialPhase",
    calc_type: str = "plastic",
    activate: list[str] | None = None,
    deactivate: list[str] | None = None,
    reset_displacements: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict:
    """Add a staged-construction phase. calc_type: plastic|consolidation|safety|dynamic.
    activate/deactivate: object names (Soil_3, Plate_1, PositiveInterface_1, SurfaceLoad_2...).
    settings: phase properties, nested with dots, e.g. {"Deform.UseDefaultIterationParams": false}."""
    return await _call(
        staging.create_phase, identification, previous, calc_type, activate, deactivate, reset_displacements, settings
    )


@mcp.tool()
async def phase_configure(
    phase: str,
    calc_type: str | None = None,
    activate: list[str] | None = None,
    deactivate: list[str] | None = None,
    settings: dict[str, Any] | None = None,
    identification: str | None = None,
) -> dict:
    """Modify an existing phase (name or Identification), e.g. InitialPhase calc_type='k0' or 'gravity'."""
    return await _call(staging.configure_phase, phase, calc_type, activate, deactivate, settings, identification)


@mcp.tool()
async def phase_list() -> dict:
    """List phases with type, parent phase and calculation status."""
    return await _call(staging.list_phases)


@mcp.tool()
async def calculate(phases: list[str] | None = None) -> dict:
    """Run the calculation (blocks until PLAXIS finishes). phases limits which are calculated."""
    return await _call(staging.calculate, phases)


# ---------------------------------------------------------------------------------------
# Output / results
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def output_connect(port: int | None = None, phase: str | None = None) -> dict:
    """Connect to PLAXIS Output. Without port, Input opens Output for the phase (default last)."""
    return await _call(lambda s: s.connect_output(port, phase))


@mcp.tool()
async def results_get(
    result_type: str,
    phase: str | None = None,
    object_name: str | None = None,
    location: str = "node",
    include_values: bool = False,
    max_values: int = 500,
) -> dict:
    """Min/max/|max| (with coordinates) of a result: 'Soil.Uz', 'Soil.Utot', 'Soil.SigzzE',
    'Plate.M11', 'Plate.Q13', 'Plate.N1', 'EmbeddedBeam.N', 'Interface.SigN'...
    location: node | stresspoint. object_name restricts to one structure (Output name)."""
    return await _call(results.get_results, result_type, phase, object_name, location, include_values, max_values)


@mcp.tool()
async def results_at_point(result_type: str, x: float, y: float, z: float, phase: str | None = None) -> dict:
    """Single result value at a point (e.g. settlement 'Soil.Uz' at the road centre line)."""
    return await _call(results.get_result_at_point, result_type, x, y, z, phase)


@mcp.tool()
async def results_plate_forces(
    phase: str | None = None, plates: list[str] | None = None, quantities: list[str] | None = None
) -> dict:
    """Envelope (min/max) of plate forces N1, N2, Q13, Q23, M11, M22, M12 per plate for a phase."""
    return await _call(results.plate_force_envelope, phase, plates, quantities)


# ---------------------------------------------------------------------------------------
# Engineering helpers (no PLAXIS connection needed)
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def hl93_live_load_through_fill(
    fill_depth: float, granular_fill: bool = True, max_lanes: int = 1, clear_span: float | None = None
) -> dict:
    """HL-93 live load on a buried culvert per TCVN 11823-3:2017 (§3.6.1.2.6, §3.6.2.2):
    spread pressure at the top slab (hand check) and wheel-patch pressures for the 3D model."""
    return await _pure(traffic.hl93_through_fill, fill_depth, granular_fill, max_lanes, clear_span)


@mcp.tool()
async def concrete_properties(grade: str, thickness: float) -> dict:
    """PLAXIS plate properties of RC per TCVN 5574:2018 (no PLAXIS call)."""
    return await _pure(presets.concrete_plate_props, grade, thickness)


@mcp.tool()
async def box_culvert_layout(params: dict[str, Any] | None = None) -> dict:
    """Preview the geometry build_box_culvert would create (no PLAXIS call)."""
    return await _pure(lambda: culvert.layout(_culvert_params(params)))


@mcp.tool()
async def build_box_culvert(params: dict[str, Any] | None = None) -> dict:
    """Build a complete PLAXIS 3D model of a box culvert / underpass (hầm chui) under a road
    embankment in the CURRENT project: RC plates (TCVN 5574), wing/head walls, interfaces,
    embankment volumes, boreholes, HL-93 wheel loads (TCVN 11823-3), mesh and phases
    (K0 -> culvert -> embankment -> traffic). Start from project_new.
    params (all optional): clear_width, clear_height, t_top, t_bottom, t_wall, concrete_grade,
    cover, crest_width, side_slope, culvert_length, wing_walls, layer_levels, layer_presets,
    layer_materials, water_head, embankment_preset, margin_x, margin_y, traffic, vehicle, lanes,
    truck_x, granular_fill, generate_mesh, mesh_coarseness, auto_stage."""
    p = await _pure(_culvert_params, params)
    return await _call(culvert.build_box_culvert, p)


def _culvert_params(params: dict[str, Any] | None) -> culvert.BoxCulvertParams:
    params = dict(params or {})
    known = {f.name for f in fields(culvert.BoxCulvertParams)}
    unknown = set(params) - known
    if unknown:
        raise RuntimeError(f"Unknown culvert parameters {sorted(unknown)}; valid: {sorted(known)}")
    return culvert.BoxCulvertParams(**params)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
