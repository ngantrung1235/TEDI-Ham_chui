using System;
using System.Runtime.CompilerServices;
using System.Windows.Forms;
using Autodesk.Navisworks.Api.Plugins;
using McpBridge;
using McpBridge.Infrastructure;

namespace NwMcp
{
    // Khoi dong/dung bridge. Tach rieng de AssemblyResolver duoc cai TRUOC khi JIT bat ky method nao
    // tham chieu Newtonsoft.Json / Roslyn (Navisworks co the da nap ban khac cua cac DLL nay).
    internal static class NwBootstrap
    {
        public static void Start(bool rebindMainThread)
        {
            AssemblyResolver.Install();
            StartCore(rebindMainThread);
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void StartCore(bool rebindMainThread)
        {
            if (rebindMainThread) MainThread.Rebind(); else MainThread.Initialize();
            BridgeHost.Start();
        }

        public static void Stop() => BridgeHost.Stop();

        public static string StatusText() => BridgeHost.IsRunning
            ? $"{ProductInfo.Name}: MCP bridge DANG CHAY tai 127.0.0.1:{BridgeHost.Config.Port}\n" +
              $"C# script: {(BridgeHost.Config.EnableScripts ? "BAT" : "TAT")}\nFile discovery: {BridgeHost.Config.DiscoveryFile}"
            : $"{ProductInfo.Name}: MCP bridge DANG DUNG.";
    }

    // Tu chay khi Navisworks khoi dong (EventWatcherPlugin.OnLoaded) - khong can bam gi.
    [PluginAttribute("NwMcpBridge.AutoStart", "TEDI", DisplayName = "MCP Bridge (tu khoi dong)",
        ToolTip = "Tu dong mo MCP bridge khi Navisworks khoi dong")]
    public class AutoStartPlugin : EventWatcherPlugin
    {
        public override void OnLoaded()
        {
            try { NwBootstrap.Start(false); }
            catch (Exception ex) { BridgeHost.Log("AutoStart loi: " + ex); }
        }

        public override void OnUnloading() => NwBootstrap.Stop();
    }

    // Lenh dieu khien tren tab Add-ins:  khong tham so = bat (gan lai UI thread) + hien trang thai.
    // Tham so: start | stop | status.
    [PluginAttribute("NwMcpBridge.Control", "TEDI", DisplayName = "MCP Bridge",
        ToolTip = "Bat / tat / xem trang thai MCP bridge (Claude)")]
    [AddInPluginAttribute(AddInLocation.AddIn)]
    public class ControlPlugin : AddInPlugin
    {
        public override int Execute(params string[] parameters)
        {
            string cmd = parameters != null && parameters.Length > 0 ? parameters[0].ToLowerInvariant() : "start";
            switch (cmd)
            {
                case "stop":
                    NwBootstrap.Stop();
                    break;
                case "status":
                    break;
                default:
                    // Execute chay tren UI thread that -> gan lai hang doi main thread vao day.
                    NwBootstrap.Start(true);
                    break;
            }
            MessageBox.Show(NwBootstrap.StatusText(), ProductInfo.Name + " MCP", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
    }
}
