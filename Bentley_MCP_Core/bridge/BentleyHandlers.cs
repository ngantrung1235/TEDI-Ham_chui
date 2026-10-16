using System;
using Bentley.DgnPlatformNET;
using Bentley.MstnPlatformNET;
using BentleyMcp.Handlers;
using McpBridge;
using McpBridge.Handlers;
using McpBridge.Infrastructure;
using BIM = Bentley.Interop.MicroStationDGN;

namespace BentleyMcp
{
    // Bien toan cuc ma script C# (otd_run_csharp / obd_run_csharp) nhin thay truc tiep.
    public sealed class BentleyScriptGlobals : ScriptGlobalsBase
    {
        public Session Session => Session.Instance;
        public DgnFile ActiveFile => Session.Instance.GetActiveDgnFile();
        public DgnModel ActiveModel => Session.Instance.GetActiveDgnModel();
        public BIM.Application App => Bentley.MstnPlatformNET.InteropServices.Utilities.ComApp;
        public double UorPerMeter => ActiveModel.GetModelInfo().UorPerMeter;
    }

    // Diem dang ky handler dung chung cho moi san pham nen MicroStation (OTD, OBD...).
    // Moi ProductInfo.RegisterProductHandlers goi RegisterAll roi them handler rieng cua minh.
    internal static class BentleyHandlers
    {
        public static void RegisterAll(RpcRegistry r)
        {
            SessionHandlers.Register(r);
            LevelHandlers.Register(r);
            ElementHandlers.Register(r);
            InputHandlers.Register(r);
            GeometryHandlers.Register(r);
            EcHandlers.Register(r);
            ScriptHandlers.Register(r, new ScriptConfig
            {
                GlobalsType = typeof(BentleyScriptGlobals),
                CreateGlobals = () => new BentleyScriptGlobals(),
                DefaultImports = new[]
                {
                    "Bentley.DgnPlatformNET", "Bentley.DgnPlatformNET.Elements", "Bentley.GeometryNET",
                    "Bentley.MstnPlatformNET"
                },
                Description = "Compile & chay C# script trong san pham (code, imports, args, timeout_s)"
            });
        }

        public static void Notify(string message, string detail, bool isError)
        {
            if (isError) MessageCenter.Instance.ShowErrorMessage(message, detail, false);
            else MessageCenter.Instance.ShowInfoMessage(message, detail, false);
        }
    }
}
