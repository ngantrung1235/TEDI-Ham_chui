using System;
using System.Collections.Generic;
using System.Linq;
using Bentley.DgnPlatformNET;
using Bentley.DgnPlatformNET.DgnEC;
using Bentley.DgnPlatformNET.Elements;
using BentleyMcp.Infrastructure;
using Newtonsoft.Json.Linq;
using McpBridge;
using McpBridge.Infrastructure;

namespace BentleyMcp.Handlers
{
    // Doi tuong "thong minh" cua OpenBridge Modeler (cau, nhip, tru, dam...), OpenTunnel va
    // OpenRoads (corridor, template...) deu duoc nhan dien qua EC class gan voi element.
    // ec.summary cho biet model co nhung class nao (khong can biet truoc ten schema),
    // ec.find lay element theo class de doc thuoc tinh.
    internal static class EcHandlers
    {
        public static void Register(RpcRegistry r)
        {
            r.Add("ec.summary", true, "Thong ke EC class trong model active (max_elements)", Summary);
            r.Add("ec.find", true, "Tim element theo EC class (class_name, schema, exact, limit, include_properties)", Find);
        }

        private static object Summary(JObject p)
        {
            int maxElements = Math.Max(P.Int(p, "max_elements", 20000), 1);
            var counts = new Dictionary<string, (int Count, List<long> Samples)>();
            int scanned = 0, withEc = 0;

            foreach (Element el in Mstn.ActiveModel.GetGraphicElements())
            {
                if (scanned++ >= maxElements) break;
                bool any = false;
                foreach (string key in ClassKeys(el))
                {
                    any = true;
                    if (!counts.TryGetValue(key, out var entry)) entry = (0, new List<long>());
                    if (entry.Samples.Count < 3) entry.Samples.Add(Mstn.IdOf(el));
                    counts[key] = (entry.Count + 1, entry.Samples);
                }
                if (any) withEc++;
            }

            return new JObject
            {
                ["scanned_elements"] = Math.Min(scanned, maxElements),
                ["truncated"] = scanned > maxElements,
                ["elements_with_ec"] = withEc,
                ["classes"] = new JArray(counts
                    .OrderByDescending(kv => kv.Value.Count)
                    .Select(kv => new JObject
                    {
                        ["class"] = kv.Key,
                        ["count"] = kv.Value.Count,
                        ["sample_ids"] = new JArray(kv.Value.Samples)
                    }))
            };
        }

        private static object Find(JObject p)
        {
            string className = P.ReqStr(p, "class_name");
            string schema = P.Str(p, "schema");
            bool exact = P.Bool(p, "exact", false);
            bool withProps = P.Bool(p, "include_properties", true);
            int limit = Math.Min(Math.Max(P.Int(p, "limit", 50), 1), 2000);

            DgnModel model = Mstn.ActiveModel;
            Units units = Units.Of(model);
            var items = new JArray();
            int matched = 0;

            foreach (Element el in model.GetGraphicElements())
            {
                JArray instances = ElementHandlers.EcInstances(el);
                var hits = instances.OfType<JObject>().Where(i => Matches(i, className, schema, exact)).ToList();
                if (hits.Count == 0) continue;
                matched++;
                if (items.Count >= limit) continue;

                JObject summary = ElementHandlers.Summarize(el, units, true, false);
                if (withProps) summary["ec_instances"] = new JArray(hits);
                items.Add(summary);
            }
            return new JObject { ["total_matched"] = matched, ["returned"] = items.Count, ["items"] = items };
        }

        private static bool Matches(JObject inst, string className, string schema, bool exact)
        {
            string cls = (string)inst["class"] ?? "";
            string sch = (string)inst["schema"] ?? "";
            if (schema != null && sch.IndexOf(schema, StringComparison.OrdinalIgnoreCase) < 0) return false;
            return exact
                ? string.Equals(cls, className, StringComparison.OrdinalIgnoreCase)
                : cls.IndexOf(className, StringComparison.OrdinalIgnoreCase) >= 0;
        }

        // "Schema:Class" cua moi EC instance gan voi element (khong doc gia tri -> nhanh hon).
        private static IEnumerable<string> ClassKeys(Element el)
        {
            var keys = new List<string>();
            DgnECInstanceCollection instances = null;
            try
            {
                instances = DgnECManager.Manager.GetElementProperties(el, ECQueryProcessFlags.SearchAllClasses);
                foreach (IDgnECInstance inst in instances)
                    keys.Add(Mstn.Safe(() => inst.ClassDefinition.Schema.Name, "?") + ":" + Mstn.Safe(() => inst.ClassDefinition.Name, "?"));
            }
            catch { /* element khong co EC */ }
            finally
            {
                (instances as IDisposable)?.Dispose();
            }
            return keys.Distinct();
        }
    }
}
