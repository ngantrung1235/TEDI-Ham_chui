using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Autodesk.Navisworks.Api;
using McpBridge.Infrastructure;
using Newtonsoft.Json.Linq;

namespace NwMcp
{
    internal sealed class Condition
    {
        public string Category;   // null = bat ky category
        public string Property;
        public string Op;         // equals | not_equals | contains | starts_with | ends_with | regex | exists | not_exists | gt | gte | lt | lte
        public string Value;
    }

    // Bo loc element dung chung cho nw.search, nw.selection.set, nw.visibility, clash...
    //
    // Selector (JSON) co 1 trong cac dang:
    //   {"refs": ["0/3/12", ...]}                         cac item theo ref
    //   {"selection": true}                               vung chon hien tai trong Navisworks
    //   {"where": [{"category","property","op","value"}], "class_name": "...", "geometry_only": true,
    //    "scope_ref": "0/3", "max_items": 5000}           tim kiem
    // Dieu kien dau tien op=equals (co category) chay bang Search native cua Navisworks (nhanh, co
    // index); cac dieu kien con lai loc them trong C#. Khong co dieu kien native -> duyet cay.
    internal static class NwSearch
    {
        private static readonly Regex Number = new Regex(@"-?\d+(?:[.,]\d+)?", RegexOptions.Compiled);

        public static List<Condition> ParseWhere(JToken where)
        {
            var list = new List<Condition>();
            if (where == null || where.Type == JTokenType.Null) return list;
            var arr = where as JArray ?? new JArray(where);
            foreach (JToken t in arr)
            {
                var o = t as JObject;
                if (o == null) throw new ArgumentException("Moi dieu kien trong 'where' phai la doi tuong {category, property, op, value}.");
                var c = new Condition
                {
                    Category = P.Str(o, "category"),
                    Property = P.Str(o, "property"),
                    Op = (P.Str(o, "op", "equals") ?? "equals").ToLowerInvariant(),
                    Value = P.Str(o, "value")
                };
                if (string.IsNullOrWhiteSpace(c.Property)) throw new ArgumentException("Dieu kien thieu 'property'.");
                bool needsValue = c.Op != "exists" && c.Op != "not_exists";
                if (needsValue && c.Value == null) throw new ArgumentException($"Dieu kien op='{c.Op}' can 'value'.");
                list.Add(c);
            }
            return list;
        }

        // Tat ca item (moi model, ke ca root).
        public static IEnumerable<ModelItem> AllItems(Document doc)
        {
            foreach (ModelItem root in doc.Models.RootItems)
                foreach (ModelItem d in root.DescendantsAndSelf)
                    yield return d;
        }

        public static IEnumerable<ModelItem> Matches(Document doc, JObject spec)
        {
            List<Condition> conds = ParseWhere(spec["where"]);
            string cls = P.Str(spec, "class_name");
            bool geometryOnly = P.Bool(spec, "geometry_only", false);
            string scopeRef = P.Str(spec, "scope_ref");
            ModelItem scope = scopeRef == null ? null : NwRefs.Resolve(doc, scopeRef);

            Condition nativeCond = null;
            IEnumerable<ModelItem> source = null;
            if (scope == null)
            {
                Condition first = conds.FirstOrDefault(c => c.Op == "equals" && !string.IsNullOrEmpty(c.Category));
                if (first != null)
                {
                    source = TryNative(doc, first);
                    if (source != null) nativeCond = first;
                }
            }
            if (source == null) source = scope != null ? scope.DescendantsAndSelf : AllItems(doc);

            foreach (ModelItem it in source)
            {
                if (geometryOnly && !it.HasGeometry) continue;
                if (cls != null && !ClassMatches(it, cls)) continue;
                bool ok = true;
                foreach (Condition c in conds)
                {
                    if (ReferenceEquals(c, nativeCond)) continue;
                    if (!Eval(it, c)) { ok = false; break; }
                }
                if (ok) yield return it;
            }
        }

        // Search native; loi (vd API doi khac) -> null de roi ve duyet cay.
        private static IEnumerable<ModelItem> TryNative(Document doc, Condition c)
        {
            try
            {
                var s = new Search();
                s.Selection.SelectAll();
                s.SearchConditions.Add(SearchCondition.HasPropertyByDisplayName(c.Category, c.Property)
                    .EqualValue(VariantData.FromDisplayString(c.Value)));
                return s.FindAll(doc, false);
            }
            catch (Exception ex)
            {
                BridgeHost.Log("Search native loi, chuyen sang duyet cay: " + ex.Message);
                return null;
            }
        }

        private static bool ClassMatches(ModelItem it, string cls)
        {
            string a = Nw.Str(it, "ClassDisplayName") ?? "";
            string b = Nw.Str(it, "ClassName") ?? "";
            return a.IndexOf(cls, StringComparison.OrdinalIgnoreCase) >= 0 || b.IndexOf(cls, StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static bool Eval(ModelItem it, Condition c)
        {
            string v = NwItems.GetProperty(it, c.Category, c.Property);
            if (c.Op == "exists") return v != null;
            if (c.Op == "not_exists") return v == null;
            if (v == null) return c.Op == "not_equals";

            switch (c.Op)
            {
                case "equals": return string.Equals(v, c.Value, StringComparison.OrdinalIgnoreCase);
                case "not_equals": return !string.Equals(v, c.Value, StringComparison.OrdinalIgnoreCase);
                case "contains": return v.IndexOf(c.Value, StringComparison.OrdinalIgnoreCase) >= 0;
                case "starts_with": return v.StartsWith(c.Value, StringComparison.OrdinalIgnoreCase);
                case "ends_with": return v.EndsWith(c.Value, StringComparison.OrdinalIgnoreCase);
                case "regex": return Regex.IsMatch(v, c.Value, RegexOptions.IgnoreCase);
                case "gt":
                case "gte":
                case "lt":
                case "lte":
                    double a, b;
                    if (!TryNumber(v, out a) || !TryNumber(c.Value, out b)) return false;
                    return c.Op == "gt" ? a > b : c.Op == "gte" ? a >= b : c.Op == "lt" ? a < b : a <= b;
                default:
                    throw new ArgumentException($"op '{c.Op}' khong ho tro. Dung: equals, not_equals, contains, starts_with, ends_with, regex, exists, not_exists, gt, gte, lt, lte.");
            }
        }

        // Lay so dau tien trong chuoi hien thi (vd "3.50 m" -> 3.5).
        private static bool TryNumber(string s, out double value)
        {
            value = 0;
            Match m = Number.Match(s ?? "");
            return m.Success && double.TryParse(m.Value.Replace(',', '.'), System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out value);
        }
    }

    internal static class NwSelectors
    {
        // selector -> ModelItemCollection (toi da max_items phan tu, mac dinh 100000).
        public static ModelItemCollection Resolve(Document doc, JToken selector)
        {
            var spec = selector as JObject;
            if (spec == null) throw new ArgumentException("selector phai la doi tuong: {\"refs\":[..]} | {\"selection\":true} | {\"where\":[..],...}.");
            var result = new ModelItemCollection();

            if (spec["refs"] != null)
            {
                foreach (string r in P.StrList(spec, "refs")) result.Add(NwRefs.Resolve(doc, r));
                return result;
            }
            if (P.Bool(spec, "selection", false))
            {
                foreach (ModelItem it in doc.CurrentSelection.SelectedItems) result.Add(it);
                return result;
            }
            if (spec["where"] == null && spec["class_name"] == null && !P.Bool(spec, "geometry_only", false) && spec["scope_ref"] == null)
                throw new ArgumentException("selector khong co tieu chi nao (refs | selection | where | class_name | geometry_only | scope_ref).");

            int max = Math.Max(P.Int(spec, "max_items", 100000), 1);
            foreach (ModelItem it in NwSearch.Matches(doc, spec))
            {
                result.Add(it);
                if (result.Count >= max) break;
            }
            return result;
        }
    }
}
