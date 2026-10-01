"""Phan chung cho MCP server dieu khien san pham Bentley nen MicroStation qua add-in bridge."""

from .bridge_client import BridgeClient, BridgeError, BridgeUnavailable
from .product import ProductConfig

__version__ = "0.2.0"
__all__ = ["BridgeClient", "BridgeError", "BridgeUnavailable", "ProductConfig"]
