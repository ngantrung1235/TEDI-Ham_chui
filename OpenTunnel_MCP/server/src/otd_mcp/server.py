"""MCP server cho Bentley OpenTunnel Designer 2026.

Chay: `otd-mcp` (stdio). Server nay chi la lop dich MCP <-> HTTP; moi thao tac that su
thuc hien trong add-in OTDMcpBridge nap ben trong OpenTunnel Designer. Cac tool chung
(otd_status, otd_send_keyins, otd_run_csharp...) nam o bentley_mcp_core.common_tools.
"""

from __future__ import annotations

from typing import Any

from bentley_mcp_core import BridgeClient
from bentley_mcp_core.common_tools import SectionPlane, register_common_tools
from bentley_mcp_core.compat import WRITE, MCPServer, ToolError
from bentley_mcp_core.guide import common_guide
from bentley_mcp_core.sections import section_properties

from . import PRODUCT
from .culvert import BoxCulvertSection, quantities
from .guide import TUNNEL_GUIDE

INSTRUCTIONS = """\
Điều khiển Bentley OpenTunnel Designer 2026 (nền MicroStation) đang mở trên máy người dùng.
- Gọi otd_status trước tiên. Toạ độ = mét, kích thước tiết diện = mm.
- Ưu tiên tool có kiểu; đối tượng tunnel → otd_ec_summary/otd_find_by_ec_class; lệnh chưa có tool →
  otd_send_keyins (+ otd_send_data_point/otd_send_reset); API .NET sâu → otd_explore_api rồi otd_run_csharp.
  Không đoán tên key-in/API — dò trước.
- Sau thao tác ghi, kiểm tra bằng otd_capture_view hoặc truy vấn lại. Đọc resource otd://guide để biết chi tiết.
"""


def create_server(client: BridgeClient | None = None) -> MCPServer:
    bridge = client or BridgeClient(PRODUCT)
    mcp = MCPServer("opentunnel-designer", instructions=INSTRUCTIONS)
    register_common_tools(mcp, bridge, PRODUCT)

    @mcp.tool(annotations=WRITE)
    def otd_create_box_culvert(
        start: list[float],
        end: list[float],
        clear_width_mm: float,
        clear_height_mm: float,
        top_slab_mm: float,
        bottom_slab_mm: float,
        wall_mm: float,
        cells: int = 1,
        mid_wall_mm: float | None = None,
        chamfer_top_mm: float = 0.0,
        chamfer_bottom_mm: float = 0.0,
        section_plane: SectionPlane = "vertical",
        level: str | None = "HamChui_BeTong",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Dựng khối bê tông hầm chui / cống hộp BTCT (1 hoặc nhiều khoang, có vút góc 45°).

        start/end: tim MẶT DƯỚI BẢN ĐÁY tại 2 đầu đoạn hầm [x, y, z] (mét).
        clear_width_mm × clear_height_mm: khẩu độ thông thuỷ B × H mỗi khoang.
        top_slab_mm / bottom_slab_mm / wall_mm: chiều dày bản nắp / bản đáy / tường biên;
        mid_wall_mm: tường giữa (bắt buộc khi cells > 1). chamfer_*: cạnh vút trong.
        dry_run=True: chỉ tính tiết diện, đặc trưng hình học + khối lượng bê tông, không vẽ.
        """
        section = BoxCulvertSection(
            clear_width_mm=clear_width_mm, clear_height_mm=clear_height_mm,
            top_slab_mm=top_slab_mm, bottom_slab_mm=bottom_slab_mm, wall_mm=wall_mm,
            cells=cells, mid_wall_mm=mid_wall_mm,
            chamfer_top_mm=chamfer_top_mm, chamfer_bottom_mm=chamfer_bottom_mm,
        )
        try:
            section.validate()
        except ValueError as exc:
            raise ToolError(f"Tiết diện không hợp lệ: {exc}") from exc
        result: dict[str, Any] = {"quantities": quantities(section, start, end, section_plane)}
        loops = section.loops_m()
        if dry_run:
            result["loops_m"] = loops
            result["section_properties"] = section_properties(loops, unit="m")
            return result
        result["element"] = bridge.call("geometry.extrusion", {
            "origin": start, "end": end, "loops": loops, "section_plane": section_plane, "level": level,
        })
        return result

    @mcp.resource("otd://guide", name="otd-guide", mime_type="text/markdown",
                  description="Hướng dẫn chiến lược điều khiển OpenTunnel Designer qua MCP")
    def guide() -> str:
        return common_guide(PRODUCT, asm_hint="Tunnel") + TUNNEL_GUIDE

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
