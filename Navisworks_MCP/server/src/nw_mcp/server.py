"""MCP server cho Autodesk Navisworks Manage 2025.

Chay: `nw-mcp` (stdio). Server nay chi la lop dich MCP <-> HTTP; moi thao tac that su thuc hien trong plugin
NwMcpBridge nap ben trong Navisworks (xem Navisworks_MCP/bridge). Tool chung (nw_explore_api, nw_run_csharp,
nw_bridge_methods) nam o mcp_bridge_common.registry.
"""

from __future__ import annotations

import base64
from typing import Any, Literal

from mcp_bridge_common import BridgeClient, BridgeError
from mcp_bridge_common.compat import DESTRUCTIVE, READ, WRITE, Image, MCPServer, ToolError
from mcp_bridge_common.registry import make_tool, register_generic_tools, window_capture

from . import PRODUCT, snippets
from .guide import nw_guide
from .reports import write_report
from .scripting import run_snippet

INSTRUCTIONS = """\
Điều khiển Autodesk Navisworks Manage 2025 đang mở trên máy người dùng.
- Gọi nw_status trước tiên. Toạ độ/khoảng cách = mét. Item được định danh bằng `ref` (đường dẫn chỉ số trong cây).
- Luôn đọc mẫu thuộc tính (nw_get_item / nw_search include_properties) trước khi lọc: tên tab/thuộc tính phụ thuộc file nguồn.
- Lọc → nw_search (where[]) ; thao tác trên "selector" ({"refs"} | {"selection":true} | {"where":...}).
- Clash/viewpoint/màu/tệp chạy bằng snippet C#: nếu báo lỗi biên dịch, dùng nw_explore_api để dò tên API đúng rồi nw_run_csharp.
- Đọc resource nw://guide để biết chi tiết. Không tự lưu file; chỉ nw_save_file khi người dùng đồng ý.
"""

Selector = dict[str, Any]
Color = list[int]

# Mo ta tool duoc .format() (placeholder {product}/{p}) nen dau { } literal phai viet doi.
SELECTOR_DOC = ('selector: {{"refs": ["0/3/12"]}} | {{"selection": true}} | {{"where": [{{"category","property","op","value"}}], '
                '"class_name", "geometry_only", "scope_ref", "max_items"}} (xem nw://guide).')


def create_server(client: BridgeClient | None = None) -> MCPServer:
    bridge = client or BridgeClient(PRODUCT)
    mcp = MCPServer("navisworks-manage", instructions=INSTRUCTIONS)
    tool = make_tool(mcp, PRODUCT)
    snip = lambda body, args=None, **kw: run_snippet(bridge, body, args, **kw)  # noqa: E731

    # ------------------------------------------------------------------ tài liệu / cây mô hình (C# lõi)
    @tool("status", READ, "Trạng thái bridge + tài liệu {product} đang mở: file, đơn vị, hệ số ra mét, danh sách model, "
                          "số item đang chọn.")
    def status() -> dict[str, Any]:
        return bridge.call("nw.doc.info")

    @tool("tree", READ, "Duyệt cây mô hình. Không có ref → các model gốc; có ref → con trực tiếp của item đó. "
                        "limit ≤ 5000. Mỗi item có ref, tên, lớp, has_geometry, hidden, số con.")
    def tree(ref: str | None = None, limit: int = 200, include_properties: bool = False) -> dict[str, Any]:
        return bridge.call("nw.tree", {"ref": ref, "limit": limit, "include_properties": include_properties}, timeout_s=300)

    @tool("search", READ,
          "Tìm item. where: [{{category, property, op, value}}] (AND); op = equals | not_equals | contains | starts_with | "
          "ends_with | regex | exists | not_exists | gt | gte | lt | lte (category bỏ trống = mọi tab). class_name: lọc theo "
          "lớp (vd 'Geometry'); geometry_only; scope_ref: chỉ tìm trong nhánh; limit ≤ 2000 + offset phân trang; "
          "include_range: bbox (m); include_properties: kèm toàn bộ thuộc tính; select=True: đồng thời chọn kết quả. "
          "Điều kiện equals đầu tiên có category chạy bằng Search native (nhanh); còn lại duyệt cây.")
    def search(where: list[dict[str, Any]] | None = None, class_name: str | None = None, geometry_only: bool = False,
               scope_ref: str | None = None, limit: int = 100, offset: int = 0, max_scan: int = 500000,
               include_range: bool = False, include_properties: bool = False, select: bool = False) -> dict[str, Any]:
        if not (where or class_name or geometry_only or scope_ref):
            raise ToolError("Cần ít nhất một tiêu chí: where, class_name, geometry_only hoặc scope_ref.")
        return bridge.call("nw.search", {
            "where": where, "class_name": class_name, "geometry_only": geometry_only, "scope_ref": scope_ref,
            "limit": limit, "offset": offset, "max_scan": max_scan, "include_range": include_range,
            "include_properties": include_properties, "select": select,
        }, timeout_s=600)

    @tool("get_item", READ, "Chi tiết 1 item theo ref: lớp, bbox (m), TOÀN BỘ thuộc tính theo tab (Item, Element...).")
    def get_item(ref: str, include_properties: bool = True) -> dict[str, Any]:
        return bridge.call("nw.item.get", {"ref": ref, "include_properties": include_properties})

    @tool("get_selection", READ, "Item người dùng đang chọn trong {product} (kèm ref, bbox).")
    def get_selection(limit: int = 200, include_properties: bool = False) -> dict[str, Any]:
        return bridge.call("nw.selection.get", {"limit": limit, "include_properties": include_properties})

    @tool("select", WRITE, "Đặt vùng chọn theo selector. " + SELECTOR_DOC)
    def select(selector: Selector) -> dict[str, Any]:
        return bridge.call("nw.selection.set", {"selector": selector}, timeout_s=300)

    # ------------------------------------------------------------------ tệp (snippet)
    @tool("open_file", DESTRUCTIVE,
          "Mở file (nwd/nwf/nwc, rvt, ifc, dwg... tuỳ file reader đã cài) trong {product}. append=True: nạp thêm vào "
          "model hiện tại; append=False THAY tài liệu đang mở (thay đổi chưa lưu sẽ mất).")
    def open_file(path: str, append: bool = False) -> Any:
        return snip(snippets.FILE_OPEN, {"path": path, "append": append}, timeout_s=900, what="mở file")

    @tool("save_file", WRITE, "Lưu tài liệu (nwd/nwf). Không truyền path = ghi đè file hiện tại.")
    def save_file(path: str | None = None) -> Any:
        return snip(snippets.FILE_SAVE, {"path": path}, timeout_s=900, what="lưu file")

    # ------------------------------------------------------------------ hiển thị / màu (snippet)
    @tool("set_visibility", WRITE,
          "Ẩn/hiện item. action = hide | show | isolate (chỉ giữ lại các item này và con cháu) | reset_all (hiện lại tất cả; "
          "không cần selector). " + SELECTOR_DOC)
    def set_visibility(action: Literal["hide", "show", "isolate", "reset_all"], selector: Selector | None = None) -> Any:
        if action != "reset_all" and not selector:
            raise ToolError("Cần selector cho action này.")
        return snip(snippets.VISIBILITY, {"action": action, "selector": selector}, timeout_s=300, what="ẩn/hiện")

    @tool("set_appearance", WRITE,
          "Ghi đè màu / độ trong suốt (permanent override) của item. color: [r,g,b] 0-255; transparency: 0 (đặc) → 1 "
          "(trong suốt hoàn toàn); reset=True: bỏ ghi đè của selector; reset_all=True: bỏ mọi ghi đè. " + SELECTOR_DOC)
    def set_appearance(selector: Selector | None = None, color: Color | None = None,
                       transparency: float | None = None, reset: bool = False, reset_all: bool = False) -> Any:
        if not reset_all and not selector:
            raise ToolError("Cần selector (trừ khi reset_all=True).")
        if color is not None and (len(color) != 3 or any(not 0 <= c <= 255 for c in color)):
            raise ToolError("color phải là [r, g, b] với mỗi giá trị 0-255.")
        if transparency is not None and not 0 <= transparency <= 1:
            raise ToolError("transparency phải trong khoảng 0..1.")
        return snip(snippets.APPEARANCE, {"selector": selector, "color": color, "transparency": transparency,
                                          "reset": reset, "reset_all": reset_all}, timeout_s=300, what="tô màu")

    # ------------------------------------------------------------------ viewpoint (snippet)
    @tool("list_viewpoints", READ, "Liệt kê saved viewpoint (cây thư mục: name, path, type).")
    def list_viewpoints() -> Any:
        return snip(snippets.VIEWPOINT_LIST, what="liệt kê viewpoint")

    @tool("save_viewpoint", WRITE, "Lưu khung nhìn hiện tại thành saved viewpoint tên `name`.")
    def save_viewpoint(name: str) -> Any:
        return snip(snippets.VIEWPOINT_SAVE, {"name": name}, what="lưu viewpoint")

    @tool("apply_viewpoint", WRITE, "Chuyển khung nhìn tới saved viewpoint theo tên hoặc đường dẫn 'Thư mục/Tên'.")
    def apply_viewpoint(name: str) -> Any:
        return snip(snippets.VIEWPOINT_APPLY, {"name": name}, what="áp viewpoint")

    @tool("focus_selection", WRITE, "Zoom khung nhìn tới các item đang chọn (chọn bằng {p}_select trước).")
    def focus_selection() -> Any:
        return snip(snippets.FOCUS_SELECTION, what="zoom tới vùng chọn")

    @tool("capture_view", READ,
          "Chụp màn hình {product} (PNG). mode: viewport (chỉ khung nhìn 3D, thử API của View) | window (cả cửa sổ) | auto "
          "(viewport, lỗi thì window). Với window: method auto | printwindow | screen (screen cần cửa sổ ở trên cùng).")
    def capture_view(mode: Literal["auto", "viewport", "window"] = "auto", max_width: int = 1600,
                     method: str = "auto") -> Image:
        if mode in ("auto", "viewport"):
            try:
                shot = snip(snippets.CAPTURE_VIEWPORT, {"width": max_width, "height": int(max_width * 9 / 16)},
                            what="chụp viewport")
                return Image(data=base64.b64decode(shot["data_base64"]), format="png")
            except (ToolError, BridgeError):
                if mode == "viewport":
                    raise
        return window_capture(bridge, max_width, method)

    # ------------------------------------------------------------------ selection set (snippet)
    @tool("list_selection_sets", READ, "Liệt kê selection set / search set (cây thư mục).")
    def list_selection_sets() -> Any:
        return snip(snippets.SELECTION_SET_LIST, what="liệt kê selection set")

    @tool("create_selection_set", WRITE,
          "Tạo selection set (tập chọn cố định) từ selector, đặt tên `name`. " + SELECTOR_DOC)
    def create_selection_set(name: str, selector: Selector) -> Any:
        return snip(snippets.SELECTION_SET_CREATE, {"name": name, "selector": selector}, timeout_s=300,
                    what="tạo selection set")

    @tool("select_selection_set", WRITE, "Chọn các item của một selection set (theo tên hoặc 'Thư mục/Tên').")
    def select_selection_set(name: str) -> Any:
        return snip(snippets.SELECTION_SET_SELECT, {"name": name}, what="chọn selection set")

    # ------------------------------------------------------------------ Clash Detective (snippet)
    clash = dict(headers=snippets.CLASH_HEADERS, what="Clash Detective")

    @tool("clash_list_tests", READ, "Liệt kê Clash Detective test: tên, trạng thái, loại, dung sai (m), tóm tắt kết quả.")
    def clash_list_tests() -> Any:
        return snip(snippets.CLASH_LIST_TESTS, **clash)

    @tool("clash_create_test", WRITE,
          "Tạo clash test giữa hai nhóm A và B rồi (mặc định) chạy ngay. selection_a/selection_b: selector hoặc "
          "{{\"selection_set\": \"tên\"}}. test_type: hard | hard_conservative | clearance | duplicate. tolerance_m: dung sai "
          "(m; hard = độ xuyên tối thiểu, clearance = khoảng cách an toàn). " + SELECTOR_DOC)
    def clash_create_test(name: str, selection_a: Selector, selection_b: Selector,
                          test_type: Literal["hard", "hard_conservative", "clearance", "duplicate"] = "hard",
                          tolerance_m: float = 0.0, self_intersect_a: bool = False, self_intersect_b: bool = False,
                          run: bool = True) -> Any:
        if tolerance_m < 0:
            raise ToolError("tolerance_m không được âm.")
        type_name = {"hard": "Hard", "hard_conservative": "HardConservative", "clearance": "Clearance",
                     "duplicate": "Duplicate"}[test_type]
        return snip(snippets.CLASH_CREATE_TEST, {
            "name": name, "selection_a": selection_a, "selection_b": selection_b, "test_type": type_name,
            "tolerance_m": tolerance_m, "self_intersect_a": self_intersect_a, "self_intersect_b": self_intersect_b,
            "run": run,
        }, timeout_s=1800, **clash)

    @tool("clash_run_test", WRITE, "Chạy lại một clash test theo tên; bỏ trống name = chạy tất cả test.")
    def clash_run_test(name: str | None = None) -> Any:
        return snip(snippets.CLASH_RUN_TEST, {"name": name}, timeout_s=1800, **clash)

    @tool("clash_results", READ,
          "Kết quả của một clash test: tên, trạng thái, khoảng cách (m), điểm va chạm (m), hai cấu kiện (ref + đường dẫn "
          "trong cây). status lọc theo New/Active/Reviewed/Approved/Resolved. limit mặc định 200.")
    def clash_results(test: str, status: str | None = None, limit: int = 200) -> Any:
        return snip(snippets.CLASH_RESULTS, {"name": test, "status": status, "limit": limit}, timeout_s=600, **clash)

    @tool("clash_report", WRITE,
          "Xuất báo cáo va chạm của một test ra file CSV (mở được bằng Excel) hoặc HTML trên máy chạy MCP. "
          "format: csv | html. Ghi tối đa max_results kết quả.")
    def clash_report(test: str, path: str, format: Literal["csv", "html"] = "csv", status: str | None = None,
                     max_results: int = 5000) -> dict[str, Any]:
        data = snip(snippets.CLASH_RESULTS, {"name": test, "status": status, "limit": max_results}, timeout_s=900, **clash)
        written = write_report(path, format, test, data.get("results", []))
        return {"file": written, "format": format, "test": test, "written": len(data.get("results", [])),
                "matched": data.get("matched"), "total_results": data.get("total_results")}

    # ------------------------------------------------------------------ TimeLiner (snippet, chưa kiểm chứng)
    @tool("timeliner_tasks", READ,
          "Liệt kê nhiệm vụ TimeLiner (cây: tên, loại, ngày bắt đầu/kết thúc kế hoạch & thực tế, tiến độ). "
          "Chạy bằng snippet — nếu báo lỗi biên dịch, xem nw://guide mục 4.")
    def timeliner_tasks(limit: int = 500) -> Any:
        return snip(snippets.TIMELINER_TASKS, {"limit": limit}, headers=snippets.TIMELINER_HEADERS,
                    what="TimeLiner")

    # ------------------------------------------------------------------ dùng chung (dò API, script, chẩn đoán)
    register_generic_tools(mcp, bridge, PRODUCT, include_capture=False)

    @mcp.resource("nw://guide", name="nw-guide", mime_type="text/markdown",
                  description="Hướng dẫn chiến lược điều khiển Navisworks qua MCP")
    def guide() -> str:
        return nw_guide(PRODUCT)

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
