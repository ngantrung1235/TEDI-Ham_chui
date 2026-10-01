using System;
using System.IO;
using System.Security.Cryptography;

namespace OTDMcpBridge.Infrastructure
{
    // Cau hinh doc tu bien moi truong (dat trong Windows hoac file .cfg cua OTD):
    //   OTD_MCP_PORT            cong TCP loopback (mac dinh 8765)
    //   OTD_MCP_ENABLE_SCRIPTS  "0" de TAT cong cu chay C# script (mac dinh BAT)
    //   OTD_MCP_DISCOVERY       duong dan file discovery (mac dinh %LOCALAPPDATA%\OTDMcp\bridge.json)
    // Token ngau nhien sinh moi lan khoi dong, ghi vao file discovery -> MCP server Python
    // doc file nay de biet port + token (chi user hien tai doc duoc %LOCALAPPDATA%).
    internal sealed class BridgeConfig
    {
        public int Port { get; private set; }
        public string Token { get; private set; }
        public bool EnableScripts { get; private set; }
        public string DiscoveryFile { get; private set; }

        public static BridgeConfig Load()
        {
            var cfg = new BridgeConfig
            {
                Port = int.TryParse(Environment.GetEnvironmentVariable("OTD_MCP_PORT"), out int p) && p > 0 ? p : 8765,
                EnableScripts = Environment.GetEnvironmentVariable("OTD_MCP_ENABLE_SCRIPTS") != "0",
                DiscoveryFile = Environment.GetEnvironmentVariable("OTD_MCP_DISCOVERY")
            };
            if (string.IsNullOrWhiteSpace(cfg.DiscoveryFile))
            {
                cfg.DiscoveryFile = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "OTDMcp", "bridge.json");
            }

            var bytes = new byte[32];
            using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(bytes);
            cfg.Token = Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
            return cfg;
        }
    }
}
