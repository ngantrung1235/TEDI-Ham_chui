using System;
using Bentley.DgnPlatformNET;
using Bentley.DgnPlatformNET.DgnEC;
using Bentley.DgnPlatformNET.Elements;
using Bentley.ECObjects.Instance;
using Bentley.GeometryNET;
using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;
using BIM = Bentley.Interop.MicroStationDGN;

namespace BentleyMcp.Handlers
{
    internal static class ElementHandlers
    {
        public static void Register(RpcRegistry r)
        {
            r.Add("elements.query", true,
                "Loc element do hoa trong model active (level, element_type, text, limit, offset, include_range, include_properties)",
                Query);

            r.Add("elements.get", true, "Chi tiet 1 element + thuoc tinh EC (id, include_properties)", p =>
            {
                Element el = Mstn.FindById(Mstn.ActiveModel, (long)p["id"]);
                return Summarize(el, Units.Of(Mstn.ActiveModel), true, P.Bool(p, "include_properties", true));
            });

            r.Add("elements.selection", true, "Id cac element dang duoc chon (selection set)", p =>
            {
                var arr = new JArray();
                BIM.ElementEnumerator ee = Mstn.App.ActiveModelReference.GetSelectedElements();
                while (ee.MoveNext()) arr.Add(ee.Current.ID);
                return new JObject { ["count"] = arr.Count, ["ids"] = arr };
            });

            r.Add("elements.select", true, "Chon element theo id (ids, clear_first)", p =>
            {
                if (P.Bool(p, "clear_first", true)) SelectionSetManager.EmptyAll();
                DgnModel model = Mstn.ActiveModel;
                int n = 0;
                foreach (long id in P.LongList(p, "ids"))
                {
                    SelectionSetManager.AddElement(Mstn.FindById(model, id), model);
                    n++;
                }
                return new JObject { ["selected"] = n };
            });

            r.Add("elements.delete", true, "Xoa element theo id (ids)", p =>
            {
                DgnModel model = Mstn.ActiveModel;
                var deleted = new JArray();
                var failed = new JObject();
                foreach (long id in P.LongList(p, "ids"))
                {
                    try
                    {
                        Mstn.FindById(model, id).DeleteFromModel();
                        deleted.Add(id);
                    }
                    catch (Exception ex) { failed[id.ToString()] = ex.Message; }
                }
                return new JObject { ["deleted"] = deleted, ["failed"] = failed };
            });
        }

        private static object Query(JObject p)
        {
            string level = P.Str(p, "level");
            string type = P.Str(p, "element_type");
            string text = P.Str(p, "text");
            int limit = Math.Min(Math.Max(P.Int(p, "limit", 200), 1), 5000);
            int offset = Math.Max(P.Int(p, "offset", 0), 0);
            bool withRange = P.Bool(p, "include_range", false);
            bool withProps = P.Bool(p, "include_properties", false);

            DgnModel model = Mstn.ActiveModel;
            Units units = Units.Of(model);
            var items = new JArray();
            int matched = 0;

            foreach (Element el in model.GetGraphicElements())
            {
                if (level != null && !string.Equals(LevelName(el), level, StringComparison.OrdinalIgnoreCase)) continue;
                if (type != null && !Contains(el.ElementType.ToString(), type) && !Contains(Mstn.Safe(() => el.TypeName), type)) continue;
                if (text != null && !Contains(Mstn.Safe(() => el.Description), text)) continue;

                if (matched >= offset && items.Count < limit)
                    items.Add(Summarize(el, units, withRange, withProps));
                matched++;
            }

            return new JObject
            {
                ["total_matched"] = matched,
                ["offset"] = offset,
                ["returned"] = items.Count,
                ["has_more"] = matched > offset + items.Count,
                ["items"] = items
            };
        }

        public static JObject Summarize(Element el, Units units, bool withRange, bool withProps)
        {
            var o = new JObject
            {
                ["id"] = Mstn.IdOf(el),
                ["element_type"] = el.ElementType.ToString(),
                ["type_name"] = Mstn.Safe(() => el.TypeName),
                ["description"] = Mstn.Safe(() => el.Description),
                ["level"] = LevelName(el)
            };

            if (withRange && el is DisplayableElement de)
            {
                de.CalcElementRange(out DRange3d range);
                if (range.Low.X <= range.High.X && range.Low.Y <= range.High.Y)
                    o["range_m"] = new JObject { ["low"] = units.ToMeters(range.Low), ["high"] = units.ToMeters(range.High) };
            }

            if (withProps) o["ec_instances"] = EcInstances(el);
            return o;
        }

        private static string LevelName(Element el)
        {
            return Mstn.Safe(() =>
            {
                var levelId = new ElementPropertiesGetter(el).Level;
                LevelHandle h = Mstn.ActiveFile.GetLevelCache().GetLevel(levelId);
                return h != null && h.IsValid ? h.Name : null;
            });
        }

        // Thuoc tinh EC = noi OpenTunnel/OpenBridge/OpenRoads luu du lieu nghiep vu (ten
        // tunnel/cau, template, ly trinh, vat lieu, khoi luong...). Doc het moi class gan voi element.
        public static JArray EcInstances(Element el)
        {
            var arr = new JArray();
            DgnECInstanceCollection instances = null;
            try
            {
                instances = DgnECManager.Manager.GetElementProperties(el, ECQueryProcessFlags.SearchAllClasses);
                foreach (IDgnECInstance inst in instances)
                {
                    var props = new JObject();
                    foreach (IECPropertyValue pv in inst) AddValue(props, pv, 0);
                    arr.Add(new JObject
                    {
                        ["schema"] = Mstn.Safe(() => inst.ClassDefinition.Schema.Name),
                        ["class"] = Mstn.Safe(() => inst.ClassDefinition.Name),
                        ["display_label"] = Mstn.Safe(() => inst.ClassDefinition.DisplayLabel),
                        ["properties"] = props
                    });
                }
            }
            catch (Exception ex)
            {
                arr.Add(new JObject { ["error"] = ex.Message });
            }
            finally
            {
                (instances as IDisposable)?.Dispose();
            }
            return arr;
        }

        private static void AddValue(JObject target, IECPropertyValue pv, int depth)
        {
            string name = Mstn.Safe(() => pv.Property.Name, "?");
            try
            {
                if (pv.IsNull) return;
                if (depth < 4 && pv is IECStructValue sv)
                {
                    var sub = new JObject();
                    foreach (IECPropertyValue child in sv) AddValue(sub, child, depth + 1);
                    target[name] = sub;
                }
                else if (depth < 4 && pv is IECArrayValue av)
                {
                    var items = new JArray();
                    for (int i = 0; i < av.Count && i < 500; i++)
                    {
                        var holder = new JObject();
                        AddValue(holder, av[i], depth + 1);
                        foreach (var prop in holder.Properties()) items.Add(prop.Value);
                    }
                    target[name] = items;
                }
                else
                {
                    target[name] = pv.StringValue;
                }
            }
            catch (Exception ex)
            {
                target[name] = "<loi doc: " + ex.Message + ">";
            }
        }

        private static bool Contains(string haystack, string needle) =>
            haystack != null && haystack.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0;
    }
}
