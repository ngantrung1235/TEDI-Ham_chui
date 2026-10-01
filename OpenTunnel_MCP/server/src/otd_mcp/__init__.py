"""MCP server cho Bentley OpenTunnel Designer 2026 (qua add-in OTDMcpBridge)."""

from bentley_mcp_core import ProductConfig

__version__ = "0.2.0"

PRODUCT = ProductConfig(
    code="OTD",
    name="OpenTunnel Designer 2026",
    version="26.00.00.83",
    tool_prefix="otd",
    addin_name="OTDMcpBridge",
    keyin="OTDMCP",
    env_prefix="OTD_MCP_",
    discovery_folder="OTDMcp",
)
