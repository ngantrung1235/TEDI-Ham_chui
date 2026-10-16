using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace McpBridge.Infrastructure
{
    internal sealed class HttpRequest
    {
        public string Method;
        public string Path;
        public Dictionary<string, string> Headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        public string Body;
    }

    internal sealed class HttpResponse
    {
        public int Status = 200;
        public string ContentType = "application/json; charset=utf-8";
        public string Body = "";
    }

    // HTTP/1.1 toi gian tren TcpListener, CHI bind 127.0.0.1.
    // Khong dung HttpListener vi http.sys doi URL ACL (quyen admin) va khop Host header,
    // de gay loi tren may cong ty bi khoa quyen.
    internal sealed class MiniHttpServer
    {
        private const int MaxHeaderBytes = 64 * 1024;
        private const int MaxBodyBytes = 32 * 1024 * 1024;

        private readonly Func<HttpRequest, HttpResponse> _handler;
        private TcpListener _listener;
        private Thread _acceptThread;
        private volatile bool _running;

        public MiniHttpServer(Func<HttpRequest, HttpResponse> handler)
        {
            _handler = handler;
        }

        public void Start(int port)
        {
            _listener = new TcpListener(IPAddress.Loopback, port);
            _listener.Start();
            _running = true;
            _acceptThread = new Thread(AcceptLoop) { IsBackground = true, Name = ProductInfo.AddInName + "-Accept" };
            _acceptThread.Start();
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); } catch { /* bo qua */ }
        }

        private void AcceptLoop()
        {
            while (_running)
            {
                TcpClient client;
                try { client = _listener.AcceptTcpClient(); }
                catch { if (!_running) break; continue; }
                ThreadPool.QueueUserWorkItem(_ => Serve(client));
            }
        }

        private void Serve(TcpClient client)
        {
            using (client)
            {
                try
                {
                    NetworkStream stream = client.GetStream();
                    stream.ReadTimeout = 30000;
                    HttpResponse response;
                    HttpRequest request = ReadRequest(stream);
                    if (request == null)
                    {
                        response = new HttpResponse { Status = 400, Body = "{\"ok\":false,\"error\":{\"message\":\"bad request\"}}" };
                    }
                    else
                    {
                        try { response = _handler(request); }
                        catch (Exception ex)
                        {
                            response = new HttpResponse { Status = 500, Body = "{\"ok\":false,\"error\":{\"message\":" + Newtonsoft.Json.JsonConvert.ToString(ex.Message) + "}}" };
                        }
                    }
                    WriteResponse(stream, response);
                }
                catch (Exception ex)
                {
                    BridgeHost.Log("HTTP serve error: " + ex.Message);
                }
            }
        }

        private static HttpRequest ReadRequest(Stream stream)
        {
            // Doc header den "\r\n\r\n".
            var header = new MemoryStream();
            int matched = 0;
            byte[] terminator = { 13, 10, 13, 10 };
            while (matched < 4)
            {
                int b = stream.ReadByte();
                if (b < 0 || header.Length > MaxHeaderBytes) return null;
                header.WriteByte((byte)b);
                matched = b == terminator[matched] ? matched + 1 : (b == 13 ? 1 : 0);
            }

            string[] lines = Encoding.ASCII.GetString(header.ToArray()).Split(new[] { "\r\n" }, StringSplitOptions.None);
            string[] requestLine = lines[0].Split(' ');
            if (requestLine.Length < 2) return null;

            var req = new HttpRequest { Method = requestLine[0].ToUpperInvariant(), Path = requestLine[1] };
            for (int i = 1; i < lines.Length; i++)
            {
                int colon = lines[i].IndexOf(':');
                if (colon > 0) req.Headers[lines[i].Substring(0, colon).Trim()] = lines[i].Substring(colon + 1).Trim();
            }

            int length = 0;
            if (req.Headers.TryGetValue("Content-Length", out string cl) && !int.TryParse(cl, out length)) return null;
            if (length < 0 || length > MaxBodyBytes) return null;

            var body = new byte[length];
            int read = 0;
            while (read < length)
            {
                int n = stream.Read(body, read, length - read);
                if (n <= 0) return null;
                read += n;
            }
            req.Body = Encoding.UTF8.GetString(body);
            return req;
        }

        private static void WriteResponse(Stream stream, HttpResponse resp)
        {
            byte[] body = Encoding.UTF8.GetBytes(resp.Body ?? "");
            string head =
                $"HTTP/1.1 {resp.Status} {Reason(resp.Status)}\r\n" +
                $"Content-Type: {resp.ContentType}\r\n" +
                $"Content-Length: {body.Length}\r\n" +
                "Connection: close\r\n\r\n";
            byte[] headBytes = Encoding.ASCII.GetBytes(head);
            stream.Write(headBytes, 0, headBytes.Length);
            stream.Write(body, 0, body.Length);
            stream.Flush();
        }

        private static string Reason(int status)
        {
            switch (status)
            {
                case 200: return "OK";
                case 400: return "Bad Request";
                case 401: return "Unauthorized";
                case 404: return "Not Found";
                default: return "Internal Server Error";
            }
        }
    }
}
