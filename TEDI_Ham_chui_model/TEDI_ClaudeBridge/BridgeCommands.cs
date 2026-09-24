using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.UI;
using Newtonsoft.Json.Linq;
using TEDI_Ham_chui_model.Models;

namespace TEDI_ClaudeBridge
{
    // Cac lenh ma Claude duoc phep goi vao Revit. Tat ca chay tren thread chinh cua
    // Revit (goi tu BridgeEventHandler.Execute). Don vi tra ve:
    //  - toa do / chieu dai hinh hoc: mm (doi tu don vi noi bo feet cua Revit);
    //  - gia tri parameter: "value" = chuoi hien thi theo don vi du an (AsValueString),
    //    "raw" = gia tri noi bo (feet, rad...) de tinh toan neu can.
    // set_parameters (1 Transaction, loi 1 param la rollback ca lo) va draw_all_rebar
    // (logic nut "Ve tat ca thep" cua add-in ham chui) la 2 lenh thay doi model.
    internal static class BridgeCommands
    {
        private const int DefaultListLimit = 200;
        private const int MaxListLimit = 5000;
        private const double SteelDensityKgPerM3 = 7850.0;

        public static JToken? Dispatch(UIApplication app, string method, JObject p)
        {
            switch (method)
            {
                case "ping":
                    return Ping(app);
                case "get_document_info":
                    return GetDocumentInfo(RequireUiDoc(app));
                case "get_selection":
                    return GetSelection(RequireUiDoc(app));
                case "list_categories":
                    return ListCategories(RequireUiDoc(app).Document);
                case "list_elements":
                    return ListElements(RequireUiDoc(app), p);
                case "get_element":
                    return GetElement(RequireUiDoc(app).Document, p);
                case "set_parameters":
                    return SetParameters(RequireUiDoc(app).Document, p);
                case "select_elements":
                    return SelectElements(RequireUiDoc(app), p);
                case "get_rebar_summary":
                    return GetRebarSummary(RequireUiDoc(app), p);
                case "get_draw_all_rebar_settings":
                    return GetDrawAllRebarSettings(RequireUiDoc(app).Document);
                case "draw_all_rebar":
                    return DrawAllRebar(RequireUiDoc(app), p);
                default:
                    throw new InvalidOperationException($"Lenh khong ho tro: '{method}'.");
            }
        }

        private static UIDocument RequireUiDoc(UIApplication app) =>
            app.ActiveUIDocument ?? throw new InvalidOperationException("Revit chua mo model nao.");

        // ------------------------------------------------------------------ read

        private static JToken Ping(UIApplication app) => new JObject
        {
            ["revit_version"] = app.Application.VersionNumber,
            ["revit_build"] = app.Application.VersionBuild,
            ["active_document"] = app.ActiveUIDocument?.Document.Title,
        };

        private static JToken GetDocumentInfo(UIDocument uidoc)
        {
            Document doc = uidoc.Document;
            View view = doc.ActiveView;
            ForgeTypeId lengthUnit = doc.GetUnits().GetFormatOptions(SpecTypeId.Length).GetUnitTypeId();

            return new JObject
            {
                ["title"] = doc.Title,
                ["path"] = doc.PathName,
                ["is_family_document"] = doc.IsFamilyDocument,
                ["is_workshared"] = doc.IsWorkshared,
                ["length_display_unit"] = LabelUtils.GetLabelForUnit(lengthUnit),
                ["active_view"] = new JObject
                {
                    ["id"] = view.Id.Value,
                    ["name"] = view.Name,
                    ["type"] = view.ViewType.ToString(),
                },
                ["element_count"] = new FilteredElementCollector(doc).WhereElementIsNotElementType().GetElementCount(),
                ["levels"] = new JArray(new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                    .OrderBy(l => l.Elevation)
                    .Select(l => new JObject
                    {
                        ["id"] = l.Id.Value,
                        ["name"] = l.Name,
                        ["elevation_mm"] = Math.Round(ToMm(l.Elevation), 1),
                    })),
            };
        }

        private static JToken GetSelection(UIDocument uidoc)
        {
            Document doc = uidoc.Document;
            List<JObject> items = uidoc.Selection.GetElementIds()
                .Select(doc.GetElement)
                .Where(e => e != null)
                .Select(e => Summarize(doc, e))
                .ToList();
            return new JObject { ["count"] = items.Count, ["elements"] = new JArray(items) };
        }

        private static JToken ListCategories(Document doc)
        {
            // Chi liet ke category thuc su co phan tu trong model, kem so luong.
            var counts = new FilteredElementCollector(doc).WhereElementIsNotElementType()
                .Where(e => e.Category != null)
                .GroupBy(e => e.Category.Id.Value)
                .Select(g => new { Category = g.First().Category, Count = g.Count() })
                .OrderByDescending(x => x.Count);

            return new JArray(counts.Select(x => new JObject
            {
                ["name"] = x.Category.Name,
                ["built_in"] = x.Category.BuiltInCategory != BuiltInCategory.INVALID
                    ? x.Category.BuiltInCategory.ToString() : null,
                ["count"] = x.Count,
            }));
        }

        private static JToken ListElements(UIDocument uidoc, JObject p)
        {
            Document doc = uidoc.Document;
            FilteredElementCollector collector = GetBool(p, "active_view_only", false)
                ? new FilteredElementCollector(doc, doc.ActiveView.Id)
                : new FilteredElementCollector(doc);
            collector.WhereElementIsNotElementType();

            string? category = GetString(p, "category");
            if (!string.IsNullOrWhiteSpace(category))
                collector.OfCategoryId(ResolveCategory(doc, category!).Id);

            IEnumerable<Element> elements = collector;
            string? nameContains = GetString(p, "name_contains");
            if (!string.IsNullOrWhiteSpace(nameContains))
            {
                elements = elements.Where(e =>
                    ContainsIgnoreCase(e.Name, nameContains!) ||
                    ContainsIgnoreCase(doc.GetElement(e.GetTypeId())?.Name, nameContains!));
            }

            int limit = Math.Max(1, Math.Min(MaxListLimit, GetInt(p, "limit", DefaultListLimit)));
            List<Element> all = elements.ToList();
            return new JObject
            {
                ["total"] = all.Count,
                ["returned"] = Math.Min(limit, all.Count),
                ["elements"] = new JArray(all.Take(limit).Select(e => Summarize(doc, e))),
            };
        }

        private static JToken GetElement(Document doc, JObject p)
        {
            Element e = RequireElement(doc, GetLong(p, "id"));
            JObject result = Summarize(doc, e);
            result["parameters"] = DumpParameters(e);

            if (GetBool(p, "include_type_parameters", false) && doc.GetElement(e.GetTypeId()) is Element type)
                result["type_parameters"] = DumpParameters(type);

            switch (e.Location)
            {
                case LocationPoint lp:
                    result["location"] = new JObject { ["point_mm"] = PointMm(lp.Point) };
                    break;
                case LocationCurve lc:
                    result["location"] = new JObject
                    {
                        ["start_mm"] = PointMm(lc.Curve.GetEndPoint(0)),
                        ["end_mm"] = PointMm(lc.Curve.GetEndPoint(1)),
                        ["length_mm"] = Math.Round(ToMm(lc.Curve.Length), 1),
                    };
                    break;
            }

            BoundingBoxXYZ? bb = e.get_BoundingBox(null);
            if (bb != null)
                result["bounding_box_mm"] = new JObject { ["min"] = PointMm(bb.Min), ["max"] = PointMm(bb.Max) };

            return result;
        }

        // Thong ke thep: nhom theo loai thanh (RebarBarType), tong so thanh, tong chieu
        // dai va khoi luong danh nghia = A_danh_nghia x L x 7850 kg/m3. Chi tinh doi
        // tuong Rebar (khong gom Area/Path Reinforcement va RebarInSystem).
        private static JToken GetRebarSummary(UIDocument uidoc, JObject p)
        {
            Document doc = uidoc.Document;
            IEnumerable<Rebar> rebars = new FilteredElementCollector(doc).OfClass(typeof(Rebar)).Cast<Rebar>();

            long? hostId = GetOptionalLong(p, "host_id");
            if (hostId.HasValue)
                rebars = rebars.Where(r => r.GetHostId().Value == hostId.Value);
            if (GetBool(p, "selection_only", false))
            {
                var selected = new HashSet<long>(uidoc.Selection.GetElementIds().Select(id => id.Value));
                rebars = rebars.Where(r => selected.Contains(r.Id.Value) || selected.Contains(r.GetHostId().Value));
            }
            return SummarizeRebars(doc, rebars);
        }

        private static JObject SummarizeRebars(Document doc, IEnumerable<Rebar> rebars)
        {
            var groups = rebars
                .GroupBy(r => r.GetTypeId().Value)
                .Select(g =>
                {
                    var barType = doc.GetElement(new ElementId(g.Key)) as RebarBarType;
                    double diameterFt = barType?.BarNominalDiameter ?? 0;
                    double lengthM = g.Sum(r => r.TotalLength) * 0.3048;
                    double areaM2 = Math.PI * Math.Pow(diameterFt * 0.3048, 2) / 4.0;
                    return new
                    {
                        Name = barType?.Name ?? "(khong ro)",
                        DiameterMm = ToMm(diameterFt),
                        Elements = g.Count(),
                        Bars = g.Sum(r => r.Quantity),
                        LengthM = lengthM,
                        WeightKg = areaM2 * lengthM * SteelDensityKgPerM3,
                    };
                })
                .OrderBy(x => x.DiameterMm)
                .ToList();

            return new JObject
            {
                ["bar_types"] = new JArray(groups.Select(x => new JObject
                {
                    ["bar_type"] = x.Name,
                    ["diameter_mm"] = Math.Round(x.DiameterMm, 1),
                    ["rebar_elements"] = x.Elements,
                    ["bar_count"] = x.Bars,
                    ["total_length_m"] = Math.Round(x.LengthM, 2),
                    ["nominal_weight_kg"] = Math.Round(x.WeightKg, 1),
                })),
                ["total_rebar_elements"] = groups.Sum(x => x.Elements),
                ["total_length_m"] = Math.Round(groups.Sum(x => x.LengthM), 2),
                ["total_nominal_weight_kg"] = Math.Round(groups.Sum(x => x.WeightKg), 1),
                ["note"] = "Khoi luong danh nghia = pi*d^2/4 x L x 7850 kg/m3 (d = BarNominalDiameter).",
            };
        }

        // ------------------------------------------------------------------ ve thep ham chui

        private const string OuterShapeName = "Rebar_21";

        // Cac thong so double co the ghi de cua RebarAllInOneSettings (CoverMm, DiamS1Mm,
        // SpaceS1Mm, ..., VuonMm) - lay bang reflection de tu khop khi add-in them thong so.
        private static IEnumerable<PropertyInfo> DrawSettingProperties() =>
            typeof(RebarAllInOneSettings).GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(pi => pi.PropertyType == typeof(double) && pi.CanRead && pi.CanWrite);

        private static JToken GetDrawAllRebarSettings(Document doc)
        {
            var defaults = new RebarAllInOneSettings();
            var values = new JObject();
            foreach (PropertyInfo pi in DrawSettingProperties())
                values[pi.Name] = (double)pi.GetValue(defaults)!;

            return new JObject
            {
                ["defaults_mm"] = values,
                ["outer_shape_available"] = OuterShapeAvailable(doc),
                ["legend"] = "S=Nap, F=Day, H=Tuong trai+phai. S1/F1/H1 thep ngang lop trong; S2/F2 thep " +
                             "hinh Z (RebarShape Rebar_21); S4/F4/H2 thep doc; S6/F6/H3 dai C; S5 thep cheo " +
                             "goc vat (VuonMm = doan vuon 2 dau). Diam* = duong kinh, Space* = khoang cach (mm). " +
                             "ShapeUTipMm/ShapeCEndCompensationMm: hieu chinh hinh hoc Rebar_21, do cho B=3500mm + D20.",
            };
        }

        // Chay logic nut "Ve tat ca thep": dung cau kien dang chon (hoac host_ids), NGUOI
        // DUNG phai pick 3 mat (mat bang / mat dung / mat canh) cho TUNG cau kien trong
        // Revit, roi ve S4/F4/H2 + dai C, Rebar_21 (S2/F2), S1/F1/H1, S5 - moi nhom 1
        // Transaction rieng.
        private static JToken DrawAllRebar(UIDocument uidoc, JObject p)
        {
            Document doc = uidoc.Document;
            var settings = new RebarAllInOneSettings();
            if (p["settings"] is JObject overrides)
                ApplyDrawSettings(settings, overrides);

            if (p["host_ids"] is JArray)
                uidoc.Selection.SetElementIds(GetIdList(p, "host_ids").Where(id => doc.GetElement(id) != null).ToList());
            if (uidoc.Selection.GetElementIds().Count == 0)
                throw new InvalidOperationException(
                    "Chua chon cau kien ham nao. Chon cau kien trong Revit (hoac truyen host_ids) roi chay lai.");

            // Kiem tra truoc khi bat nguoi dung pick: thieu Rebar_21 thi buoc S2/F2 se loi
            // SAU KHI cac buoc truoc da commit thep -> bao som thay vi ve do dang.
            if (!OuterShapeAvailable(doc))
                throw new InvalidOperationException(
                    $"Model chua co RebarShape '{OuterShapeName}' va khong co file {OuterShapeName}.rfa dung phien ban " +
                    "canh add-in. File Rebar_21.rfa trong repo luu bang Revit 2027 nen Revit 2024 KHONG load duoc: " +
                    "hay tao lai RebarShape 'Rebar_21' bang Revit 2024 (hoac load vao model thu cong) roi chay lai.");

            var before = new HashSet<long>(new FilteredElementCollector(doc).OfClass(typeof(Rebar)).ToElementIds().Select(id => id.Value));
            List<Rebar> Created() => new FilteredElementCollector(doc).OfClass(typeof(Rebar)).Cast<Rebar>()
                .Where(r => !before.Contains(r.Id.Value)).ToList();

            string report;
            try
            {
                report = settings.Run(uidoc);
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                throw new InvalidOperationException(
                    "Nguoi dung da huy (Esc) khi pick mat - chua ve thanh thep nao.");
            }
            catch (Exception ex)
            {
                int made = Created().Count;
                throw new InvalidOperationException(made == 0
                    ? ex.Message
                    : $"{ex.Message}\nDa tao {made} doi tuong Rebar o cac buoc truoc khi loi (moi buoc 1 " +
                      "Transaction rieng - Ctrl+Z tung buoc de hoan tac).");
            }

            List<Rebar> created = Created();
            JObject result = SummarizeRebars(doc, created);
            result["report"] = report;
            result["settings_used_mm"] = new JObject(DrawSettingProperties()
                .Select(pi => new JProperty(pi.Name, (double)pi.GetValue(settings)!)));
            result["created_ids_sample"] = new JArray(created.Take(50).Select(r => r.Id.Value));
            return result;
        }

        private static void ApplyDrawSettings(RebarAllInOneSettings settings, JObject overrides)
        {
            var props = DrawSettingProperties().ToDictionary(pi => pi.Name, StringComparer.OrdinalIgnoreCase);
            foreach (JProperty prop in overrides.Properties())
            {
                if (!props.TryGetValue(prop.Name, out PropertyInfo? pi))
                    throw new InvalidOperationException(
                        $"Thong so khong ton tai: '{prop.Name}'. Hop le: {string.Join(", ", props.Keys)}.");
                if (prop.Value.Type != JTokenType.Integer && prop.Value.Type != JTokenType.Float)
                    throw new InvalidOperationException($"'{prop.Name}' phai la so (mm).");

                double value = prop.Value.Value<double>();
                bool mustBePositive = pi.Name.StartsWith("Diam") || pi.Name.StartsWith("Space") || pi.Name == "CoverMm";
                if (double.IsNaN(value) || double.IsInfinity(value) || value < 0 || (mustBePositive && value == 0))
                    throw new InvalidOperationException($"Gia tri '{prop.Name}' = {value} khong hop le.");
                pi.SetValue(settings, value);
            }
        }

        // Giong thu tu tim cua ShapeDrivenOuterRebar.FindOrLoadRebarShape: co san trong
        // model, hoac file .rfa canh DLL (chi kem theo ban build Revit 2027).
        private static bool OuterShapeAvailable(Document doc)
        {
            bool inModel = new FilteredElementCollector(doc).OfClass(typeof(RebarShape)).Cast<RebarShape>()
                .Any(rs => rs.Name.Trim().Equals(OuterShapeName, StringComparison.OrdinalIgnoreCase));
            if (inModel)
                return true;
            string dllFolder = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location) ?? "";
            return File.Exists(Path.Combine(dllFolder, OuterShapeName + ".rfa"));
        }

        // ------------------------------------------------------------------ write

        private static JToken SelectElements(UIDocument uidoc, JObject p)
        {
            Document doc = uidoc.Document;
            List<ElementId> ids = GetIdList(p, "ids").Where(id => doc.GetElement(id) != null).ToList();
            uidoc.Selection.SetElementIds(ids);
            if (ids.Count > 0 && GetBool(p, "zoom", true))
                uidoc.ShowElements(ids);
            return new JObject { ["selected"] = ids.Count };
        }

        // params: { "id": 123, "values": { "Comments": "abc", "Length": 2500 } }
        // So (number) duoc hieu theo DON VI HIEN THI cua du an (vd. mm) roi doi sang don
        // vi noi bo; chuoi (string) voi tham so so thi dung SetValueString (vd. "2500 mm").
        private static JToken SetParameters(Document doc, JObject p)
        {
            Element e = RequireElement(doc, GetLong(p, "id"));
            if (!(p["values"] is JObject values) || !values.HasValues)
                throw new InvalidOperationException("Thieu 'values' (object ten_parameter -> gia tri).");

            var changed = new JArray();
            using (var t = new Transaction(doc, "Claude: Set parameters"))
            {
                t.Start();
                foreach (JProperty prop in values.Properties())
                {
                    Parameter? param = e.LookupParameter(prop.Name);
                    if (param == null)
                        throw new InvalidOperationException($"Phan tu {e.Id.Value} khong co parameter '{prop.Name}'.");
                    if (param.IsReadOnly)
                        throw new InvalidOperationException($"Parameter '{prop.Name}' chi doc (read-only).");

                    string? before = ParamDisplay(param);
                    if (!SetParameterValue(doc, param, prop.Value))
                        throw new InvalidOperationException($"Revit khong nhan gia tri '{prop.Value}' cho '{prop.Name}'.");

                    changed.Add(new JObject { ["name"] = prop.Name, ["before"] = before, ["after"] = ParamDisplay(param) });
                }

                if (t.Commit() != TransactionStatus.Committed)
                    throw new InvalidOperationException("Transaction khong commit duoc (xem canh bao trong Revit).");
            }
            return new JObject { ["id"] = e.Id.Value, ["changed"] = changed };
        }

        private static bool SetParameterValue(Document doc, Parameter param, JToken value)
        {
            JTokenType kind = value.Type;
            if (kind != JTokenType.String && kind != JTokenType.Integer && kind != JTokenType.Float && kind != JTokenType.Boolean)
                throw new InvalidOperationException($"Gia tri cho '{param.Definition.Name}' phai la so, chuoi hoac bool.");

            switch (param.StorageType)
            {
                case StorageType.String:
                    return param.Set(value.Type == JTokenType.String ? value.Value<string>() : value.ToString());

                case StorageType.Integer:
                    if (kind == JTokenType.Boolean)
                        return param.Set(value.Value<bool>() ? 1 : 0);
                    if (kind == JTokenType.Integer)
                        return param.Set(value.Value<int>());
                    return param.SetValueString(value.ToString());

                case StorageType.Double:
                    if (kind == JTokenType.String)
                        return param.SetValueString(value.Value<string>());
                    double number = value.Value<double>();
                    ForgeTypeId spec = param.Definition.GetDataType();
                    if (UnitUtils.IsMeasurableSpec(spec))
                    {
                        ForgeTypeId displayUnit = doc.GetUnits().GetFormatOptions(spec).GetUnitTypeId();
                        number = UnitUtils.ConvertToInternalUnits(number, displayUnit);
                    }
                    return param.Set(number);

                case StorageType.ElementId:
                    return param.Set(new ElementId(value.Value<long>()));

                default:
                    return false;
            }
        }

        // ------------------------------------------------------------------ helpers

        private static JObject Summarize(Document doc, Element e)
        {
            var o = new JObject
            {
                ["id"] = e.Id.Value,
                ["name"] = e.Name,
                ["category"] = e.Category?.Name,
                ["type"] = doc.GetElement(e.GetTypeId())?.Name,
            };
            if (e.LevelId != ElementId.InvalidElementId && doc.GetElement(e.LevelId) is Level level)
                o["level"] = level.Name;
            return o;
        }

        private static JArray DumpParameters(Element e)
        {
            return new JArray(e.Parameters.Cast<Parameter>()
                .Where(prm => prm.Definition != null)
                .OrderBy(prm => prm.Definition.Name)
                .Select(prm => new JObject
                {
                    ["name"] = prm.Definition.Name,
                    ["value"] = ParamDisplay(prm),
                    ["raw"] = ParamRaw(prm),
                    ["storage"] = prm.StorageType.ToString(),
                    ["read_only"] = prm.IsReadOnly,
                    ["shared"] = prm.IsShared,
                }));
        }

        private static string? ParamDisplay(Parameter prm) =>
            prm.StorageType == StorageType.String ? prm.AsString() : prm.AsValueString();

        private static JToken? ParamRaw(Parameter prm)
        {
            if (!prm.HasValue)
                return null;
            switch (prm.StorageType)
            {
                case StorageType.Double: return prm.AsDouble();
                case StorageType.Integer: return prm.AsInteger();
                case StorageType.String: return prm.AsString();
                case StorageType.ElementId: return prm.AsElementId().Value;
                default: return null;
            }
        }

        // Nhan ten BuiltInCategory ("OST_Rebar") hoac ten hien thi ("Structural Rebar",
        // khong phan biet hoa thuong).
        private static Category ResolveCategory(Document doc, string name)
        {
            if (Enum.TryParse(name, true, out BuiltInCategory bic) && bic != BuiltInCategory.INVALID)
            {
                Category? byEnum = Category.GetCategory(doc, bic);
                if (byEnum != null)
                    return byEnum;
            }
            foreach (Category c in doc.Settings.Categories)
            {
                if (string.Equals(c.Name, name, StringComparison.OrdinalIgnoreCase))
                    return c;
            }
            throw new InvalidOperationException(
                $"Khong tim thay category '{name}'. Dung lenh list_categories de xem ten hop le.");
        }

        private static Element RequireElement(Document doc, long id) =>
            doc.GetElement(new ElementId(id)) ?? throw new InvalidOperationException($"Khong co phan tu id {id}.");

        private static double ToMm(double feet) => UnitUtils.ConvertFromInternalUnits(feet, UnitTypeId.Millimeters);

        private static JArray PointMm(XYZ pt) =>
            new JArray(Math.Round(ToMm(pt.X), 1), Math.Round(ToMm(pt.Y), 1), Math.Round(ToMm(pt.Z), 1));

        private static bool ContainsIgnoreCase(string? text, string part) =>
            text != null && text.IndexOf(part, StringComparison.OrdinalIgnoreCase) >= 0;

        private static string? GetString(JObject p, string key) =>
            p[key]?.Type == JTokenType.String ? p.Value<string>(key) : null;

        private static bool GetBool(JObject p, string key, bool fallback) =>
            p[key]?.Type == JTokenType.Boolean ? p.Value<bool>(key) : fallback;

        private static int GetInt(JObject p, string key, int fallback) =>
            p[key]?.Type == JTokenType.Integer ? p.Value<int>(key) : fallback;

        private static long? GetOptionalLong(JObject p, string key)
        {
            JToken? v = p[key];
            if (v == null)
                return null;
            if (v.Type == JTokenType.Integer)
                return v.Value<long>();
            if (v.Type == JTokenType.String &&
                long.TryParse(v.Value<string>(), NumberStyles.Integer, CultureInfo.InvariantCulture, out long parsed))
                return parsed;
            return null;
        }

        private static long GetLong(JObject p, string key) =>
            GetOptionalLong(p, key) ?? throw new InvalidOperationException($"Thieu tham so '{key}' (element id).");

        private static IEnumerable<ElementId> GetIdList(JObject p, string key)
        {
            if (!(p[key] is JArray arr))
                throw new InvalidOperationException($"Thieu tham so '{key}' (mang element id).");
            return arr.Where(t => t.Type == JTokenType.Integer)
                .Select(t => new ElementId(t.Value<long>()))
                .ToList();
        }
    }
}
