using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;

namespace BentleyMcp.Handlers
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

        public static void Register(RpcRegistry r)
        {
            r.Add("view.capture", true, "Chup cua so chinh (max_width) -> PNG base64", p =>
            {
                IntPtr hwnd = Process.GetCurrentProcess().MainWindowHandle;
                if (hwnd == IntPtr.Zero) throw new InvalidOperationException($"Khong tim thay cua so chinh cua {ProductInfo.Name}.");
                if (IsIconic(hwnd)) throw new InvalidOperationException($"Cua so {ProductInfo.Name} dang thu nho (minimize) - hay mo lai roi chup.");
                GetWindowRect(hwnd, out RECT rc);
                int w = rc.Right - rc.Left, h = rc.Bottom - rc.Top;
                if (w <= 0 || h <= 0) throw new InvalidOperationException("Kich thuoc cua so khong hop le.");

                using (var full = new Bitmap(w, h, PixelFormat.Format32bppArgb))
                {
                    using (Graphics g = Graphics.FromImage(full))
                    {
                        IntPtr hdc = g.GetHdc();
                        try { PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT); }
                        finally { g.ReleaseHdc(hdc); }
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
