using McpBridge.Infrastructure;
namespace McpBridge
{
    internal static class ProductInfo
    {
        public const string Name = "Test", Code = "TST", AddInName = "TstBridge", Keyin = "TST", EnvPrefix = "TST_MCP_", DiscoveryFolder = "Tst";
        public const int DefaultPort = 9999;
        public static void RegisterProductHandlers(RpcRegistry r) { }
        public static void Notify(string m, string d, bool e) { }
    }
}
