"""Phan trung lap dung chung cho MCP server dieu khien phan mem Windows qua add-in bridge."""

from .bridge_client import BridgeClient, BridgeError, BridgeUnavailable
from .product import ProductConfig

__version__ = "0.1.0"
__all__ = ["BridgeClient", "BridgeError", "BridgeUnavailable", "ProductConfig"]
