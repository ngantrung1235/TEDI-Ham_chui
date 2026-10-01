using System;
using Bentley.DgnPlatformNET;
using Bentley.DgnPlatformNET.Elements;
using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;
using BIM = Bentley.Interop.MicroStationDGN;

namespace BentleyMcp.Handlers
{
    internal static class LevelHandlers
    {
        public static void Register(RpcRegistry r)
        {
            r.Add("levels.list", true, "Liet ke level cua file active", p =>
            {
                var arr = new JArray();
                string active = Mstn.Safe(() => Mstn.App.ActiveSettings.Level.Name);
                foreach (BIM.Level lv in Mstn.App.ActiveDesignFile.Levels)
                {
                    arr.Add(new JObject
                    {
                        ["name"] = lv.Name,
                        ["description"] = Mstn.Safe(() => lv.Description),
                        ["displayed"] = Mstn.Safe(() => (bool?)lv.IsDisplayed),
                        ["active"] = lv.Name == active
                    });
                }
                return arr;
            });

            r.Add("levels.ensure", true, "Tao level neu chua co (name, description, make_active)", p =>
            {
                string name = P.ReqStr(p, "name");
                bool created = EnsureLevel(name, P.Str(p, "description"));
                if (P.Bool(p, "make_active", false))
                    Mstn.App.ActiveSettings.Level = Mstn.App.ActiveDesignFile.Levels[name];
                return new JObject { ["name"] = name, ["created"] = created };
            });
        }

        // Tra ve true neu vua tao moi.
        public static bool EnsureLevel(string name, string description = null)
        {
            var file = Mstn.App.ActiveDesignFile;
            foreach (BIM.Level lv in file.Levels)
                if (string.Equals(lv.Name, name, StringComparison.OrdinalIgnoreCase)) return false;

            BIM.Level created = file.AddNewLevel(name);
            if (!string.IsNullOrEmpty(description)) created.Description = description;
            file.Levels.Rewrite();
            return true;
        }

        // Gan level (tao neu chua co) cho element moi tao, truoc khi AddToModel.
        public static void ApplyLevel(Element el, string levelName)
        {
            if (string.IsNullOrWhiteSpace(levelName)) return;
            EnsureLevel(levelName);
            LevelHandle handle = Mstn.ActiveFile.GetLevelCache().GetLevelByName(levelName);
            if (handle == null || !handle.IsValid)
                throw new InvalidOperationException($"Khong lay duoc level '{levelName}'.");

            var setter = new ElementPropertiesSetter();
            setter.SetLevel(handle.LevelId);
            setter.Apply(el);
        }
    }
}
