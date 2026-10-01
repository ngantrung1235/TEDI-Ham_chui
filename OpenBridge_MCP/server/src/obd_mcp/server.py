"""MCP server cho Bentley OpenBridge Designer 2026.

Chay: `obd-mcp` (stdio). Server nay chi la lop dich MCP <-> HTTP; moi thao tac that su
thuc hien trong add-in OBDMcpBridge nap ben trong OpenBridge Designer. Cac tool chung
(obd_status, obd_send_keyins, obd_run_csharp...) nam o bentley_mcp_core.common_tools.
"""

from __future__ import annotations

from typing import Any

from bentley_mcp_core import BridgeClient
from bentley_mcp_core.common_tools import SectionPlane, register_common_tools
from bentley_mcp_core.compat import WRITE, MCPServer, ToolError
from bentley_mcp_core.guide import common_guide

from . import PRODUCT
from .guide import BRIDGE_GUIDE
from .shapes import (
    DeckSlab,
    IGirderSection,
    MultiColumnPier,
    axis_info,
    composite_properties,
    lateral_offsets_m,
    offset_axis,
)

INSTRUCTIONS = """\
Điều khiển Bentley OpenBridge Designer 2026 (OpenBridge Modeler + OpenRoads, nền MicroStation) đang mở
trên máy người dùng.
- Gọi obd_status trước tiên. Toạ độ = mét, kích thước tiết diện/cấu kiện = mm.
- Đối tượng cầu OBM có sẵn → obd_ec_summary rồi obd_find_by_ec_class (không đoán tên schema/class).
- Dựng nhanh dầm/bản/trụ dạng solid → obd_create_girders / obd_create_deck_slab / obd_create_pier
  (dry_run=True để tính trước). Tạo đối tượng OBM native → obd_send_keyins (+ data point) hoặc obd_run_csharp
  sau khi dò API bằng obd_explore_api.
- Sau thao tác ghi, kiểm tra bằng obd_capture_view hoặc truy vấn lại. Đọc resource obd://guide để biết chi tiết.
"""


def _check(fn):
    try:
        return fn()
    except ValueError as exc:
        raise ToolError(f"Tham số không hợp lệ: {exc}") from exc


def create_server(client: BridgeClient | None = None) -> MCPServer:
    bridge = client or BridgeClient(PRODUCT)
    mcp = MCPServer("openbridge-designer", instructions=INSTRUCTIONS)
    register_common_tools(mcp, bridge, PRODUCT)

    def extrude(origin, end, loops, section_plane, level) -> dict[str, Any]:
        return bridge.call("geometry.extrusion", {
            "origin": origin, "end": end, "loops": loops, "section_plane": section_plane, "level": level,
        })

    # ------------------------------------------------------------------ dầm I
    @mcp.tool(annotations=WRITE)
    def obd_create_girders(
        start: list[float],
        end: list[float],
        height_mm: float,
        top_flange_width_mm: float,
        top_flange_thickness_mm: float,
        top_haunch_height_mm: float,
        web_thickness_mm: float,
        bottom_flange_width_mm: float,
        bottom_flange_thickness_mm: float,
        bottom_haunch_height_mm: float,
        count: int = 1,
        spacing_mm: float | None = None,
        slab_effective_width_mm: float | None = None,
        slab_thickness_mm: float | None = None,
        slab_haunch_mm: float = 0.0,
        modular_ratio: float = 1.0,
        section_plane: SectionPlane = "vertical",
        level: str | None = "Dam_BeTong",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Dựng dầm I tham số (kiểu AASHTO/PCI, dầm I BTCT DƯL) — 1 hoặc nhiều dầm song song.

        start/end: TIM ĐÁY DẦM tại 2 đầu dầm [x, y, z] (mét) của dầm ở giữa nhóm.
        count/spacing_mm: số dầm và khoảng cách tim-tim; các dầm rải đối xứng 2 bên trục start→end.
        Kích thước tiết diện (mm): height, top_flange_width/thickness, top_haunch_height (vút trên, chiều đứng),
        web_thickness, bottom_flange_width/thickness, bottom_haunch_height (vút dưới).
        Liên hợp (tuỳ chọn): slab_effective_width_mm (b_eff theo TCVN 11823-4 / AASHTO 4.6.2.6), slab_thickness_mm,
        slab_haunch_mm (lớp đệm), modular_ratio n = E_bản/E_dầm.
        Trả về đặc trưng tiết diện (mm), khối lượng bê tông; dry_run=True: không vẽ.
        """
        section = IGirderSection(
            height_mm=height_mm, top_flange_width_mm=top_flange_width_mm,
            top_flange_thickness_mm=top_flange_thickness_mm, top_haunch_height_mm=top_haunch_height_mm,
            web_thickness_mm=web_thickness_mm, bottom_flange_width_mm=bottom_flange_width_mm,
            bottom_flange_thickness_mm=bottom_flange_thickness_mm, bottom_haunch_height_mm=bottom_haunch_height_mm,
        )
        _check(section.validate)
        axis = _check(lambda: axis_info(start, end))
        offsets = _check(lambda: lateral_offsets_m(count, spacing_mm))
        props = section.properties_mm()
        effective_len = axis["length_plan_m"] if section_plane == "vertical" else axis["length_3d_m"]
        volume_each = props["area_mm2"] * 1e-6 * effective_len

        result: dict[str, Any] = {
            "section_properties_mm": props,
            "girder_length_3d_m": round(axis["length_3d_m"], 4),
            "longitudinal_slope_pct": round(axis["slope_pct"], 4),
            "concrete_volume_per_girder_m3": round(volume_each, 4),
            "concrete_volume_total_m3": round(volume_each * count, 4),
            "lateral_offsets_m": offsets,
        }
        if slab_effective_width_mm is not None or slab_thickness_mm is not None:
            if not slab_effective_width_mm or not slab_thickness_mm:
                raise ToolError("Tiết diện liên hợp cần cả slab_effective_width_mm và slab_thickness_mm.")
            result["composite_properties_mm"] = _check(lambda: composite_properties(
                section, slab_effective_width_mm, slab_thickness_mm, slab_haunch_mm, modular_ratio))
        if dry_run:
            result["loops_m"] = section.loops_m()
            return result

        loops = section.loops_m()
        result["elements"] = []
        for off in offsets:
            s, e = offset_axis(axis, off)
            result["elements"].append({"offset_m": off, **extrude(s, e, loops, section_plane, level)})
        return result

    # ------------------------------------------------------------------ bản mặt cầu
    @mcp.tool(annotations=WRITE)
    def obd_create_deck_slab(
        start: list[float],
        end: list[float],
        width_mm: float,
        thickness_mm: float,
        left_slope_pct: float = 2.0,
        right_slope_pct: float = 2.0,
        crown_offset_mm: float = 0.0,
        section_plane: SectionPlane = "vertical",
        level: str | None = "BanMatCau",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Dựng bản mặt cầu dày đều theo trục start→end.

        start/end: ĐỈNH MẶT BẢN tại vị trí đỉnh dốc (crown) ở 2 đầu (mét).
        left/right_slope_pct: dốc ngang từ crown ra mép trái/phải, DƯƠNG = dốc xuống (2 mái 2%: 2 và 2;
        siêu cao 1 mái 4% xuống bên phải: -4 và 4). crown_offset_mm: crown lệch khỏi trục (dương = trái).
        """
        slab = DeckSlab(width_mm=width_mm, thickness_mm=thickness_mm, left_slope_pct=left_slope_pct,
                        right_slope_pct=right_slope_pct, crown_offset_mm=crown_offset_mm)
        _check(slab.validate)
        axis = _check(lambda: axis_info(start, end))
        effective_len = axis["length_plan_m"] if section_plane == "vertical" else axis["length_3d_m"]
        result: dict[str, Any] = {
            "area_m2": round(slab.area_m2(), 6),
            "length_3d_m": round(axis["length_3d_m"], 4),
            "concrete_volume_m3": round(slab.area_m2() * effective_len, 4),
        }
        loops = slab.loops_m()
        if dry_run:
            result["loops_m"] = loops
            return result
        result["element"] = extrude(axis["start"], axis["end"], loops, section_plane, level)
        return result

    # ------------------------------------------------------------------ trụ
    @mcp.tool(annotations=WRITE)
    def obd_create_pier(
        base_point: list[float],
        orientation_deg: float,
        footing_length_mm: float,
        footing_width_mm: float,
        footing_thickness_mm: float,
        column_count: int,
        column_height_mm: float,
        cap_length_mm: float,
        cap_width_mm: float,
        cap_depth_mm: float,
        column_shape: str = "circle",
        column_diameter_mm: float | None = None,
        column_size_mm: list[float] | None = None,
        column_spacing_mm: float = 0.0,
        level: str | None = "Tru_BeTong",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Dựng trụ cầu nhiều cột: bệ + n cột (tròn/chữ nhật) + xà mũ chữ nhật.

        base_point: TIM ĐÁY BỆ [x, y, z] (mét). orientation_deg: góc phương vị trục ngang trụ (phương dài xà mũ)
        từ +X, ngược chiều kim đồng hồ. footing_length/cap_length: dọc trục ngang trụ; *_width: dọc hướng cầu.
        Cột tròn: column_diameter_mm; cột chữ nhật: column_size_mm [a dọc trục ngang, b dọc hướng cầu].
        column_spacing_mm: tim-tim cột. Trả về khối lượng bệ/cột/xà mũ và cao độ; dry_run=True: không vẽ.
        """
        pier = MultiColumnPier(
            footing_length_mm=footing_length_mm, footing_width_mm=footing_width_mm,
            footing_thickness_mm=footing_thickness_mm, column_count=column_count,
            column_height_mm=column_height_mm, column_spacing_mm=column_spacing_mm,
            cap_length_mm=cap_length_mm, cap_width_mm=cap_width_mm, cap_depth_mm=cap_depth_mm,
            column_shape=column_shape, column_diameter_mm=column_diameter_mm,
            column_size_mm=tuple(column_size_mm) if column_size_mm else None,
        )
        _check(pier.validate)
        comps = pier.components(base_point, orientation_deg)
        result: dict[str, Any] = {"quantities": pier.quantities(base_point)}
        if dry_run:
            result["components"] = comps
            return result
        result["elements"] = [
            {"name": c["name"], **extrude(c["origin"], c["end"], c["loops"], "perpendicular", level)}
            for c in comps
        ]
        return result

    @mcp.resource("obd://guide", name="obd-guide", mime_type="text/markdown",
                  description="Hướng dẫn chiến lược điều khiển OpenBridge Designer qua MCP")
    def guide() -> str:
        return common_guide(PRODUCT, asm_hint="Bridge") + BRIDGE_GUIDE

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
