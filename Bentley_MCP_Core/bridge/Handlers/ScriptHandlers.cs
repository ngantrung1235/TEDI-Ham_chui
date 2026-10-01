using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using Bentley.DgnPlatformNET;
using Bentley.MstnPlatformNET;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;
using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;
using BIM = Bentley.Interop.MicroStationDGN;

namespace BentleyMcp.Handlers
{
    // Bien toan cuc ma script C# nhin thay truc tiep (Session, ActiveModel, App, Print...).
    public sealed class ScriptGlobals
    {
        private readonly StringBuilder _out = new StringBuilder();

        public Session Session => Session.Instance;
        public DgnFile ActiveFile => Session.Instance.GetActiveDgnFile();
        public DgnModel ActiveModel => Session.Instance.GetActiveDgnModel();
        public BIM.Application App => Bentley.MstnPlatformNET.InteropServices.Utilities.ComApp;
        public double UorPerMeter => ActiveModel.GetModelInfo().UorPerMeter;

        public void Print(object value) => _out.AppendLine(value?.ToString() ?? "null");

        internal string Output => _out.ToString();
    }

    // Lop "khong gioi han": compile C# bang Roslyn (tren thread nen) roi chay tren main
    // thread voi day du assembly dang nap trong san pham -> goi duoc MOI API .NET cua
    // MicroStation, OpenRoads (Bentley.CifNET.*), OpenTunnel/OpenBridge, ECObjects... ma
    // khong can build lai add-in. Tat bang <PREFIX>ENABLE_SCRIPTS=0 (vd OBD_MCP_ENABLE_SCRIPTS).
    internal static class ScriptHandlers
    {
        private static readonly string[] DefaultImports =
        {
            "System", "System.Linq", "System.Collections.Generic", "System.IO",
            "Bentley.DgnPlatformNET", "Bentley.DgnPlatformNET.Elements", "Bentley.GeometryNET",
            "Bentley.MstnPlatformNET"
        };

        public static void Register(RpcRegistry r)
        {
            // OnMainThread = false: tu compile tren thread nen, chi phan Run len main thread.
            r.Add("script.csharp", false, "Compile & chay C# script trong san pham (code, imports, timeout_s)", Run);
        }

        private static object Run(JObject p)
        {
            if (!BridgeHost.Config.EnableScripts)
                throw new InvalidOperationException($"C# script dang TAT ({ProductInfo.EnvPrefix}ENABLE_SCRIPTS=0).");

            string code = P.ReqStr(p, "code");
            var imports = DefaultImports.Concat(P.StrList(p, "imports")).Distinct().ToArray();

            ScriptOptions options = ScriptOptions.Default
                .WithReferences(LoadedReferences())
                .WithImports(imports)
                .WithEmitDebugInformation(false);

            Script<object> script = CSharpScript.Create<object>(code, options, typeof(ScriptGlobals));
            var errors = script.Compile().Where(d => d.Severity == DiagnosticSeverity.Error).ToList();
            if (errors.Count > 0)
            {
                return new JObject
                {
                    ["compiled"] = false,
                    ["errors"] = new JArray(errors.Take(30).Select(d => d.ToString()))
                };
            }

            var globals = new ScriptGlobals();
            double timeoutS = P.Dbl(p, "timeout_s", 120);
            object value = MainThread.Invoke(() =>
            {
                // Script dong bo -> RunAsync hoan tat ngay; KHONG duoc await viec can main thread.
                ScriptState<object> state = script.RunAsync(globals).GetAwaiter().GetResult();
                return state.ReturnValue;
            }, TimeSpan.FromSeconds(timeoutS));

            return new JObject
            {
                ["compiled"] = true,
                ["return_value"] = Json.ToToken(value),
                ["return_type"] = value?.GetType().FullName,
                ["output"] = globals.Output
            };
        }

        private static IEnumerable<MetadataReference> LoadedReferences()
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var refs = new List<MetadataReference>();
            foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
            {
                string location;
                try
                {
                    if (a.IsDynamic) continue;
                    location = a.Location;
                }
                catch { continue; }
                if (string.IsNullOrEmpty(location) || !seen.Add(a.GetName().Name)) continue;
                try { refs.Add(MetadataReference.CreateFromFile(location)); }
                catch { /* assembly native/khong doc duoc metadata -> bo qua */ }
            }
            return refs;
        }
    }
}
