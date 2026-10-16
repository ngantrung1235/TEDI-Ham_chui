using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Autodesk.Navisworks.Api;
using McpBridge;
using McpBridge.Handlers;
using McpBridge.Infrastructure;
using Newtonsoft.Json.Linq;
using NwApp = Autodesk.Navisworks.Api.Application;

namespace NwMcp
{
    // Bien toan cuc ma script C# (nw_run_csharp va cac tool clash/viewpoint... dung snippet) nhin thay truc tiep.
    public sealed class NwScriptGlobals : ScriptGlobalsBase
    {
        public Document Doc { get { return NwApp.ActiveDocument; } }
        public ModelItemCollection Selected { get { return NwApp.ActiveDocument.CurrentSelection.SelectedItems; } }

        // Don vi tai lieu -> met.
        public double MetersPerUnit { get { return Nw.MetersPerUnit(NwApp.ActiveDocument); } }

        // selector JSON (xem NwSearch.cs) -> ModelItemCollection
        public ModelItemCollection Resolve(JToken selector) { return NwSelectors.Resolve(NwApp.ActiveDocument, selector); }

        public string RefOf(ModelItem item) { return NwRefs.ToRef(NwApp.ActiveDocument, item); }

        public ModelItem FromRef(string r) { return NwRefs.Resolve(NwApp.ActiveDocument, r); }

        // Tom tat 1 item thanh JSON (ref, ten, lop, bbox m, thuoc tinh...)
        public JObject Describe(ModelItem item, bool bbox = true, bool props = false)
        {
            return NwItems.Summarize(NwApp.ActiveDocument, item, bbox, props);
        }
    }

    internal static class NwHandlers
    {
        public static void RegisterAll(RpcRegistry r)
        {
            r.Add("nw.doc.info", true, "Tai lieu active: ten file, don vi, danh sach model, so item dang chon", p => DocInfo());
            r.Add("nw.tree", true, "Duyet cay mo hinh (ref, limit, include_properties)", Tree);
            r.Add("nw.search", true,
                "Tim item (where[], class_name, geometry_only, scope_ref, limit, offset, max_scan, include_range, include_properties, select)",
                Search);
            r.Add("nw.item.get", true, "Chi tiet 1 item + thuoc tinh (ref, include_properties)", p =>
            {
                Document doc = Nw.Doc;
                ModelItem it = NwRefs.Resolve(doc, P.ReqStr(p, "ref"));
                return NwItems.Summarize(doc, it, true, P.Bool(p, "include_properties", true));
            });
            r.Add("nw.selection.get", true, "Item dang chon (limit, include_properties)", SelectionGet);
            r.Add("nw.selection.set", true, "Dat vung chon theo selector (selector)", p =>
            {
                Document doc = Nw.Doc;
                ModelItemCollection items = NwSelectors.Resolve(doc, p["selector"]);
                doc.CurrentSelection.Clear();
                doc.CurrentSelection.CopyFrom(items);
                return new JObject { ["selected"] = items.Count };
            });

            ScriptHandlers.Register(r, new ScriptConfig
            {
                GlobalsType = typeof(NwScriptGlobals),
                CreateGlobals = () => new NwScriptGlobals(),
                // Chi namespace CHAC CHAN co: namespace sai se lam hong MOI script. Clash/TimeLiner... tu
                // khai bao `using` trong snippet de loi chi anh huong tool do.
                DefaultImports = new[] { "Autodesk.Navisworks.Api" },
                PreloadAssemblies = new[]
                {
                    "Autodesk.Navisworks.Api", "Autodesk.Navisworks.Clash", "Autodesk.Navisworks.Timeliner",
                    "Autodesk.Navisworks.Takeoff", "Autodesk.Navisworks.ComApi", "Autodesk.Navisworks.Interop.ComApi",
                    "Autodesk.Navisworks.Controls", "navisworks.gui.roamer"
                },
                Description = "Compile & chay C# script trong Navisworks (code, imports, args, timeout_s). " +
                              "Bien: Doc, Selected, MetersPerUnit, Resolve(selector), RefOf(item), FromRef(ref), Describe(item), Arg<T>(name), Print(x)"
            });
        }

        private static object DocInfo()
        {
            Document doc = Nw.Doc;
            var models = new JArray();
            int i = 0;
            foreach (ModelItem root in doc.Models.RootItems)
            {
                models.Add(new JObject { ["index"] = i, ["name"] = root.DisplayName, ["children"] = root.Children.Count() });
                i++;
            }
            // Ten file nguon cua tung model (reflection: ten thanh vien khac giua cac ban)
            int k = 0;
            foreach (object model in (System.Collections.IEnumerable)doc.Models)
            {
                if (k < models.Count)
                {
                    ((JObject)models[k])["file"] = Nw.Str(model, "SourceFileName") ?? Nw.Str(model, "FileName");
                }
                k++;
            }

            Process proc = Process.GetCurrentProcess();
            string exe = null, version = null;
            try { exe = proc.MainModule.FileName; version = proc.MainModule.FileVersionInfo.ProductVersion; } catch { /* khong doc duoc */ }
            return new JObject
            {
                ["application"] = ProductInfo.Name,
                ["version"] = version,
                ["process_path"] = exe,
                ["title"] = Nw.Str(doc, "Title"),
                ["file_name"] = Nw.Str(doc, "FileName"),
                ["units"] = Nw.UnitsName(doc),
                ["units_known"] = Nw.UnitsKnown(doc),
                ["meters_per_unit"] = Nw.MetersPerUnit(doc),
                ["models"] = models,
                ["selected_count"] = doc.CurrentSelection.SelectedItems.Count,
                ["coordinate_convention"] = "Toa do/bbox tra ve bang MET (da nhan he so don vi tai lieu). ref = duong dan chi so trong cay mo hinh.",
                ["bridge"] = BridgeHost.Health()
            };
        }

        private static object Tree(JObject p)
        {
            Document doc = Nw.Doc;
            int limit = Math.Min(Math.Max(P.Int(p, "limit", 200), 1), 5000);
            bool props = P.Bool(p, "include_properties", false);
            string r = P.Str(p, "ref");

            IEnumerable<ModelItem> source = r == null ? doc.Models.RootItems : NwRefs.Resolve(doc, r).Children;
            var items = new JArray();
            int total = 0;
            foreach (ModelItem it in source)
            {
                total++;
                if (items.Count < limit) items.Add(NwItems.Summarize(doc, it, false, props));
            }
            return new JObject { ["parent_ref"] = r, ["total_children"] = total, ["returned"] = items.Count, ["items"] = items };
        }

        private static object Search(JObject p)
        {
            Document doc = Nw.Doc;
            int limit = Math.Min(Math.Max(P.Int(p, "limit", 100), 1), 2000);
            int offset = Math.Max(P.Int(p, "offset", 0), 0);
            int maxScan = Math.Max(P.Int(p, "max_scan", 500000), 1);
            bool box = P.Bool(p, "include_range", false);
            bool props = P.Bool(p, "include_properties", false);
            bool select = P.Bool(p, "select", false);

            var items = new JArray();
            var selection = select ? new ModelItemCollection() : null;
            int matched = 0, scanned = 0;
            bool truncated = false;
            foreach (ModelItem it in NwSearch.Matches(doc, p))
            {
                if (++scanned > maxScan) { truncated = true; break; }
                if (matched >= offset && items.Count < limit) items.Add(NwItems.Summarize(doc, it, box, props));
                if (selection != null) selection.Add(it);
                matched++;
            }
            if (selection != null)
            {
                doc.CurrentSelection.Clear();
                doc.CurrentSelection.CopyFrom(selection);
            }
            return new JObject
            {
                ["total_matched"] = matched,
                ["truncated"] = truncated,
                ["offset"] = offset,
                ["returned"] = items.Count,
                ["has_more"] = matched > offset + items.Count,
                ["selected"] = selection != null ? (int?)selection.Count : null,
                ["items"] = items
            };
        }

        private static object SelectionGet(JObject p)
        {
            Document doc = Nw.Doc;
            int limit = Math.Min(Math.Max(P.Int(p, "limit", 200), 1), 5000);
            bool props = P.Bool(p, "include_properties", false);
            ModelItemCollection sel = doc.CurrentSelection.SelectedItems;
            var items = new JArray();
            foreach (ModelItem it in sel)
            {
                if (items.Count >= limit) break;
                items.Add(NwItems.Summarize(doc, it, true, props));
            }
            return new JObject { ["count"] = sel.Count, ["returned"] = items.Count, ["items"] = items };
        }
    }
}
