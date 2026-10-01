using Bentley.MstnPlatformNET;
using BentleyMcp.Infrastructure;

namespace BentleyMcp
{
    // Handler cua bang key-in trong commands.xml. Chu ky (string unparsed) la bat buoc.
    public static class KeyinCommands
    {
        public static void Start(string unparsed)
        {
            MainThread.Initialize();
            BridgeHost.Start();
            Status(unparsed);
        }

        public static void Stop(string unparsed)
        {
            BridgeHost.Stop();
            MessageCenter.Instance.ShowInfoMessage($"{ProductInfo.Code} MCP bridge: da dung.", null, false);
        }

        public static void Status(string unparsed)
        {
            string msg = BridgeHost.IsRunning
                ? $"{ProductInfo.Code} MCP bridge dang chay tai 127.0.0.1:{BridgeHost.Config.Port} (C# script: {(BridgeHost.Config.EnableScripts ? "BAT" : "TAT")})"
                : $"{ProductInfo.Code} MCP bridge dang dung. Go '{ProductInfo.Keyin} START' de chay.";
            MessageCenter.Instance.ShowInfoMessage(msg, BridgeHost.Config?.DiscoveryFile, false);
        }
    }
}
