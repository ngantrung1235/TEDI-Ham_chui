using System;
using System.Windows.Forms;
using McpBridge.Infrastructure;

namespace McpBridge
{
    // Thong so rieng cua Navisworks ma ma nguon chung (Mcp_Common\bridge) tham chieu.
    internal static class ProductInfo
    {
        public const string Name = "Navisworks Manage 2025";
        public const string Code = "NW";
        public const string AddInName = "NwMcpBridge";       // ten DLL / thu muc plugin
        public const string Keyin = "Add-ins > MCP Bridge";  // Navisworks khong co key-in: dung lenh plugin
        public const string EnvPrefix = "NW_MCP_";           // NW_MCP_PORT, NW_MCP_ENABLE_SCRIPTS, NW_MCP_DISCOVERY
        public const string DiscoveryFolder = "NwMcp";       // %LOCALAPPDATA%\NwMcp\bridge.json + bridge.log
        public const int DefaultPort = 8767;                 // OTD 8765, OBD 8766

        public static void RegisterProductHandlers(RpcRegistry r)
        {
            NwMcp.NwHandlers.RegisterAll(r);
        }

        // Navisworks khong co MessageCenter: thong tin chi ghi log (BridgeHost.Log da lam), chi hien
        // hop thoai khi co loi (vd cong bi chiem) de nguoi dung biet.
        public static void Notify(string message, string detail, bool isError)
        {
            if (isError) MessageBox.Show(message + (string.IsNullOrEmpty(detail) ? "" : "\n\n" + detail), Name + " MCP", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }
}
