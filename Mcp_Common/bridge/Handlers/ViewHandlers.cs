using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using Newtonsoft.Json.Linq;
using McpBridge.Infrastructure;

namespace McpBridge.Handlers
{
    // Chup cua so chinh cua san pham thanh PNG (base64) de LLM "nhin" ket qua sau moi buoc.
    // Dung PrintWindow(PW_RENDERFULLCONTENT) nen van chup duoc khi cua so bi che.
    internal static class ViewHandlers
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct RECT { public int Left, Top, Right, Bottom; }

        [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
        [DllImport("user32.dll")] private static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
        [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr hWnd);

        private const uint PW_RENDERFULLCONTENT = 0x00000002;

        // Lay mau luoi 20x20 diem; coi la "den" neu >= 95% diem co R,G,B deu < 8.
        private static bool IsMostlyBlack(Bitmap bmp)
        {
            int dark = 0, total = 0;
            for (int i = 0; i < 20; i++)
                for (int j = 0; j < 20; j++)
                {
                    Color c = bmp.GetPixel((bmp.Width - 1) * i / 19, (bmp.Height - 1) * j / 19);
                    total++;
                    if (c.R < 8 && c.G < 8 && c.B < 8) dark++;
                }
            return dark * 100 >= total * 95;
        }

        public static void Register(RpcRegistry r)
        {
            r.Add("view.capture", true, "Chup cua so chinh (max_width, method=auto|printwindow|screen) -> PNG base64", p =>
            {
                IntPtr hwnd = Process.GetCurrentProcess().MainWindowHandle;
                if (hwnd == IntPtr.Zero) throw new InvalidOperationException($"Khong tim thay cua so chinh cua {ProductInfo.Name}.");
                if (IsIconic(hwnd)) throw new InvalidOperationException($"Cua so {ProductInfo.Name} dang thu nho (minimize) - hay mo lai roi chup.");
                GetWindowRect(hwnd, out RECT rc);
                int w = rc.Right - rc.Left, h = rc.Bottom - rc.Top;
                if (w <= 0 || h <= 0) throw new InvalidOperationException("Kich thuoc cua so khong hop le.");

                // method: "auto" (mac dinh) = PrintWindow, neu anh gan nhu den (khung nhin GPU/OpenGL/DirectX
                // khong duoc PrintWindow chup) thi chup lai tu man hinh; "printwindow" | "screen" de ep.
                // "screen" yeu cau cua so nam tren cung, khong bi che.
                string method = (P.Str(p, "method", "auto") ?? "auto").ToLowerInvariant();
                using (var full = new Bitmap(w, h, PixelFormat.Format32bppArgb))
                {
                    string used = method;
                    if (method != "screen")
                    {
                        using (Graphics g = Graphics.FromImage(full))
                        {
                            IntPtr hdc = g.GetHdc();
                            try { PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT); }
                            finally { g.ReleaseHdc(hdc); }
                        }
                        used = "printwindow";
                    }
                    if (method == "screen" || (method == "auto" && IsMostlyBlack(full)))
                    {
                        using (Graphics g = Graphics.FromImage(full))
                            g.CopyFromScreen(rc.Left, rc.Top, 0, 0, new Size(w, h));
                        used = "screen";
                    }

                    int maxWidth = Math.Max(P.Int(p, "max_width", 1600), 200);
                    Bitmap output = full;
                    if (w > maxWidth)
                    {
                        output = new Bitmap(maxWidth, (int)Math.Round(h * (double)maxWidth / w));
                        using (Graphics g = Graphics.FromImage(output))
                        {
                            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                            g.DrawImage(full, 0, 0, output.Width, output.Height);
                        }
                    }
                    try
                    {
                        using (var ms = new MemoryStream())
                        {
                            output.Save(ms, ImageFormat.Png);
                            return new JObject
                            {
                                ["mime_type"] = "image/png",
                                ["method"] = used,
                                ["width"] = output.Width,
                                ["height"] = output.Height,
                                ["data_base64"] = Convert.ToBase64String(ms.ToArray())
                            };
                        }
                    }
                    finally
                    {
                        if (!ReferenceEquals(output, full)) output.Dispose();
                    }
                }
            });
        }
    }
}
