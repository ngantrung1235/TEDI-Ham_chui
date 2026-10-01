"""MCP server cho Bentley OpenBridge Designer 2026 (qua add-in OBDMcpBridge)."""

from bentley_mcp_core import ProductConfig

__version__ = "0.2.0"

PRODUCT = ProductConfig(
    code="OBD",
    name="OpenBridge Designer 2026",
    version="26.00.00.142",
    tool_prefix="obd",
    addin_name="OBDMcpBridge",
    keyin="OBDMCP",
    env_prefix="OBD_MCP_",
    discovery_folder="OBDMcp",
)
