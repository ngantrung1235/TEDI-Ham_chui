using McpBridge.Infrastructure;

namespace McpBridge
{
    // Thong so rieng cua san pham ma ma nguon chung (Mcp_Common\bridge, Bentley_MCP_Core\bridge) tham chieu.
    internal static class ProductInfo
    {
        public const string Name = "OpenBridge Designer 2026";
        public const string Code = "OBD";
        public const string AddInName = "OBDMcpBridge";   // MdlTaskID, ten DLL, ten key-in tree
        public const string Keyin = "OBDMCP";             // OBDMCP START | STOP | STATUS
        public const string EnvPrefix = "OBD_MCP_";       // OBD_MCP_PORT, OBD_MCP_ENABLE_SCRIPTS, OBD_MCP_DISCOVERY
        public const string DiscoveryFolder = "OBDMcp";   // %LOCALAPPDATA%\OBDMcp\bridge.json + bridge.log
        public const int DefaultPort = 8766;              // khac OTD (8765) de chay song song

        // Dang ky handler Bentley dung chung; handler rieng cua san pham them o day neu can.
        public static void RegisterProductHandlers(RpcRegistry r)
        {
            BentleyMcp.BentleyHandlers.RegisterAll(r);
        }

        public static void Notify(string message, string detail, bool isError) =>
            BentleyMcp.BentleyHandlers.Notify(message, detail, isError);
    }
}
