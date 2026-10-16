"""MCP server cho Autodesk Navisworks Manage 2025 (qua plugin NwMcpBridge)."""

from mcp_bridge_common import ProductConfig

__version__ = "0.1.0"

PRODUCT = ProductConfig(
    code="NW",
    name="Navisworks Manage 2025",
    version="2025",
    tool_prefix="nw",
    addin_name="NwMcpBridge",
    keyin="Add-ins > MCP Bridge",
    env_prefix="NW_MCP_",
    discovery_folder="NwMcp",
    start_hint=(
        "Hay mo Navisworks Manage 2025 (plugin NwMcpBridge tu khoi dong cung chuong trinh). Neu van khong ket noi: "
        "tab Add-ins > MCP Bridge de bat lai va xem trang thai; kiem tra plugin da duoc cai vao "
        "'...\\Navisworks Manage 2025\\Plugins\\NwMcpBridge\\' (xem scripts\\build_bridge.ps1) va file log "
        "%LOCALAPPDATA%\\NwMcp\\bridge.log."
    ),
)
