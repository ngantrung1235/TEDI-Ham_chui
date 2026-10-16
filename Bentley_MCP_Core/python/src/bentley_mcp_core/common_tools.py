"""Tool MCP dung chung cho moi san pham nen MicroStation (ten tool co tien to theo san pham)."""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp_bridge_common import BridgeClient, ProductConfig
from mcp_bridge_common.compat import DESTRUCTIVE, READ, WRITE, MCPServer, ToolError
from mcp_bridge_common.registry import make_tool, register_generic_tools

from .sections import section_properties

SectionPlane = Literal["vertical", "perpendicular"]


def register_common_tools(mcp: MCPServer, bridge: BridgeClient, product: ProductConfig) -> None:
    tool = make_tool(mcp, product)

    # ------------------------------------------------------------------ phiên làm việc
    @tool("status", READ, "Trạng thái bridge + thông tin phiên {product}: file/model/level active, "
                          "đơn vị (UOR/mét), runtime .NET.")
    def status() -> dict[str, Any]:
        return bridge.call("session.info")

    @tool("open_file", WRITE, "Mở file DGN (đường dẫn tuyệt đối trên máy chạy {product}).")
    def open_file(path: str, read_only: bool = False) -> dict[str, Any]:
        return bridge.call("file.open", {"path": path, "read_only": read_only}, timeout_s=300)

    @tool("save_file", WRITE, "Lưu file DGN active.")
    def save_file() -> dict[str, Any]:
        return bridge.call("file.save")

    @tool("list_models", READ, "Liệt kê model (design/sheet/drawing) trong file active.")
    def list_models() -> list[dict[str, Any]]:
        return bridge.call("file.models")

    @tool("list_levels", READ, "Liệt kê level của file active.")
    def list_levels() -> list[dict[str, Any]]:
        return bridge.call("levels.list")

    @tool("ensure_level", WRITE, "Tạo level nếu chưa có; make_active=True để đặt làm level active.")
    def ensure_level(name: str, description: str | None = None, make_active: bool = False) -> dict[str, Any]:
        return bridge.call("levels.ensure", {"name": name, "description": description, "make_active": make_active})

    # ------------------------------------------------------------------ phần tử
    @tool("query_elements", READ,
          "Lọc element đồ hoạ trong model active. level: tên level chính xác; element_type: chuỗi con của loại "
          "(vd 'Solid', 'Line', 'Cell'); text: chuỗi con trong mô tả. include_range: bao khung (mét). "
          "include_properties: kèm thuộc tính EC (chậm — nên dùng {p}_get_element). Phân trang offset/limit (≤5000).")
    def query_elements(level: str | None = None, element_type: str | None = None, text: str | None = None,
                       limit: int = 100, offset: int = 0, include_range: bool = False,
                       include_properties: bool = False) -> dict[str, Any]:
        return bridge.call("elements.query", {
            "level": level, "element_type": element_type, "text": text, "limit": limit,
            "offset": offset, "include_range": include_range, "include_properties": include_properties,
        }, timeout_s=300)

    @tool("get_element", READ,
          "Chi tiết 1 element: loại, level, bao khung (mét) và TOÀN BỘ thuộc tính EC (nơi {product} lưu "
          "dữ liệu nghiệp vụ: tên đối tượng, template, lý trình, vật liệu, khối lượng...).")
    def get_element(element_id: int, include_properties: bool = True) -> dict[str, Any]:
        return bridge.call("elements.get", {"id": element_id, "include_properties": include_properties})

    @tool("get_selection", READ, "Id các element người dùng đang chọn trong {product}.")
    def get_selection() -> dict[str, Any]:
        return bridge.call("elements.selection")

    @tool("select_elements", WRITE, "Đưa element vào selection set (để chạy lệnh tác động lên vùng chọn).")
    def select_elements(element_ids: list[int], clear_first: bool = True) -> dict[str, Any]:
        return bridge.call("elements.select", {"ids": element_ids, "clear_first": clear_first})

    @tool("delete_elements", DESTRUCTIVE, "XOÁ element theo id (có thể Undo). Chỉ dùng khi người dùng yêu cầu rõ.")
    def delete_elements(element_ids: list[int]) -> dict[str, Any]:
        return bridge.call("elements.delete", {"ids": element_ids})

    # ------------------------------------------------------------------ EC (đối tượng thông minh)
    @tool("ec_summary", READ,
          "Thống kê các EC class (Schema:Class) gắn với element trong model active kèm số lượng và id mẫu. "
          "Dùng ĐẦU TIÊN để biết model có những đối tượng thông minh nào của {product} mà không cần đoán tên schema.")
    def ec_summary(max_elements: int = 20000) -> dict[str, Any]:
        return bridge.call("ec.summary", {"max_elements": max_elements}, timeout_s=600)

    @tool("find_by_ec_class", READ,
          "Tìm element theo tên EC class (chuỗi con, hoặc exact=True) và trả về thuộc tính của class đó. "
          "Lấy tên class từ {p}_ec_summary.")
    def find_by_ec_class(class_name: str, schema: str | None = None, exact: bool = False, limit: int = 50,
                         include_properties: bool = True) -> dict[str, Any]:
        return bridge.call("ec.find", {"class_name": class_name, "schema": schema, "exact": exact, "limit": limit,
                                       "include_properties": include_properties}, timeout_s=600)

    # ------------------------------------------------------------------ key-in / input
    @tool("send_keyins", DESTRUCTIVE,
          "Gửi key-in vào {product} — chạy được MỌI lệnh trên ribbon (như người dùng gõ). Key-in được xếp hàng "
          "và thực thi sau khi tool trả về. delay_ms > 0: gửi lần lượt, nghỉ delay_ms giữa các lần. "
          "Không đoán key-in riêng của sản phẩm — xem resource hướng dẫn.")
    def send_keyins(keyins: list[str], delay_ms: int = 0) -> dict[str, Any]:
        if delay_ms <= 0:
            return bridge.call("keyin.send", {"keyins": keyins})
        sent: list[str] = []
        for k in keyins:
            bridge.call("keyin.send", {"keyins": [k]})
            sent.append(k)
            time.sleep(delay_ms / 1000)
        return {"queued": sent}

    @tool("send_data_point", WRITE, "Gửi data point (click trái) tại toạ độ mét vào lệnh đang chạy.")
    def send_data_point(x: float, y: float, z: float = 0.0, view: int = 1) -> dict[str, Any]:
        return bridge.call("input.data_point", {"point": [x, y, z], "view": view})

    @tool("send_reset", WRITE, "Gửi reset (click phải): kết thúc/huỷ bước hiện tại của lệnh đang chạy.")
    def send_reset() -> dict[str, Any]:
        return bridge.call("input.reset")

    @tool("get_cexpression", READ, "Đọc giá trị một C expression của MicroStation (biến hệ thống/ứng dụng MDL).")
    def get_cexpression(expression: str, app: str | None = None) -> dict[str, Any]:
        return bridge.call("cexpr.get", {"expression": expression, "app": app})

    # ------------------------------------------------------------------ hình học
    @tool("draw_polyline", WRITE, "Vẽ line string (closed=False) hoặc shape kín (closed=True). points: [[x,y,z],...] mét.")
    def draw_polyline(points: list[list[float]], closed: bool = False, level: str | None = None) -> dict[str, Any]:
        return bridge.call("geometry.polyline", {"points": points, "closed": closed, "level": level})

    @tool("create_extrusion", WRITE,
          "Đùn tiết diện 2D bất kỳ theo trục origin→end (mét). loops: [{{\"role\": \"outer\"|\"hole\", "
          "\"points\": [[u, v], ...]}}] (mét) — u ngang (dương = bên trái chiều origin→end; trục thẳng đứng thì "
          "u = X, v = Y), v đứng. Đúng 1 loop outer. section_plane: 'vertical' (tiết diện thẳng đứng) | "
          "'perpendicular' (vuông góc trục 3D; bắt buộc khi trục thẳng đứng).")
    def create_extrusion(origin: list[float], end: list[float], loops: list[dict[str, Any]],
                         section_plane: SectionPlane = "vertical", level: str | None = None) -> dict[str, Any]:
        return bridge.call("geometry.extrusion", {
            "origin": origin, "end": end, "loops": loops, "section_plane": section_plane, "level": level,
        })

    @tool("section_properties", READ,
          "Tính đặc trưng hình học tiết diện đa giác có lỗ rỗng (không cần {product}): A, trọng tâm, yb/yt, "
          "Ix/Iy/Ixy, mômen chính, W (Sb/St), bán kính quán tính. loops như {p}_create_extrusion; đơn vị kết quả "
          "theo đơn vị toạ độ nhập (unit chỉ để gắn nhãn).")
    def section_props(loops: list[dict[str, Any]], unit: str = "mm") -> dict[str, Any]:
        try:
            return section_properties(loops, unit)
        except (ValueError, KeyError, TypeError) as exc:
            raise ToolError(f"Tiết diện không hợp lệ: {exc}") from exc

    # ------------------------------------------------------------------ dùng chung với mọi phần mềm
    register_generic_tools(mcp, bridge, product,
                           fit_view=lambda: bridge.call("keyin.send", {"keyins": ["fit view extended"]}))
