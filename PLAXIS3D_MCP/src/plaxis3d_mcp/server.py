"""MCP server exposing PLAXIS 3D (Input + Output remote scripting) to Claude."""

from __future__ import annotations

import logging
import sys
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

from .engineering import culvert, design, presets, traffic, tunnel
from .ops import design_check, export, geometry, importers, materials, project, results, staging, water
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
Tunnels: build_tunnel (step-by-step excavation). Imports: import_geometry, import_dxf,
import_boreholes. Water: water_* tools. Exports: results_export, results_along_line,
results_history, plot_image (returns a picture you can look at). Design: design_check_plates
(TCVN 11823 Strength I / Service I on plate forces), rc_section_check.
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


# ---------------------------------------------------------------------------------------
# Tunnels
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def build_tunnel(params: dict[str, Any] | None = None) -> dict:
    """Circular tunnel with step-by-step excavation in the CURRENT project (soil must exist):
    per round a core soil volume, lining plates and optional face pressure; phases
    K0 -> round 1..N (excavate, dry core, face pressure, lining installed unsupported_rounds
    behind the face) -> lining closure. params: center_x, center_z, y_start, radius, rounds,
    round_length, n_facets, lining_grade, lining_thickness, lining_material, core_material,
    unsupported_rounds, face_pressure, interfaces, dry_core, auto_stage, generate_mesh,
    mesh_coarseness. Axis along +Y."""
    p = await _pure(_dataclass_params, tunnel.TunnelParams, params)
    return await _call(tunnel.build_tunnel, p)


# ---------------------------------------------------------------------------------------
# Import (Civil 3D / Revit / Excel)
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def import_geometry(path: str) -> dict:
    """Import a geometry file with PLAXIS' own importer (DXF/DWG/IFC/STEP/3DS, version dependent)."""
    return await _call(importers.import_geometry_native, path)


@mcp.tool()
async def import_dxf(
    path: str,
    create: str = "surface",
    layers: list[str] | None = None,
    material: str | None = None,
    scale: float = 1.0,
    offset: list[float] | None = None,
    extrusion: list[float] | None = None,
    max_faces: int = 2000,
) -> dict:
    """Read 3DFACE / closed polylines / meshes from a DXF (Civil 3D, Revit export) and create
    surfaces, plates or extruded soil volumes. offset = [x0, y0, z0] subtracted before scaling
    (e.g. VN-2000 coordinates -> local origin); scale = 0.001 for mm drawings. Needs ezdxf."""
    return await _call(importers.import_dxf, path, create, layers, material, scale, offset, extrusion, max_faces)


@mcp.tool()
async def import_boreholes(path: str, create_missing_materials: bool = False) -> dict:
    """Boreholes from CSV/XLSX, one row per layer top->bottom with columns
    borehole, x, y, top, bottom, material[, head]. All boreholes need the same layer sequence
    (zero thickness allowed). Materials are referenced by their Identification."""
    return await _call(importers.import_boreholes, path, create_missing_materials)


# ---------------------------------------------------------------------------------------
# Groundwater
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def water_borehole_head(borehole: str, head: float) -> dict:
    """Set the groundwater head of a borehole (m)."""
    return await _call(water.set_borehole_head, borehole, head)


@mcp.tool()
async def water_level_create(points: list[list[float]]) -> dict:
    """Create a user water level through >= 3 points (e.g. lowered level in an excavation)."""
    return await _call(water.create_water_level, points)


@mcp.tool()
async def water_phase_settings(
    phase: str, pore_pressure: str | None = None, global_water_level: str | None = None
) -> dict:
    """Phase pore pressure: phreatic | steady | previous, and the global water level name."""
    return await _call(water.set_phase_water, phase, pore_pressure, global_water_level)


@mcp.tool()
async def water_soil_condition(soils: list[str], phase: str, condition: str = "Dry", head: float | None = None) -> dict:
    """Water condition of soil volumes/clusters in a phase: Dry | Head (with head) |
    Interpolate | Global level | Cluster phreatic level | User-defined."""
    return await _call(water.set_soil_water_condition, soils, phase, condition, head)


# ---------------------------------------------------------------------------------------
# Exports and images
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def results_export(
    result_types: list[str], path: str, phase: str | None = None, object_name: str | None = None,
    location: str = "node",
) -> dict:
    """Write X, Y, Z + result columns of one group to .csv or .xlsx (e.g. ['Soil.Ux','Soil.Uz'])."""
    return await _call(export.export_results, result_types, path, phase, object_name, location)


@mcp.tool()
async def results_along_line(
    p1: list[float], p2: list[float], result_types: list[str], n_points: int = 51,
    phase: str | None = None, path: str | None = None,
) -> dict:
    """Sample results along a line (settlement trough, profile under a slab), optional CSV/XLSX."""
    return await _call(export.results_along_line, p1, p2, result_types, n_points, phase, path)


@mcp.tool()
async def results_history(
    point: list[float], result_types: list[str], phases: list[str] | None = None, path: str | None = None
) -> dict:
    """Values at one point through all phases (settlement vs construction stage)."""
    return await _call(export.results_history, point, result_types, phases, path)


@mcp.tool()
async def plot_image(
    path: str, result_type: str | None = None, phase: str | None = None, width: int = 1600, height: int = 1000
) -> list:
    """Export the current Output plot as PNG (optionally set result type / phase first) and
    return the image so it can be inspected."""
    info, data = await _call(export.export_plot_image, path, result_type, phase, width, height)
    return [Image(data=data, format="png"), info] if data else [info]


# ---------------------------------------------------------------------------------------
# Design checks (TCVN 11823)
# ---------------------------------------------------------------------------------------
@mcp.tool()
async def design_check_plates(
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
    """TCVN 11823-3 Strength I / Service I combination of plate forces (factoring of effects:
    permanent phase x gamma_p + (live - permanent) x gamma_LL) and TCVN 11823-5 checks of
    flexure+axial (strain compatibility), shear (culvert-slab clause for fill >= 0.6 m) and crack
    control, both plate directions. sections: {"Plate_1_1": {"h": 500, "as_pos": 1340,
    "as_neg": 1005, "cover": 60, "fc": 30, "fy": 400, "spacing": 150, "member": "top_slab",
    "dir2": {"as_pos": 560, "as_neg": 560}}, "*": {...default for other plates}}. mm, MPa."""
    return await _call(
        design_check.design_check_plates, permanent_phase, sections, live_phase, gamma_p_max, gamma_p_min,
        gamma_ll, eta, fill_depth, path,
    )


@mcp.tool()
async def rc_section_check(
    section: dict[str, Any], Mu: float, Pu: float = 0.0, Vu: float = 0.0, Ms: float | None = None,
    member: str = "wall", fill_depth: float | None = None,
) -> dict:
    """Check one 1 m wide RC section (TCVN 11823-5): Mu kNm/m, Pu kN/m (compression +), Vu kN/m,
    Ms service moment. section: h, as_pos, as_neg, cover, fc, fy, spacing, gamma_e (mm, MPa)."""
    return await _pure(
        lambda: design.check_point(design.Section(**section), Mu, Pu, Vu, Mu if Ms is None else Ms, member, fill_depth)
    )


@mcp.tool()
async def load_factors() -> dict:
    """Load factors of TCVN 11823-3:2017 Tables 3.4.1-1/-2 used by the design tools."""
    return {k: {"max": v[0], "min": v[1]} for k, v in design.LOAD_FACTORS.items()}


def _dataclass_params(cls: type, params: dict[str, Any] | None) -> Any:
    params = dict(params or {})
    known = {f.name for f in fields(cls)}
    unknown = set(params) - known
    if unknown:
        raise RuntimeError(f"Unknown parameters {sorted(unknown)}; valid: {sorted(known)}")
    return cls(**params)


def _culvert_params(params: dict[str, Any] | None) -> culvert.BoxCulvertParams:
    return _dataclass_params(culvert.BoxCulvertParams, params)


def check() -> int:
    """`python -m plaxis3d_mcp --check`: test the PLAXIS connection from a terminal."""
    try:
        info = SESSION.connect_input()
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1
    print("[OK] Connected to PLAXIS:", {k: v for k, v in info.items() if v is not None})
    return 0


def main() -> None:
    if "--check" in sys.argv:
        raise SystemExit(check())
    if "--list-tools" in sys.argv:

        async def _names():
            return sorted(t.name for t in await mcp.list_tools())

        for name in anyio.run(_names):
            print(name)
        return
    mcp.run()


if __name__ == "__main__":
    main()
