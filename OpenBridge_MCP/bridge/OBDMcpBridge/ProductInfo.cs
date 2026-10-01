using BentleyMcp.Infrastructure;

namespace BentleyMcp
{
    // Thong so rieng cua san pham ma ma nguon chung (Bentley_MCP_Core\bridge) tham chieu.
    internal static class ProductInfo
    {
        public const string Name = "OpenBridge Designer 2026";
        public const string Code = "OBD";
        public const string AddInName = "OBDMcpBridge";   // MdlTaskID, ten DLL, ten key-in tree
        public const string Keyin = "OBDMCP";             // OBDMCP START | STOP | STATUS
        public const string EnvPrefix = "OBD_MCP_";       // OBD_MCP_PORT, OBD_MCP_ENABLE_SCRIPTS, OBD_MCP_DISCOVERY
        public const string DiscoveryFolder = "OBDMcp";   // %LOCALAPPDATA%\OBDMcp\bridge.json + bridge.log
        public const int DefaultPort = 8766;              // khac OTD (8765) de chay song song

        // Handler rieng cua OpenBridge: hinh hoc cau (dam, ban mat cau, tru) duoc tinh o phia
        // Python roi dung chung geometry.extrusion; doi tuong OBM native di qua ec.* / key-in / script.
        public static void RegisterProductHandlers(RpcRegistry r)
        {
        }
    }
}
