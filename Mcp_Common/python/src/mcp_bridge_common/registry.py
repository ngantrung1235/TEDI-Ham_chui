"""Dang ky tool MCP co tien to theo phan mem + cac tool trung lap (khong phu thuoc hang)."""

from __future__ import annotations

import base64
import time
from typing import Any, Callable

from .bridge_client import BridgeClient
from .compat import DESTRUCTIVE, READ, Image, MCPServer
from .product import ProductConfig


def make_tool(mcp: MCPServer, product: ProductConfig) -> Callable:
    """Tra ve decorator tool(suffix, annotations, description) -> dang ky '<prefix>_<suffix>'.

    description duoc format voi {product} (ten phan mem) va {p} (tien to tool); dau { } literal
    trong mo ta phai viet {{ }}.
    """
    prefix, pname = product.tool_prefix, product.name

    def tool(suffix: str, annotations, description: str) -> Callable:
        return mcp.tool(name=f"{prefix}_{suffix}", annotations=annotations,
                        description=description.format(product=pname, p=prefix))

    return tool


def window_capture(bridge: BridgeClient, max_width: int = 1600, method: str = "auto") -> Image:
    """Chup cua so chinh cua phan mem qua bridge (view.capture). method: auto | printwindow | screen."""
    shot = bridge.call("view.capture", {"max_width": max_width, "method": method})
    return Image(data=base64.b64decode(shot["data_base64"]), format="png")


def register_generic_tools(mcp: MCPServer, bridge: BridgeClient, product: ProductConfig, *,
                           fit_view: Callable[[], None] | None = None, include_capture: bool = True) -> None:
    """capture_view, explore_api, run_csharp, bridge_methods - co o MOI phan mem co add-in bridge.

    fit_view: ham phan mem-cu-the dua khung nhin ve toan canh truoc khi chup (None = khong ho tro fit).
    include_capture: False khi phan mem tu dinh nghia capture_view rieng (vd Navisworks chup viewport).
    """
    tool = make_tool(mcp, product)

    if include_capture:
        @tool("capture_view", READ,
              "Chụp màn hình cửa sổ {product} (PNG) để kiểm tra trực quan. fit=True: đưa khung nhìn về toàn cảnh "
              "(nếu phần mềm hỗ trợ) rồi chụp. method: auto (PrintWindow, nếu ảnh đen do khung nhìn GPU thì chụp "
              "lại từ màn hình) | printwindow | screen (cần cửa sổ nằm trên cùng, không bị che).")
        def capture_view(fit: bool = False, max_width: int = 1600, method: str = "auto") -> Image:
            if fit and fit_view is not None:
                fit_view()
                time.sleep(1.0)
            return window_capture(bridge, max_width, method)

    @tool("explore_api", READ,
          "Dò API .NET đang nạp trong {product} bằng reflection. Chỉ assembly_filter → danh sách assembly; "
          "có type_filter → type public (+ chữ ký member nếu include_members). Dùng TRƯỚC {p}_run_csharp.")
    def explore_api(assembly_filter: str | None = None, type_filter: str | None = None,
                    include_members: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        if type_filter is None and not include_members:
            return bridge.call("api.assemblies", {"filter": assembly_filter})
        return bridge.call("api.types", {"assembly_filter": assembly_filter, "type_filter": type_filter,
                                         "include_members": include_members, "limit": limit})

    @tool("run_csharp", DESTRUCTIVE,
          "Biên dịch & chạy C# script BÊN TRONG {product} trên main thread, tham chiếu mọi assembly đang nạp. "
          "Giá trị biểu thức cuối → return_value; Print(x) → output; lỗi biên dịch → errors. "
          "args: JSON truyền vào script, đọc bằng Arg<T>(\"tên\") hoặc Args[\"tên\"]. "
          "Biến có sẵn khác nhau theo phần mềm (xem resource hướng dẫn). Script chặn giao diện khi chạy.")
    def run_csharp(code: str, imports: list[str] | None = None, args: dict[str, Any] | None = None,
                   timeout_s: float = 120) -> dict[str, Any]:
        return bridge.call("script.csharp", {"code": code, "imports": imports or [], "args": args or {},
                                             "timeout_s": timeout_s}, timeout_s=timeout_s + 30)

    @tool("bridge_methods", READ, "(Chẩn đoán) Danh sách method RPC mà add-in bridge cung cấp.")
    def bridge_methods() -> list[dict[str, Any]]:
        return bridge.call("rpc.list")
