"""MCP server cho Bentley OpenTunnel Designer 2026.

Chay: `otd-mcp` (stdio). Server nay chi la lop dich MCP <-> HTTP; moi thao tac that su
thuc hien trong add-in OTDMcpBridge nap ben trong OpenTunnel Designer.
"""

from __future__ import annotations

import base64
import time
from typing import Any, Literal

from mcp.types import ToolAnnotations

try:  # mcp >= 2.0
    from mcp.server.mcpserver import Image, MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer, Image  # type: ignore[no-redef]

from .bridge_client import BridgeClient, ToolError
from .culvert import BoxCulvertSection, quantities
from .guide import GUIDE

INSTRUCTIONS = """\
Điều khiển Bentley OpenTunnel Designer 2026 (nền MicroStation) đang mở trên máy người dùng.
- Gọi otd_status trước tiên. Toạ độ = mét, kích thước tiết diện = mm.
- Ưu tiên tool có kiểu; lệnh OTD chưa có tool → otd_send_keyins (+ otd_send_data_point/otd_send_reset);
  API .NET sâu → otd_explore_api rồi otd_run_csharp. Không đoán tên key-in/API — dò trước.
- Sau thao tác ghi, kiểm tra bằng otd_capture_view hoặc truy vấn lại. Đọc resource otd://guide để biết chi tiết.
"""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

SectionPlane = Literal["vertical", "perpendicular"]


def create_server(client: BridgeClient | None = None) -> MCPServer:
    bridge = client or BridgeClient()
    mcp = MCPServer("opentunnel-designer", instructions=INSTRUCTIONS)

    # ------------------------------------------------------------------ phiên làm việc
    @mcp.tool(annotations=READ)
    def otd_status() -> dict[str, Any]:
        """Trạng thái bridge + thông tin phiên OTD: file/model/level active, đơn vị (UOR/mét), runtime .NET."""
        return bridge.call("session.info")

    @mcp.tool(annotations=WRITE)
    def otd_open_file(path: str, read_only: bool = False) -> dict[str, Any]:
        """Mở file DGN (đường dẫn tuyệt đối trên máy chạy OTD). File đang mở sẽ được OTD đóng theo cấu hình của nó."""
        return bridge.call("file.open", {"path": path, "read_only": read_only}, timeout_s=300)

    @mcp.tool(annotations=WRITE)
    def otd_save_file() -> dict[str, Any]:
        """Lưu file DGN active."""
        return bridge.call("file.save")

    @mcp.tool(annotations=READ)
    def otd_list_models() -> list[dict[str, Any]]:
        """Liệt kê model (design/sheet/drawing) trong file active."""
        return bridge.call("file.models")

    @mcp.tool(annotations=READ)
    def otd_list_levels() -> list[dict[str, Any]]:
        """Liệt kê level của file active."""
        return bridge.call("levels.list")

    @mcp.tool(annotations=WRITE)
    def otd_ensure_level(name: str, description: str | None = None, make_active: bool = False) -> dict[str, Any]:
        """Tạo level nếu chưa có; make_active=True để đặt làm level active."""
        return bridge.call("levels.ensure", {"name": name, "description": description, "make_active": make_active})

    # ------------------------------------------------------------------ phần tử
    @mcp.tool(annotations=READ)
    def otd_query_elements(
        level: str | None = None,
        element_type: str | None = None,
        text: str | None = None,
        limit: int = 100,
        offset: int = 0,
        include_range: bool = False,
        include_properties: bool = False,
    ) -> dict[str, Any]:
        """Lọc element đồ hoạ trong model active.

        level: tên level chính xác; element_type: chuỗi con của loại (vd 'Solid', 'Line', 'Cell');
        text: chuỗi con trong mô tả element. include_range: bao khung (mét).
        include_properties: kèm thuộc tính EC (chậm với model lớn — nên dùng otd_get_element).
        Phân trang bằng offset/limit (tối đa 5000).
        """
        return bridge.call("elements.query", {
            "level": level, "element_type": element_type, "text": text, "limit": limit,
            "offset": offset, "include_range": include_range, "include_properties": include_properties,
        }, timeout_s=300)

    @mcp.tool(annotations=READ)
    def otd_get_element(element_id: int, include_properties: bool = True) -> dict[str, Any]:
        """Chi tiết 1 element: loại, level, bao khung (mét) và TOÀN BỘ thuộc tính EC
        (nơi OpenTunnel/OpenRoads lưu tên tunnel, template, lý trình, vật liệu, khối lượng...)."""
        return bridge.call("elements.get", {"id": element_id, "include_properties": include_properties})

    @mcp.tool(annotations=READ)
    def otd_get_selection() -> dict[str, Any]:
        """Id các element người dùng đang chọn trong OTD."""
        return bridge.call("elements.selection")

    @mcp.tool(annotations=WRITE)
    def otd_select_elements(element_ids: list[int], clear_first: bool = True) -> dict[str, Any]:
        """Đưa element vào selection set (để sau đó chạy lệnh OTD tác động lên vùng chọn)."""
        return bridge.call("elements.select", {"ids": element_ids, "clear_first": clear_first})

    @mcp.tool(annotations=DESTRUCTIVE)
    def otd_delete_elements(element_ids: list[int]) -> dict[str, Any]:
        """XOÁ element theo id (có thể Undo trong OTD). Chỉ dùng khi người dùng yêu cầu rõ."""
        return bridge.call("elements.delete", {"ids": element_ids})

    # ------------------------------------------------------------------ key-in / input
    @mcp.tool(annotations=DESTRUCTIVE)
    def otd_send_keyins(keyins: list[str], delay_ms: int = 0) -> dict[str, Any]:
        """Gửi key-in vào OTD — chạy được MỌI lệnh trên ribbon (tunnel, civil, MicroStation).

        Key-in được xếp hàng và thực thi sau khi tool trả về. delay_ms > 0: gửi lần lượt từng
        key-in, nghỉ delay_ms giữa các lần (cho lệnh mở dialog/tính toán lâu).
        Không đoán key-in riêng của OpenTunnel — xem resource otd://guide mục 4.
        """
        if delay_ms <= 0:
            return bridge.call("keyin.send", {"keyins": keyins})
        sent: list[str] = []
        for k in keyins:
            bridge.call("keyin.send", {"keyins": [k]})
            sent.append(k)
            time.sleep(delay_ms / 1000)
        return {"queued": sent}

    @mcp.tool(annotations=WRITE)
    def otd_send_data_point(x: float, y: float, z: float = 0.0, view: int = 1) -> dict[str, Any]:
        """Gửi data point (click trái) tại toạ độ mét vào lệnh đang chạy (vd: điểm đặt, điểm đầu/cuối)."""
        return bridge.call("input.data_point", {"point": [x, y, z], "view": view})

    @mcp.tool(annotations=WRITE)
    def otd_send_reset() -> dict[str, Any]:
        """Gửi reset (click phải): kết thúc/huỷ bước hiện tại của lệnh đang chạy."""
        return bridge.call("input.reset")

    @mcp.tool(annotations=READ)
    def otd_get_cexpression(expression: str, app: str | None = None) -> dict[str, Any]:
        """Đọc giá trị một C expression của MicroStation (biến hệ thống/ứng dụng MDL)."""
        return bridge.call("cexpr.get", {"expression": expression, "app": app})

    # ------------------------------------------------------------------ hình học
    @mcp.tool(annotations=WRITE)
    def otd_draw_polyline(points: list[list[float]], closed: bool = False, level: str | None = None) -> dict[str, Any]:
        """Vẽ line string (closed=False) hoặc shape kín (closed=True). points: [[x,y,z], ...] mét."""
        return bridge.call("geometry.polyline", {"points": points, "closed": closed, "level": level})

    @mcp.tool(annotations=WRITE)
    def otd_create_extrusion(
        origin: list[float],
        end: list[float],
        loops: list[dict[str, Any]],
        section_plane: SectionPlane = "vertical",
        level: str | None = None,
    ) -> dict[str, Any]:
        """Đùn tiết diện 2D bất kỳ (hầm móng ngựa, tròn xấp xỉ đa giác, tường chắn...) theo trục origin→end.

        loops: [{"role": "outer"|"hole", "points": [[u, v], ...]}] (mét) — u ngang (dương = bên trái
        chiều origin→end), v đứng. Đúng 1 loop outer, nhiều hole.
        section_plane: 'vertical' (tiết diện thẳng đứng — tường đứng khi trục có dốc) |
        'perpendicular' (vuông góc trục 3D).
        """
        return bridge.call("geometry.extrusion", {
            "origin": origin, "end": end, "loops": loops, "section_plane": section_plane, "level": level,
        })

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
        dry_run=True: chỉ tính tiết diện + khối lượng bê tông, không vẽ.
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
            return result
        result["element"] = bridge.call("geometry.extrusion", {
            "origin": start, "end": end, "loops": loops, "section_plane": section_plane, "level": level,
        })
        return result

    # ------------------------------------------------------------------ hiển thị
    @mcp.tool(annotations=READ)
    def otd_capture_view(fit: bool = False, max_width: int = 1600) -> Image:
        """Chụp màn hình cửa sổ OpenTunnel Designer (PNG) để kiểm tra trực quan.
        fit=True: gửi 'fit view extended' và chờ vẽ lại trước khi chụp."""
        if fit:
            bridge.call("keyin.send", {"keyins": ["fit view extended"]})
            time.sleep(1.0)
        shot = bridge.call("view.capture", {"max_width": max_width})
        return Image(data=base64.b64decode(shot["data_base64"]), format="png")

    # ------------------------------------------------------------------ API nâng cao
    @mcp.tool(annotations=READ)
    def otd_explore_api(
        assembly_filter: str | None = None,
        type_filter: str | None = None,
        include_members: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Dò API .NET đang nạp trong OTD bằng reflection.

        Chỉ có assembly_filter (không type_filter) → danh sách assembly khớp (vd 'Tunnel', 'CifNET').
        Có type_filter → danh sách type public (+ chữ ký member nếu include_members=True).
        Dùng TRƯỚC otd_run_csharp để biết chính xác namespace/class/method.
        """
        if type_filter is None and not include_members:
            return bridge.call("api.assemblies", {"filter": assembly_filter})
        return bridge.call("api.types", {
            "assembly_filter": assembly_filter, "type_filter": type_filter,
            "include_members": include_members, "limit": limit,
        })

    @mcp.tool(annotations=DESTRUCTIVE)
    def otd_run_csharp(code: str, imports: list[str] | None = None, timeout_s: float = 120) -> dict[str, Any]:
        """Biên dịch & chạy C# script BÊN TRONG OTD trên main thread, tham chiếu mọi assembly đang nạp
        (MicroStation DgnPlatformNET/MstnPlatformNET, OpenRoads CifNET, OpenTunnel, ECObjects...).

        Biến có sẵn: Session, ActiveFile, ActiveModel, App (COM Interop), UorPerMeter, Print(x).
        Giá trị biểu thức cuối được trả về (return_value); Print → output. Lỗi biên dịch trả về trong
        'errors' để sửa và chạy lại. Script chặn giao diện OTD khi chạy — tránh vòng lặp dài.
        """
        return bridge.call("script.csharp", {"code": code, "imports": imports or [], "timeout_s": timeout_s},
                           timeout_s=timeout_s + 30)

    @mcp.tool(annotations=READ)
    def otd_bridge_methods() -> list[dict[str, Any]]:
        """(Chẩn đoán) Danh sách method RPC mà add-in bridge cung cấp."""
        return bridge.call("rpc.list")

    # ------------------------------------------------------------------ tài liệu
    @mcp.resource("otd://guide", name="otd-guide", mime_type="text/markdown",
                  description="Hướng dẫn chiến lược điều khiển OpenTunnel Designer qua MCP")
    def guide() -> str:
        return GUIDE

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
