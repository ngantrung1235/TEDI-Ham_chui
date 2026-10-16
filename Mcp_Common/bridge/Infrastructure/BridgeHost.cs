using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using McpBridge.Handlers;

namespace McpBridge.Infrastructure
{
    // Giao thuc (chi 127.0.0.1), dung chung cho moi san pham (OTD, OBD, Navisworks...):
    //   GET  /health                      -> {"ok":true,"name":...}       (khong can token)
    //   POST /rpc  {"method":..,"params":{..}}  header X-MCP-Token: <token>
    //        -> {"ok":true,"result":..} | {"ok":false,"error":{"type","message","detail"}}
    //   POST /rpc  {"method":"rpc.list"}  -> danh sach method
    internal static class BridgeHost
    {
        public static readonly string Version =
            typeof(BridgeHost).Assembly.GetName().Version?.ToString() ?? "0.0.0";

        private static readonly object Gate = new object();
        private static MiniHttpServer _server;
        private static RpcRegistry _registry;
        private static readonly DateTime LoadedAt = DateTime.Now;

        public static BridgeConfig Config { get; private set; }
        public static bool IsRunning => _server != null;

        public static void Start()
        {
            lock (Gate)
            {
                if (_server != null) return;
                Config = BridgeConfig.Load();
                _registry = BuildRegistry();

                var server = new MiniHttpServer(Handle);
                try
                {
                    server.Start(Config.Port);
                }
                catch (Exception ex)
                {
                    Log($"Khong mo duoc cong {Config.Port}: {ex.Message}");
                    ProductInfo.Notify(
                        $"{ProductInfo.Code} MCP bridge: khong mo duoc cong {Config.Port} (dang bi chiem?). Dat {ProductInfo.EnvPrefix}PORT khac roi '{ProductInfo.Keyin} START'.",
                        ex.ToString(), true);
                    return;
                }
                _server = server;
                WriteDiscovery();
                Log($"Bridge v{Version} chay tai 127.0.0.1:{Config.Port}");
                ProductInfo.Notify(
                    $"{ProductInfo.Code} MCP bridge v{Version} dang chay tai 127.0.0.1:{Config.Port}", Config.DiscoveryFile, false);
            }
        }

        public static void Stop()
        {
            lock (Gate)
            {
                if (_server == null) return;
                _server.Stop();
                _server = null;
                try
                {
                    // Chi xoa file discovery neu la cua chinh process nay (nhieu phien san pham cung luc).
                    if (File.Exists(Config.DiscoveryFile)
                        && (int?)JObject.Parse(File.ReadAllText(Config.DiscoveryFile))["pid"] == Process.GetCurrentProcess().Id)
                        File.Delete(Config.DiscoveryFile);
                }
                catch { /* bo qua */ }
                Log("Bridge da dung.");
            }
        }

        private static RpcRegistry BuildRegistry()
        {
            var r = new RpcRegistry();
            r.Add("rpc.list", false, "Liet ke cac method cua bridge", p =>
            {
                var arr = new JArray();
                foreach (var e in r.All)
                    arr.Add(new JObject { ["name"] = e.Name, ["main_thread"] = e.OnMainThread, ["description"] = e.Description });
                return arr;
            });
            r.Add("ping", false, "Kiem tra bridge con song", p => Health());
            ViewHandlers.Register(r);
            ApiHandlers.Register(r);
            // Handler rieng cua san pham (Bentley: session/level/element/EC/key-in/hinh hoc/script;
            // Navisworks: selection/search/viewpoint/clash...). Dang ky nhu cac method khac.
            ProductInfo.RegisterProductHandlers(r);
            return r;
        }

        public static JObject Health() => new JObject
        {
            ["ok"] = true,
            ["name"] = ProductInfo.AddInName,
            ["product"] = ProductInfo.Name,
            ["version"] = Version,
            ["pid"] = Process.GetCurrentProcess().Id,
            ["process"] = Process.GetCurrentProcess().ProcessName,
            ["runtime"] = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            ["loaded_at"] = LoadedAt.ToString("o"),
            ["scripts_enabled"] = Config?.EnableScripts ?? false,
            ["main_thread_ready"] = MainThread.IsInitialized
        };

        private static HttpResponse Handle(HttpRequest req)
        {
            if (req.Method == "GET" && req.Path.StartsWith("/health", StringComparison.Ordinal))
                return Ok(Health().ToString(Formatting.None));

            if (req.Method != "POST" || !req.Path.StartsWith("/rpc", StringComparison.Ordinal))
                return new HttpResponse { Status = 404, Body = Error("NotFound", "Chi ho tro GET /health va POST /rpc") };

            req.Headers.TryGetValue("X-MCP-Token", out string token);
            if (!TokenEquals(token, Config.Token))
                return new HttpResponse { Status = 401, Body = Error("Unauthorized", "Sai hoac thieu X-MCP-Token (doc lai file discovery).") };

            JObject body;
            try { body = JObject.Parse(string.IsNullOrEmpty(req.Body) ? "{}" : req.Body); }
            catch (Exception ex) { return new HttpResponse { Status = 400, Body = Error("BadJson", ex.Message) }; }

            string method = (string)body["method"];
            JObject p = body["params"] as JObject ?? new JObject();
            if (string.IsNullOrEmpty(method) || !_registry.TryGet(method, out RpcEntry entry))
                return Ok(Error("UnknownMethod", $"Khong co method '{method}'. Goi 'rpc.list' de xem danh sach."));

            var sw = Stopwatch.StartNew();
            try
            {
                double timeoutS = P.Dbl(p, "_timeout_s", 120);
                object result = entry.OnMainThread
                    ? MainThread.Invoke(() => entry.Handler(p), TimeSpan.FromSeconds(timeoutS))
                    : entry.Handler(p);
                var resp = new JObject { ["ok"] = true, ["result"] = Json.ToToken(result), ["elapsed_ms"] = sw.ElapsedMilliseconds };
                return Ok(resp.ToString(Formatting.None));
            }
            catch (Exception ex)
            {
                Exception inner = Unwrap(ex);
                Log($"{method} loi: {inner}");
                return Ok(Error(inner.GetType().Name, inner.Message, inner.ToString()));
            }
        }

        private static Exception Unwrap(Exception ex)
        {
            while ((ex is AggregateException || ex is TargetInvocationException) && ex.InnerException != null)
                ex = ex.InnerException;
            return ex;
        }

        private static HttpResponse Ok(string body) => new HttpResponse { Body = body };

        private static string Error(string type, string message, string detail = null)
        {
            var err = new JObject { ["type"] = type, ["message"] = message };
            if (detail != null) err["detail"] = detail.Length > 4000 ? detail.Substring(0, 4000) : detail;
            return new JObject { ["ok"] = false, ["error"] = err }.ToString(Formatting.None);
        }

        private static bool TokenEquals(string a, string b)
        {
            if (a == null || b == null) return false;
            byte[] x = Encoding.UTF8.GetBytes(a), y = Encoding.UTF8.GetBytes(b);
            if (x.Length != y.Length) return false;
            int diff = 0;
            for (int i = 0; i < x.Length; i++) diff |= x[i] ^ y[i];
            return diff == 0;
        }

        private static void WriteDiscovery()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Config.DiscoveryFile));
            var info = Health();
            info["port"] = Config.Port;
            info["token"] = Config.Token;
            info["url"] = $"http://127.0.0.1:{Config.Port}";
            File.WriteAllText(Config.DiscoveryFile, info.ToString(Formatting.Indented));
        }

        public static void Log(string message)
        {
            try
            {
                string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), ProductInfo.DiscoveryFolder);
                Directory.CreateDirectory(dir);
                File.AppendAllText(Path.Combine(dir, "bridge.log"), $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {message}{Environment.NewLine}");
            }
            catch { /* log khong duoc thi bo qua */ }
        }
    }
}
