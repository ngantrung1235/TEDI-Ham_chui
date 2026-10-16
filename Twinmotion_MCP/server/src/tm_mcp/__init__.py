"""MCP server cho Twinmotion 2026.1 (For Revit) - dieu khien giao dien, chi chay tren Windows."""

from mcp_bridge_common import ProductConfig

__version__ = "0.1.0"

# Twinmotion khong co add-in bridge: cac truong addin/keyin/env/discovery khong dung, chi tool_prefix + name duoc dung.
PRODUCT = ProductConfig(
    code="TM",
    name="Twinmotion 2026.1 (For Revit)",
    version="2026.1",
    tool_prefix="tm",
    addin_name="-",
    keyin="-",
    env_prefix="TM_MCP_",
    discovery_folder="-",
)
