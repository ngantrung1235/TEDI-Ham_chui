using BentleyMcp.Infrastructure;

namespace BentleyMcp
{
    // Thong so rieng cua san pham ma ma nguon chung (Bentley_MCP_Core\bridge) tham chieu.
    internal static class ProductInfo
    {
        public const string Name = "OpenTunnel Designer 2026";
        public const string Code = "OTD";
        public const string AddInName = "OTDMcpBridge";   // MdlTaskID, ten DLL, ten key-in tree
        public const string Keyin = "OTDMCP";             // OTDMCP START | STOP | STATUS
        public const string EnvPrefix = "OTD_MCP_";       // OTD_MCP_PORT, OTD_MCP_ENABLE_SCRIPTS, OTD_MCP_DISCOVERY
        public const string DiscoveryFolder = "OTDMcp";   // %LOCALAPPDATA%\OTDMcp\bridge.json + bridge.log
        public const int DefaultPort = 8765;

        // Handler rieng cua OpenTunnel (hien chua co - moi thu tunnel di qua key-in/EC/script).
        public static void RegisterProductHandlers(RpcRegistry r)
        {
        }
    }
}
