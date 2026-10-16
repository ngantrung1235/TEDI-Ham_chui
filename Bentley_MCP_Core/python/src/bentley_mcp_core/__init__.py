"""Phan chung cho MCP server dieu khien san pham Bentley nen MicroStation (OTD, OBD...).

Ha tang trung lap (client HTTP, ProductConfig, tool chup man hinh / dò API / script C#) nam o
mcp_bridge_common; goi nay chi them phan rieng cua MicroStation/OpenRoads: tool phien lam viec,
element/EC, key-in, hinh hoc, dac trung tiet dien.
"""

from mcp_bridge_common import BridgeClient, BridgeError, BridgeUnavailable, ProductConfig

__version__ = "0.3.0"
__all__ = ["BridgeClient", "BridgeError", "BridgeUnavailable", "ProductConfig"]
