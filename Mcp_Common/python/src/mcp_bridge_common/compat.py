"""Import tuong thich ca mcp 1.x (FastMCP) va mcp 2.x (MCPServer)."""

from mcp.types import ToolAnnotations

try:  # mcp >= 2.0
    from mcp.server.mcpserver import Image, MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer, Image  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

__all__ = ["DESTRUCTIVE", "Image", "MCPServer", "READ", "ToolAnnotations", "ToolError", "WRITE"]
