"""MCP server cho Twinmotion 2026.1 (For Revit) - dieu khien o tang giao dien, chi chay tren Windows.

Chay: `tm-mcp` (stdio) tren CHINH may co Twinmotion (khong dung duoc tu xa/Linux). Twinmotion khong co API script,
nen server cung cap: tien trinh + cua so + chup man hinh + chuot/phim + (tuy chon) UI Automation, kem lop an toan.
"""

from __future__ import annotations

import base64
import json
import sys
from typing import Any, Callable, Literal

from mcp_bridge_common import ProductConfig
from mcp_bridge_common.compat import DESTRUCTIVE, READ, WRITE, Image, MCPServer, ToolError
from mcp_bridge_common.registry import make_tool

from . import PRODUCT
from .controller import ControlError, Settings, TwinmotionController
from .guide import GUIDE

INSTRUCTIONS = """\
Điều khiển Twinmotion 2026.1 (For Revit) trên máy này. Twinmotion KHÔNG có API script: điều khiển giao diện theo vòng lặp
tm_screenshot (nhìn) → tm_click/tm_drag/tm_type_text/tm_hotkey (làm) → tm_screenshot (kiểm tra).
- Gọi tm_status trước. Toạ độ tính theo ẢNH GỐC của vùng nội dung cửa sổ; nếu ảnh bị thu nhỏ, chia cho `scale` trong meta.
- Luôn chụp màn hình trước khi bấm và sau khi bấm; chờ tác vụ lâu bằng tm_wait_stable, đừng đoán thời gian.
- Không giết tiến trình (tm_close force) khi chưa được người dùng đồng ý. Đưa chuột vào góc trên-trái màn hình để dừng khẩn cấp.
- Đọc resource tm://guide để biết toạ độ, an toàn và quy trình Revit→Twinmotion.
"""

Target = Literal["main", "active"]
MouseButton = Literal["left", "right", "middle"]


def _guard(fn: Callable[[], Any]) -> Any:
    """Doi ControlError (loi giai thich duoc) thanh ToolError de LLM doc va xu ly."""
    try:
        return fn()
    except ControlError as exc:
        raise ToolError(str(exc)) from exc


def _default_controller() -> TwinmotionController:
    if sys.platform != "win32":
        raise ToolError("MCP Twinmotion chi chay tren Windows (can Win32 + cua so Twinmotion that).")
    from .process import PsutilProcessApi
    from .winapi import WindowsBackend
    return TwinmotionController(WindowsBackend(), PsutilProcessApi(), Settings.from_env())


def create_server(controller: TwinmotionController | None = None) -> MCPServer:
    mcp = MCPServer("twinmotion", instructions=INSTRUCTIONS)
    tool = make_tool(mcp, PRODUCT)
    holder: dict[str, TwinmotionController] = {}
    if controller is not None:
        holder["c"] = controller

    def ctl() -> TwinmotionController:
        if "c" not in holder:
            holder["c"] = _default_controller()
        return holder["c"]

    # ------------------------------------------------------------------ trạng thái / tiến trình
    @tool("status", READ, "Trạng thái {product}: shortcut đã giải ra file exe nào, tiến trình đang chạy, cửa sổ chính, "
                          "màn hình, chế độ chỉ-đọc.")
    def status() -> dict[str, Any]:
        return _guard(lambda: ctl().status())

    @tool("resolve_shortcut", READ, "Đọc shortcut .lnk (mặc định shortcut Twinmotion của máy này) → exe, đối số, thư mục chạy.")
    def resolve_shortcut(path: str | None = None) -> dict[str, Any]:
        from .lnk import ShortcutError, resolve_shortcut as resolve
        try:
            return resolve(path or ctl().settings.shortcut).as_dict()
        except ShortcutError as exc:
            raise ToolError(str(exc)) from exc

    @tool("launch", WRITE,
          "Chạy {product} từ shortcut (hoặc TM_EXE) và chờ cửa sổ chính xuất hiện. Đã chạy rồi thì trả về cửa sổ hiện có "
          "(không mở bản thứ hai trừ khi allow_second=True). args: đối số dòng lệnh. wait_s: thời gian chờ tối đa.")
    def launch(args: list[str] | None = None, wait_s: float = 90.0, allow_second: bool = False) -> dict[str, Any]:
        return _guard(lambda: ctl().launch(args, wait_s, allow_second))

    @tool("open_project", WRITE,
          "Chạy {product} và mở một file (.tm, .udatasmith, .fbx, .skp, .obj, .ifc, .rvt) bằng đối số dòng lệnh. Chỉ khi "
          "Twinmotion CHƯA chạy; cách này chưa kiểm chứng với 2026.1 — xác nhận bằng {p}_screenshot.")
    def open_project(path: str, wait_s: float = 120.0) -> dict[str, Any]:
        return _guard(lambda: ctl().open_project(path, wait_s))

    @tool("close", DESTRUCTIVE,
          "Đóng {product}. Mặc định đóng êm (WM_CLOSE, Twinmotion có thể hỏi lưu → xử lý hộp thoại bằng chuột/phím). "
          "force=True giết tiến trình, MẤT thay đổi chưa lưu — chỉ khi người dùng đồng ý.")
    def close(force: bool = False, wait_s: float = 15.0) -> dict[str, Any]:
        return _guard(lambda: ctl().close(force, wait_s))

    @tool("list_windows", READ, "Các cửa sổ đang hiện của {product} (cửa sổ chính, hộp thoại, menu): hwnd, tiêu đề, vị trí.")
    def list_windows() -> list[dict[str, Any]]:
        return _guard(lambda: [w.as_dict() for w in ctl().app_windows()])

    # ------------------------------------------------------------------ cửa sổ
    @tool("focus", WRITE, "Đưa cửa sổ chính {product} lên trước (khôi phục nếu đang thu nhỏ).")
    def focus() -> dict[str, Any]:
        return _guard(lambda: ctl().focus().as_dict())

    @tool("set_window", WRITE,
          "Đổi trạng thái/kích thước cửa sổ chính: state = maximize | minimize | restore; hoặc đặt x, y, width, height "
          "(pixel). Nên maximize để bố cục giao diện ổn định giữa các lần.")
    def set_window(state: Literal["maximize", "minimize", "restore"] | None = None, x: int | None = None,
                   y: int | None = None, width: int | None = None, height: int | None = None) -> dict[str, Any]:
        return _guard(lambda: ctl().set_window(state, x, y, width, height))

    # ------------------------------------------------------------------ nhìn
    @tool("screenshot", READ,
          "Chụp vùng nội dung của cửa sổ {product} (PNG) kèm meta (width, height, scale, origin_screen). target: main | "
          "active (hộp thoại/menu đang foreground). area: client | window. grid=N (≥20): vẽ lưới toạ độ thật mỗi N px. "
          "mark_x/mark_y: vẽ vòng đỏ tại điểm sắp click. max_width: thu nhỏ ảnh (0 = ảnh gốc); toạ độ trên ảnh thu nhỏ "
          "× (1/scale) = toạ độ thật. Cửa sổ phải hiện trên màn hình và không bị che.")
    def screenshot(target: Target = "main", area: Literal["client", "window"] = "client", grid: int = 0,
                   max_width: int = 1600, mark_x: int | None = None, mark_y: int | None = None) -> list:
        mark = (mark_x, mark_y) if mark_x is not None and mark_y is not None else None
        if grid and grid < 20:
            raise ToolError("grid tối thiểu 20 px (hoặc 0 để tắt).")
        png, meta = _guard(lambda: ctl().screenshot(target, area, grid, max_width, mark))
        return [Image(data=png, format="png"), json.dumps(meta, ensure_ascii=False)]

    @tool("wait_stable", READ,
          "Chờ tới khi vùng nội dung {product} gần như ngừng thay đổi (stable_frames khung liên tiếp, mỗi khung cách "
          "interval_s) — dùng sau khi nhập mô hình / render / lưu. Trả về stable=false nếu hết timeout_s.")
    def wait_stable(timeout_s: float = 60.0, interval_s: float = 1.0, stable_frames: int = 3,
                    threshold: float = 0.002) -> dict[str, Any]:
        if not 0.2 <= interval_s <= 30 or not 1 <= stable_frames <= 20 or not 1 <= timeout_s <= 3600:
            raise ToolError("interval_s 0.2..30, stable_frames 1..20, timeout_s 1..3600.")
        return _guard(lambda: ctl().wait_stable(timeout_s, interval_s, stable_frames, threshold))

    # ------------------------------------------------------------------ chuột / phím
    @tool("click", DESTRUCTIVE,
          "Click chuột tại (x, y) — toạ độ tính từ góc trên-trái vùng nội dung cửa sổ (xem {p}_screenshot). "
          "button: left | right | middle; double=True: nhấp đúp. target: main | active. Từ chối nếu ngoài cửa sổ.")
    def click(x: float, y: float, button: MouseButton = "left", double: bool = False, target: Target = "main") -> dict[str, Any]:
        return _guard(lambda: ctl().click(x, y, button, double, target))

    @tool("move", WRITE, "Di chuyển con trỏ tới (x, y) (hover để hiện tooltip/menu) mà không bấm.")
    def move(x: float, y: float, target: Target = "main") -> dict[str, Any]:
        return _guard(lambda: ctl().move(x, y, target))

    @tool("drag", DESTRUCTIVE,
          "Kéo chuột từ (x1, y1) tới (x2, y2) giữ nút `button` trong duration_ms (50..10000) — xoay/di chuyển camera trong "
          "viewport, kéo thanh trượt. Di chuyển bằng sự kiện tương đối (raw input) để engine Unreal nhận đúng.")
    def drag(x1: float, y1: float, x2: float, y2: float, button: MouseButton = "left", duration_ms: int = 400,
             target: Target = "main") -> dict[str, Any]:
        return _guard(lambda: ctl().drag(x1, y1, x2, y2, button, duration_ms, target))

    @tool("scroll", DESTRUCTIVE, "Cuộn chuột tại (x, y): notches > 0 cuộn lên / zoom vào, < 0 xuống / zoom ra (tối đa 50).")
    def scroll(x: float, y: float, notches: int, target: Target = "main") -> dict[str, Any]:
        return _guard(lambda: ctl().scroll(x, y, notches, target))

    @tool("type_text", DESTRUCTIVE,
          "Gõ văn bản vào ô đang focus (gửi Unicode → gõ được tiếng Việt, đường dẫn). Tối đa 2000 ký tự. Click vào ô "
          "trước. interval_ms > 0: gõ từng ký tự chậm (ô nhập hay mất ký tự).")
    def type_text(text: str, interval_ms: int = 0, target: Target = "main") -> dict[str, Any]:
        return _guard(lambda: ctl().type_text(text, interval_ms, target))

    @tool("hotkey", DESTRUCTIVE,
          "Bấm tổ hợp phím, ví dụ 'ctrl+s', 'ctrl+shift+z', 'alt+f4' (⚠ đóng cửa sổ), 'f11', 'enter', 'esc'. Modifier: "
          "ctrl, shift, alt, win. Chỉ 1 phím thường sau các modifier. Phím dấu câu theo bàn phím US.")
    def hotkey(keys: str, target: Target = "main") -> dict[str, Any]:
        return _guard(lambda: ctl().hotkey(keys, target))

    @tool("press", DESTRUCTIVE,
          "Nhấn một phím `count` lần, mỗi lần giữ hold_ms ms — vd giữ 'w' 800 ms để bay camera tới trước (WASD/QE).")
    def press(key: str, count: int = 1, hold_ms: int = 0, target: Target = "main") -> dict[str, Any]:
        return _guard(lambda: ctl().press(key, count, hold_ms, target))

    # ------------------------------------------------------------------ UI Automation (tuỳ chọn)
    @tool("uia_tree", READ,
          "(Tuỳ chọn, cần pywinauto) Liệt kê phần tử UI Automation của cửa sổ chính: name, control_type, automation_id, "
          "rect. Twinmotion (Unreal Slate) thường lộ rất ít — nếu danh sách ngắn, dùng ảnh chụp + {p}_click.")
    def uia_tree(max_depth: int = 4, name_filter: str | None = None, limit: int = 300) -> dict[str, Any]:
        from . import uia
        return _guard(lambda: uia.tree(ctl().main_hwnd(), max_depth, name_filter, limit))

    @tool("uia_invoke", DESTRUCTIVE,
          "(Tuỳ chọn, cần pywinauto) Kích hoạt phần tử UI Automation theo name hoặc automation_id (Invoke, nếu không được "
          "thì click). control_type lọc thêm (Button, MenuItem...).")
    def uia_invoke(name: str | None = None, automation_id: str | None = None, control_type: str | None = None,
                   index: int = 0, double: bool = False) -> dict[str, Any]:
        from . import uia
        return _guard(lambda: uia.invoke(ctl().focus().hwnd, name, automation_id, control_type, index, double))

    # ------------------------------------------------------------------ tệp
    @tool("find_files", READ,
          "Liệt kê file dự án/trao đổi trong một thư mục (mới nhất trước): .tm, .udatasmith, .fbx, .skp, .rvt, .ifc, .obj... "
          "kinds lọc đuôi (vd ['tm','udatasmith']). Dùng để tìm file Revit vừa xuất hoặc ảnh/phim vừa render "
          "(thêm kinds=['png','jpg','mp4'] cho đầu ra).")
    def find_files(folder: str, kinds: list[str] | None = None, limit: int = 50, recursive: bool = True) -> list[dict[str, Any]]:
        return _guard(lambda: TwinmotionController.find_files(folder, kinds, limit, recursive))

    @mcp.resource("tm://guide", name="tm-guide", mime_type="text/markdown",
                  description="Hướng dẫn điều khiển Twinmotion qua MCP: toạ độ, an toàn, quy trình Revit→Twinmotion")
    def guide() -> str:
        return GUIDE

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
