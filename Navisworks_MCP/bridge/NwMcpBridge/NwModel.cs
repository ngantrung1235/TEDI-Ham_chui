using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Autodesk.Navisworks.Api;
using McpBridge.Infrastructure;
using Newtonsoft.Json.Linq;
using NwApp = Autodesk.Navisworks.Api.Application;

namespace NwMcp
{
    // Tien ich truy cap Navisworks. Chi goi tren main thread.
    //
    // Nguyen tac: ma C# loi chi dung nhung API Navisworks chac chan nhat (Document, ModelItem va cay con,
    // PropertyCategories, Search/SearchCondition, CurrentSelection). Thuoc tinh chi dung de HIEN THI
    // (ten file model, don vi, GUID, bounding box...) doc bang reflection (Nw.Get/Str) de neu ten
    // thanh vien khac giua cac ban Navisworks thi chi mat truong do, KHONG vo build.
    internal static class Nw
    {
        public static Document Doc
        {
            get
            {
                Document d = NwApp.ActiveDocument;
                if (d == null) throw new InvalidOperationException("Navisworks chua co tai lieu nao dang mo.");
                return d;
            }
        }

        // Doc property/field public theo ten; khong co hoac loi -> null.
        public static object Get(object target, string member)
        {
            if (target == null) return null;
            try
            {
                Type t = target.GetType();
                PropertyInfo pi = t.GetProperty(member, BindingFlags.Public | BindingFlags.Instance);
                if (pi != null && pi.GetIndexParameters().Length == 0) return pi.GetValue(target, null);
                FieldInfo fi = t.GetField(member, BindingFlags.Public | BindingFlags.Instance);
                return fi != null ? fi.GetValue(target) : null;
            }
            catch { return null; }
        }

        public static string Str(object target, string member)
        {
            object v = Get(target, member);
            return v == null ? null : v.ToString();
        }

        public static string UnitsName(Document doc) => Str(doc, "Units");

        // He so quy doi 1 don vi tai lieu -> met (theo ten enum Autodesk.Navisworks.Api.Units).
        public static double MetersPerUnit(Document doc)
        {
            switch ((UnitsName(doc) ?? "").ToLowerInvariant())
            {
                case "meters": return 1.0;
                case "centimeters": return 0.01;
                case "millimeters": return 0.001;
                case "kilometers": return 1000.0;
                case "inches": return 0.0254;
                case "feet": return 0.3048;
                case "yards": return 0.9144;
                case "miles": return 1609.344;
                case "microns": return 1e-6;
                case "mils": return 2.54e-5;
                case "microinches": return 2.54e-8;
                default: return 1.0;   // khong ro: giu nguyen so (units_known=false trong doc.info)
            }
        }

        public static bool UnitsKnown(Document doc)
        {
            string u = (UnitsName(doc) ?? "").ToLowerInvariant();
            return new[] { "meters", "centimeters", "millimeters", "kilometers", "inches", "feet", "yards", "miles", "microns", "mils", "microinches" }.Contains(u);
        }

        // Bounding box [minX, minY, minZ, maxX, maxY, maxZ] theo don vi tai lieu; khong lay duoc -> null.
        public static double[] BBox(ModelItem item)
        {
            try
            {
                MethodInfo m = item.GetType().GetMethod("BoundingBox", Type.EmptyTypes);
                object box = m == null ? null : m.Invoke(item, null);
                object min = Get(box, "Min"), max = Get(box, "Max");
                if (min == null || max == null) return null;
                double[] v =
                {
                    Convert.ToDouble(Get(min, "X")), Convert.ToDouble(Get(min, "Y")), Convert.ToDouble(Get(min, "Z")),
                    Convert.ToDouble(Get(max, "X")), Convert.ToDouble(Get(max, "Y")), Convert.ToDouble(Get(max, "Z"))
                };
                if (v.Any(double.IsNaN) || v.Any(double.IsInfinity) || v[0] > v[3] || v[1] > v[4]) return null;
                return v;
            }
            catch { return null; }
        }
    }

    // "ref" = duong dan chi so trong cay mo hinh: "<chi so model>/<chi so con>/<chi so con>/..."
    // Navisworks khong co ID so on dinh cho ModelItem trong .NET API, nen dung duong dan chi so.
    // Ref on dinh chung nao cay mo hinh chua doi (khong append/xoa model, khong refresh file nguon).
    internal static class NwRefs
    {
        public static string ToRef(Document doc, ModelItem item)
        {
            var path = new List<int>();
            ModelItem cur = item;
            while (cur.Parent != null)
            {
                int i = IndexOf(cur.Parent.Children, cur);
                if (i < 0) return null;
                path.Add(i);
                cur = cur.Parent;
            }
            int m = IndexOf(doc.Models.RootItems, cur);
            if (m < 0) return null;
            path.Add(m);
            path.Reverse();
            return string.Join("/", path);
        }

        public static ModelItem Resolve(Document doc, string r)
        {
            if (string.IsNullOrWhiteSpace(r)) throw new ArgumentException("ref rong.");
            int[] parts;
            try { parts = r.Split('/').Select(s => int.Parse(s.Trim())).ToArray(); }
            catch { throw new ArgumentException($"ref '{r}' khong hop le (dang 'm/i/j/...' voi cac so nguyen)."); }

            ModelItem cur = doc.Models.RootItems.ElementAtOrDefault(parts[0]);
            if (cur == null) throw new ArgumentException($"ref '{r}': khong co model so {parts[0]}.");
            for (int k = 1; k < parts.Length; k++)
            {
                cur = cur.Children.ElementAtOrDefault(parts[k]);
                if (cur == null) throw new ArgumentException($"ref '{r}': khong co phan tu con so {parts[k]} o cap {k} (cay mo hinh da thay doi?).");
            }
            return cur;
        }

        private static int IndexOf(IEnumerable<ModelItem> items, ModelItem target)
        {
            int i = 0;
            foreach (ModelItem x in items)
            {
                if (x.Equals(target)) return i;
                i++;
            }
            // Phong khi ModelItem khong override Equals: so khop theo "chu ky".
            i = 0;
            string name = target.DisplayName;
            string guid = Nw.Str(target, "InstanceGuid");
            foreach (ModelItem x in items)
            {
                if (x.DisplayName == name && Nw.Str(x, "InstanceGuid") == guid && x.HasGeometry == target.HasGeometry) return i;
                i++;
            }
            return -1;
        }
    }

    internal static class NwItems
    {
        public static JObject Summarize(Document doc, ModelItem it, bool withBox, bool withProps)
        {
            var o = new JObject
            {
                ["ref"] = NwRefs.ToRef(doc, it),
                ["name"] = it.DisplayName,
                ["class"] = Nw.Str(it, "ClassDisplayName") ?? Nw.Str(it, "ClassName"),
                ["has_geometry"] = it.HasGeometry,
                ["hidden"] = Nw.Get(it, "IsHidden") as bool?,
                ["children"] = it.Children.Count()
            };
            string guid = Nw.Str(it, "InstanceGuid");
            if (!string.IsNullOrEmpty(guid) && guid != Guid.Empty.ToString()) o["guid"] = guid;

            if (withBox)
            {
                double[] b = Nw.BBox(it);
                if (b != null)
                {
                    double k = Nw.MetersPerUnit(doc);
                    o["bbox_m"] = new JObject
                    {
                        ["min"] = new JArray(Math.Round(b[0] * k, 4), Math.Round(b[1] * k, 4), Math.Round(b[2] * k, 4)),
                        ["max"] = new JArray(Math.Round(b[3] * k, 4), Math.Round(b[4] * k, 4), Math.Round(b[5] * k, 4))
                    };
                }
            }
            if (withProps) o["properties"] = Properties(it);
            return o;
        }

        // { "Item": { "Name": "...", ... }, "Element": { ... } }  (gia tri la chuoi hien thi nhu trong UI)
        public static JObject Properties(ModelItem it)
        {
            var result = new JObject();
            foreach (PropertyCategory cat in it.PropertyCategories)
            {
                string catName = cat.DisplayName ?? cat.Name ?? "?";
                var bag = result[catName] as JObject;
                if (bag == null) { bag = new JObject(); result[catName] = bag; }
                foreach (DataProperty prop in cat.Properties)
                {
                    string key = prop.DisplayName ?? prop.Name ?? "?";
                    if (bag[key] == null) bag[key] = Display(prop.Value);
                }
            }
            return result;
        }

        // Gia tri hien thi cua 1 property; category null = tim o moi category; khong co -> null.
        public static string GetProperty(ModelItem it, string category, string property)
        {
            foreach (PropertyCategory cat in it.PropertyCategories)
            {
                if (category != null
                    && !string.Equals(cat.DisplayName, category, StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(cat.Name, category, StringComparison.OrdinalIgnoreCase)) continue;
                foreach (DataProperty prop in cat.Properties)
                {
                    if (string.Equals(prop.DisplayName, property, StringComparison.OrdinalIgnoreCase)
                        || string.Equals(prop.Name, property, StringComparison.OrdinalIgnoreCase))
                        return Display(prop.Value) ?? "";
                }
            }
            return null;
        }

        private static string Display(VariantData v)
        {
            if (v == null) return null;
            try { return v.ToDisplayString(); }
            catch { return null; }
        }
    }
}
