using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using McpBridge.Infrastructure;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;
using Newtonsoft.Json.Linq;

namespace McpBridge.Handlers
{
    // Lop co so cho "bien toan cuc" ma script C# nhin thay truc tiep. Moi san pham ke thua va
    // them bien rieng (Bentley: Session, ActiveModel, App...; Navisworks: Doc, Selection...).
    // PHAI public: Roslyn bien dich script thanh assembly rieng tham chieu toi kieu nay.
    public abstract class ScriptGlobalsBase
    {
        private readonly StringBuilder _out = new StringBuilder();

        public void Print(object value) => _out.AppendLine(value?.ToString() ?? "null");

        // Tham so dua tu MCP (JSON) vao script: Args["ten"] hoac Arg<T>("ten").
        public JObject Args { get; set; } = new JObject();

        public T Arg<T>(string name, T fallback = default(T)) =>
            Args[name] == null || Args[name].Type == JTokenType.Null ? fallback : Args[name].ToObject<T>();

        internal string Output => _out.ToString();
    }

    internal sealed class ScriptConfig
    {
        public Func<ScriptGlobalsBase> CreateGlobals;
        public Type GlobalsType;
        public string[] DefaultImports = new string[0];
        // Ten assembly (khong .dll) can nap san truoc khi lay danh sach tham chieu cho Roslyn - cac DLL
        // nap lazy (vd Autodesk.Navisworks.Clash) khong co trong AppDomain cho toi khi duoc dung.
        // Tim trong thu muc chua file .exe cua phan mem; nap that bai thi bo qua.
        public string[] PreloadAssemblies = new string[0];
        public string Description = "Compile & chay C# script trong san pham (code, imports, args, timeout_s)";
    }

    // Lop "khong gioi han": compile C# bang Roslyn (tren thread nen) roi chay tren main
    // thread voi day du assembly dang nap trong san pham -> goi duoc MOI API .NET cua
    // MicroStation/OpenRoads/OpenBridge/Navisworks... ma khong can build lai add-in.
    // Tat bang <PREFIX>ENABLE_SCRIPTS=0 (vd OBD_MCP_ENABLE_SCRIPTS, NW_MCP_ENABLE_SCRIPTS).
    //
    // Mot so tool MCP "kho kiem chung" (clash, timeliner...) cung duoc cai dat bang script nhung
    // nhung vao phia Python: loi API se hien ra luc chay (errors[]) va sua duoc ma khong phai
    // build lai add-in.
    internal static class ScriptHandlers
    {
        private static readonly string[] CommonImports =
        {
            "System", "System.Linq", "System.Collections.Generic", "System.IO", "Newtonsoft.Json.Linq"
        };

        public static void Register(RpcRegistry r, ScriptConfig config)
        {
            // OnMainThread = false: tu compile tren thread nen, chi phan Run len main thread.
            r.Add("script.csharp", false, config.Description, p => Run(p, config));
        }

        private static object Run(JObject p, ScriptConfig config)
        {
            if (!BridgeHost.Config.EnableScripts)
                throw new InvalidOperationException($"C# script dang TAT ({ProductInfo.EnvPrefix}ENABLE_SCRIPTS=0).");

            string code = P.ReqStr(p, "code");
            var imports = CommonImports.Concat(config.DefaultImports).Concat(P.StrList(p, "imports")).Distinct().ToArray();

            Preload(config.PreloadAssemblies);
            ScriptOptions options = ScriptOptions.Default
                .WithReferences(LoadedReferences())
                .WithImports(imports)
                .WithEmitDebugInformation(false);

            Script<object> script = CSharpScript.Create<object>(code, options, config.GlobalsType);
            var errors = script.Compile().Where(d => d.Severity == DiagnosticSeverity.Error).ToList();
            if (errors.Count > 0)
            {
                return new JObject
                {
                    ["compiled"] = false,
                    ["errors"] = new JArray(errors.Take(30).Select(d => d.ToString()))
                };
            }

            ScriptGlobalsBase globals = config.CreateGlobals();
            globals.Args = p["args"] as JObject ?? new JObject();
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

        private static void Preload(string[] names)
        {
            if (names == null || names.Length == 0) return;
            string dir = null;
            try { dir = System.IO.Path.GetDirectoryName(System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName); }
            catch { /* khong doc duoc duong dan exe */ }
            foreach (string name in names)
            {
                try
                {
                    if (AppDomain.CurrentDomain.GetAssemblies().Any(a => string.Equals(a.GetName().Name, name, StringComparison.OrdinalIgnoreCase)))
                        continue;
                    string file = dir == null ? null : System.IO.Path.Combine(dir, name + ".dll");
                    if (file != null && System.IO.File.Exists(file)) Assembly.LoadFrom(file);
                    else Assembly.Load(name);
                }
                catch { /* khong co assembly nay trong ban cai -> bo qua */ }
            }
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
