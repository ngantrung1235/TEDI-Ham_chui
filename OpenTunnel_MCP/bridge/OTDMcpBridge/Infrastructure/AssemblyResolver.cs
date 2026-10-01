using System;
using System.IO;
using System.Reflection;

namespace OTDMcpBridge.Infrastructure
{
    // MicroStation/OTD tu nap san mot so DLL dung chung (Newtonsoft.Json, System.Memory,
    // System.Collections.Immutable...) voi phien ban KHAC phien ban add-in duoc build.
    // Add-in khong co app.config rieng (binding redirect cua ustation.exe ap cho ca process),
    // nen khi CLR khong tim thay dung version, ta nap ban di kem trong thu muc add-in.
    internal static class AssemblyResolver
    {
        private static bool _installed;
        private static readonly string AddInDir =
            Path.GetDirectoryName(typeof(AssemblyResolver).Assembly.Location);

        public static void Install()
        {
            if (_installed) return;
            _installed = true;
            AppDomain.CurrentDomain.AssemblyResolve += OnResolve;
        }

        private static Assembly OnResolve(object sender, ResolveEventArgs args)
        {
            try
            {
                string simpleName = new AssemblyName(args.Name).Name;

                // Uu tien assembly da nap trong process (bat ke version) de tranh 2 ban cung ten.
                foreach (Assembly loaded in AppDomain.CurrentDomain.GetAssemblies())
                {
                    if (string.Equals(loaded.GetName().Name, simpleName, StringComparison.OrdinalIgnoreCase)
                        && Path.GetDirectoryName(SafeLocation(loaded)) == AddInDir)
                        return loaded;
                }

                string candidate = Path.Combine(AddInDir, simpleName + ".dll");
                return File.Exists(candidate) ? Assembly.LoadFrom(candidate) : null;
            }
            catch
            {
                return null;
            }
        }

        private static string SafeLocation(Assembly a)
        {
            try { return a.IsDynamic ? "" : a.Location; } catch { return ""; }
        }
    }
}
