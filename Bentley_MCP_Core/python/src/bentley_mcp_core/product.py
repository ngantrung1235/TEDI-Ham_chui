"""Thong so rieng cua tung san pham (phai khop voi ProductInfo.cs cua add-in tuong ung)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductConfig:
    code: str              # "OTD" / "OBD"
    name: str              # ten hien thi, vd "OpenBridge Designer 2026"
    version: str           # ban da kiem tra, vd "26.00.00.142"
    tool_prefix: str       # tien to ten tool MCP: "otd" -> otd_status, ...
    addin_name: str        # ten DLL / MdlTaskID: "OBDMcpBridge"
    keyin: str             # tien to key-in add-in: "OBDMCP"
    env_prefix: str        # "OBD_MCP_" -> OBD_MCP_URL, OBD_MCP_TOKEN, OBD_MCP_DISCOVERY
    discovery_folder: str  # "%LOCALAPPDATA%\\<discovery_folder>\\bridge.json"
