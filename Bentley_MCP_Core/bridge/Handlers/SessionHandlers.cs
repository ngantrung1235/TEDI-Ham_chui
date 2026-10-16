using System;
using System.IO;
using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;
using BIM = Bentley.Interop.MicroStationDGN;
using McpBridge;
using McpBridge.Infrastructure;

namespace BentleyMcp.Handlers
{
    internal static class SessionHandlers
    {
        public static void Register(RpcRegistry r)
        {
            r.Add("session.info", true, "File/model active, phien ban, don vi", p => Info());

            r.Add("file.open", true, "Mo file DGN (path, read_only)", p =>
            {
                string path = P.ReqStr(p, "path");
                if (!File.Exists(path)) throw new FileNotFoundException("Khong tim thay file DGN.", path);
                Mstn.App.OpenDesignFile(path, P.Bool(p, "read_only", false));
                return Info();
            });

            r.Add("file.save", true, "Luu file active", p =>
            {
                Mstn.App.ActiveDesignFile.Save();
                return new JObject { ["saved"] = Mstn.App.ActiveDesignFile.FullName };
            });

            r.Add("file.models", true, "Liet ke model trong file active", p =>
            {
                var arr = new JArray();
                string active = Mstn.App.ActiveModelReference.Name;
                foreach (BIM.ModelReference m in Mstn.App.ActiveDesignFile.Models)
                {
                    arr.Add(new JObject
                    {
                        ["name"] = m.Name,
                        ["description"] = Mstn.Safe(() => m.Description),
                        ["type"] = Mstn.Safe(() => m.Type.ToString()),
                        ["is_3d"] = Mstn.Safe(() => (bool?)m.Is3D),
                        ["active"] = m.Name == active
                    });
                }
                return arr;
            });
        }

        private static JObject Info()
        {
            var app = Mstn.App;
            var units = Mstn.Safe(() => Units.Of(Mstn.ActiveModel));
            return new JObject
            {
                ["application"] = Mstn.Safe(() => app.Name),
                ["version"] = Mstn.Safe(() => app.Version),
                ["process_path"] = Mstn.Safe(() => System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName),
                ["active_file"] = Mstn.Safe(() => app.ActiveDesignFile.FullName),
                ["read_only"] = Mstn.Safe(() => (bool?)app.ActiveDesignFile.ReadOnly),
                ["active_model"] = Mstn.Safe(() => app.ActiveModelReference.Name),
                ["active_level"] = Mstn.Safe(() => app.ActiveSettings.Level.Name),
                ["is_3d"] = Mstn.Safe(() => (bool?)app.ActiveModelReference.Is3D),
                ["units"] = units?.Describe(),
                ["coordinate_convention"] = "Moi toa do MCP tinh bang MET theo he toa do hien thi (da tru Global Origin).",
                ["bridge"] = BridgeHost.Health()
            };
        }
    }
}
