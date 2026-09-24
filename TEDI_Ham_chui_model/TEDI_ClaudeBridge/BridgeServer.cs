using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Autodesk.Revit.UI;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace TEDI_ClaudeBridge
{
    // Cau noi Claude <-> Revit: mo 1 cong TCP CHI tren 127.0.0.1 (khong nhan ket noi tu
    // may khac), nhan tung dong JSON:
    //   {"token": "...", "method": "get_document_info", "params": {...}}
    // va tra ve 1 dong JSON:
    //   {"ok": true, "result": ...}  hoac  {"ok": false, "error": "..."}
    //
    // Port + token ngau nhien duoc ghi vao ConnectionFilePath de MCP server
    // (ClaudeRevitMCP/revit_mcp_server.py) tu doc - nguoi dung khong can cau hinh tay.
    // Token doi moi lan bat cau noi, nen chuong trinh khac tren may muon goi lenh thi
    // phai doc duoc file trong %APPDATA% cua dung user nay.
    //
    // Chi dung API co tren ca .NET Framework 4.8 (Revit 2024) va .NET 10 (Revit 2027).
    internal static class BridgeServer
    {
        public const int DefaultPort = 48884;
        private const int PortSearchRange = 10;
        private const int MaxRequestChars = 1_000_000;
        private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(60);

        public static string ConnectionFilePath { get; } = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "TEDI-Ham_chui", "claude_bridge.json");

        private static BridgeEventHandler? _handler;
        private static ExternalEvent? _externalEvent;
        private static TcpListener? _listener;
        private static string _token = "";

        public static bool IsRunning => _listener != null;
        public static int Port { get; private set; }

        // PHAI goi trong API context (OnStartup hoac Execute cua 1 lenh) vi
        // ExternalEvent.Create chi hop le o do.
        public static void Initialize()
        {
            if (_externalEvent != null)
                return;
            _handler = new BridgeEventHandler();
            _externalEvent = ExternalEvent.Create(_handler);
        }

        public static void Start(string revitVersion)
        {
            if (IsRunning)
                return;
            Initialize();

            int basePort = DefaultPort;
            if (int.TryParse(Environment.GetEnvironmentVariable("TEDI_REVIT_BRIDGE_PORT"), out int envPort))
                basePort = envPort;

            TcpListener? listener = null;
            for (int port = basePort; port < basePort + PortSearchRange && listener == null; port++)
            {
                try
                {
                    var candidate = new TcpListener(IPAddress.Loopback, port);
                    candidate.Start();
                    listener = candidate;
                    Port = port;
                }
                catch (SocketException)
                {
                    // Cong dang bi chiem (vd. mo 2 phien Revit) -> thu cong ke tiep.
                }
            }
            if (listener == null)
                throw new InvalidOperationException(
                    $"Khong mo duoc cong TCP nao trong khoang {basePort}-{basePort + PortSearchRange - 1}.");

            _listener = listener;
            _token = NewToken();

            WriteConnectionFile(revitVersion);
            _ = AcceptLoopAsync(listener);
        }

        public static void Stop()
        {
            // Chua bat thi khong xoa file: co the la file cua 1 phien Revit khac dang chay.
            if (!IsRunning)
                return;

            // Doi token de ket noi dang mo (neu co) khong goi tiep duoc sau khi tat.
            _token = NewToken();
            _listener?.Stop();
            _listener = null;
            try
            {
                if (File.Exists(ConnectionFilePath))
                    File.Delete(ConnectionFilePath);
            }
            catch (IOException)
            {
            }
        }

        private static string NewToken()
        {
            var bytes = new byte[24];
            using (var rng = RandomNumberGenerator.Create())
                rng.GetBytes(bytes);
            return BitConverter.ToString(bytes).Replace("-", "");
        }

        private static void WriteConnectionFile(string revitVersion)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ConnectionFilePath)!);
            var info = new JObject
            {
                ["host"] = "127.0.0.1",
                ["port"] = Port,
                ["token"] = _token,
                ["revit_version"] = revitVersion,
                ["process_id"] = Process.GetCurrentProcess().Id,
                ["started_at"] = DateTime.Now.ToString("o"),
            };
            File.WriteAllText(ConnectionFilePath, info.ToString(Formatting.Indented));
        }

        private static async Task AcceptLoopAsync(TcpListener listener)
        {
            while (true)
            {
                TcpClient client;
                try
                {
                    client = await listener.AcceptTcpClientAsync().ConfigureAwait(false);
                }
                catch (ObjectDisposedException)
                {
                    break; // listener.Stop()
                }
                catch (SocketException)
                {
                    break;
                }
                catch (InvalidOperationException)
                {
                    break;
                }
                _ = HandleClientAsync(client);
            }
        }

        private static async Task HandleClientAsync(TcpClient client)
        {
            using (client)
            {
                try
                {
                    NetworkStream stream = client.GetStream();
                    var reader = new StreamReader(stream, new UTF8Encoding(false));
                    var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };

                    while (true)
                    {
                        string? line = await reader.ReadLineAsync().ConfigureAwait(false);
                        if (line == null)
                            break;
                        if (string.IsNullOrWhiteSpace(line))
                            continue;

                        JObject response = await ProcessLineAsync(line).ConfigureAwait(false);
                        await writer.WriteLineAsync(response.ToString(Formatting.None)).ConfigureAwait(false);
                    }
                }
                catch (IOException)
                {
                    // Client ngat ket noi giua chung.
                }
                catch (ObjectDisposedException)
                {
                }
            }
        }

        private static async Task<JObject> ProcessLineAsync(string line)
        {
            JToken? requestId = null;
            try
            {
                if (line.Length > MaxRequestChars)
                    return Error(null, "Yeu cau qua lon.");

                if (!(JToken.Parse(line) is JObject request))
                    return Error(null, "Yeu cau phai la 1 JSON object.");
                requestId = request["id"];

                if (!IsRunning || !TokenEquals(request.Value<string>("token") ?? "", _token))
                    return Error(requestId, "Sai token. Hay tat/bat lai cau noi trong Revit va thu lai.");

                var bridgeRequest = new BridgeRequest
                {
                    Method = request.Value<string>("method") ?? "",
                    Params = request["params"] as JObject ?? new JObject(),
                };

                _handler!.Enqueue(bridgeRequest);
                ExternalEventRequest raised = _externalEvent!.Raise();
                if (raised == ExternalEventRequest.Denied || raised == ExternalEventRequest.TimedOut)
                {
                    bridgeRequest.Completion.TrySetCanceled();
                    return Error(requestId, $"Revit tu choi ExternalEvent ({raised}).");
                }

                Task finished = await Task.WhenAny(bridgeRequest.Completion.Task, Task.Delay(RequestTimeout)).ConfigureAwait(false);
                if (finished != bridgeRequest.Completion.Task)
                {
                    bridgeRequest.Completion.TrySetCanceled();
                    return Error(requestId,
                        "Revit khong phan hoi trong " + RequestTimeout.TotalSeconds + " giay. " +
                        "Co the dang mo 1 hop thoai/lenh khac - hay dong no roi thu lai.");
                }

                JToken? result = await bridgeRequest.Completion.Task.ConfigureAwait(false);
                return new JObject { ["id"] = requestId, ["ok"] = true, ["result"] = result };
            }
            catch (Exception ex)
            {
                return Error(requestId, ex.Message);
            }
        }

        // So sanh thoi gian hang (khong lo do dai khop qua thoi gian phan hoi).
        private static bool TokenEquals(string a, string b)
        {
            byte[] x = Encoding.UTF8.GetBytes(a), y = Encoding.UTF8.GetBytes(b);
            int diff = x.Length ^ y.Length;
            for (int i = 0; i < Math.Min(x.Length, y.Length); i++)
                diff |= x[i] ^ y[i];
            return diff == 0;
        }

        private static JObject Error(JToken? id, string message) =>
            new JObject { ["id"] = id, ["ok"] = false, ["error"] = message };
    }
}
