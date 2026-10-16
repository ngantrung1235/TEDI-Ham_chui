"""Snippet C# chay trong Navisworks qua nw_run_csharp (Roslyn) cho cac tinh nang "kho kiem chung".

Ly do dung snippet thay vi C# bien dich san: ten lop/ham trong Navisworks API (Clash, TimeLiner,
SavedViewpoint, ham doi mau...) khac nhau giua cac ban va nhom nay khong the doi chieu voi SDK that khi
viet. O day loi API chi hien thanh `errors[]` LUC CHAY cua dung tool do (khong lam hong ca add-in) va co the
sua ngay trong file Python nay ma khong phai build lai plugin. Hang `*_HEADERS` liet ke cac bien the dong
`using` se duoc thu lan luot.

Bien co san trong snippet: Doc, Selected, MetersPerUnit, Resolve(selector), RefOf(item), FromRef(ref),
Describe(item), Arg<T>(name), Args["name"], Print(x). Gia tri `return` la ket qua tra ve (JObject/JArray).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- tep
FILE_OPEN = r"""
string path = Arg<string>("path");
bool append = Arg<bool>("append", false);
if (!File.Exists(path)) throw new FileNotFoundException("Khong tim thay file: " + path);
if (append) Doc.AppendFile(path); else Doc.OpenFile(path);
return new JObject { ["opened"] = path, ["append"] = append, ["models"] = Doc.Models.RootItems.Count() };
"""

FILE_SAVE = r"""
string path = Arg<string>("path");
if (string.IsNullOrEmpty(path)) path = Doc.FileName;
if (string.IsNullOrEmpty(path)) throw new InvalidOperationException("Tai lieu chua co ten file: truyen path (.nwd / .nwf).");
Doc.SaveFile(path);
return new JObject { ["saved"] = path };
"""

# --------------------------------------------------------------------------- hien thi / mau
VISIBILITY = r"""
string action = Arg<string>("action");
if (action == "reset_all")
{
    Doc.Models.ResetAllHidden();
    return new JObject { ["action"] = action };
}
ModelItemCollection items = Resolve(Args["selector"]);
if (items.Count == 0) throw new InvalidOperationException("selector khong khop item nao.");

if (action == "hide") Doc.Models.SetHidden(items, true);
else if (action == "show") Doc.Models.SetHidden(items, false);
else if (action == "isolate")
{
    // An moi hinh hoc KHONG thuoc cac item (va con chau cua chung); khong dung den item cha.
    Doc.Models.ResetAllHidden();
    var keep = new List<ModelItem>();
    foreach (ModelItem it in items) foreach (ModelItem d in it.DescendantsAndSelf) keep.Add(d);
    var hide = new ModelItemCollection();
    foreach (ModelItem root in Doc.Models.RootItems)
        foreach (ModelItem d in root.DescendantsAndSelf)
            if (d.HasGeometry && !keep.Contains(d)) hide.Add(d);
    Doc.Models.SetHidden(hide, true);
}
else throw new ArgumentException("action phai la hide | show | isolate | reset_all.");
return new JObject { ["action"] = action, ["items"] = items.Count };
"""

APPEARANCE = r"""
if (Arg<bool>("reset_all", false))
{
    Doc.Models.ResetAllPermanentMaterials();
    return new JObject { ["reset_all"] = true };
}
ModelItemCollection items = Resolve(Args["selector"]);
if (items.Count == 0) throw new InvalidOperationException("selector khong khop item nao.");

if (Arg<bool>("reset", false))
{
    Doc.Models.ResetPermanentMaterials(items);
    return new JObject { ["reset"] = true, ["items"] = items.Count };
}
var color = Args["color"] as JArray;
bool hasT = Args["transparency"] != null && Args["transparency"].Type != JTokenType.Null;
if (color == null && !hasT) throw new ArgumentException("Can color [r,g,b] (0-255) va/hoac transparency (0..1) hoac reset=true.");
if (color != null)
    Doc.Models.OverridePermanentColor(items, Autodesk.Navisworks.Api.Color.FromByteRGB((byte)(int)color[0], (byte)(int)color[1], (byte)(int)color[2]));
if (hasT) Doc.Models.OverridePermanentTransparency(items, Arg<double>("transparency"));
return new JObject { ["items"] = items.Count, ["color"] = color, ["transparency"] = hasT ? (double?)Arg<double>("transparency") : null };
"""

# --------------------------------------------------------------------------- viewpoint
_SAVED_WALK = r"""
JArray WalkSaved(IEnumerable<SavedItem> col, string prefix)
{
    var arr = new JArray();
    foreach (SavedItem si in col)
    {
        var g = si as GroupItem;
        var o = new JObject
        {
            ["name"] = si.DisplayName,
            ["path"] = prefix + si.DisplayName,
            ["type"] = g != null ? "folder" : (si is SavedViewpoint ? "viewpoint" : si.GetType().Name)
        };
        if (g != null) o["children"] = WalkSaved(g.Children, prefix + si.DisplayName + "/");
        arr.Add(o);
    }
    return arr;
}

SavedItem FindSaved(IEnumerable<SavedItem> col, string name, string prefix)
{
    foreach (SavedItem si in col)
    {
        string path = prefix + si.DisplayName;
        if (string.Equals(si.DisplayName, name, StringComparison.OrdinalIgnoreCase) || string.Equals(path, name, StringComparison.OrdinalIgnoreCase))
            return si;
        var g = si as GroupItem;
        if (g != null)
        {
            SavedItem hit = FindSaved(g.Children, name, path + "/");
            if (hit != null) return hit;
        }
    }
    return null;
}
"""

VIEWPOINT_LIST = _SAVED_WALK + r"""
return new JObject { ["viewpoints"] = WalkSaved(Doc.SavedViewpoints.Value, "") };
"""

VIEWPOINT_SAVE = r"""
string name = Arg<string>("name");
var vp = new SavedViewpoint(Doc.CurrentViewpoint.CreateCopy());
vp.DisplayName = name;
Doc.SavedViewpoints.AddCopy(vp);
return new JObject { ["saved"] = name };
"""

VIEWPOINT_APPLY = _SAVED_WALK + r"""
string name = Arg<string>("name");
var vp = FindSaved(Doc.SavedViewpoints.Value, name, "") as SavedViewpoint;
if (vp == null) throw new ArgumentException("Khong tim thay viewpoint '" + name + "' (dung nw_list_viewpoints de xem ten/duong dan).");
Doc.CurrentViewpoint.CopyFrom(vp.Viewpoint);
return new JObject { ["applied"] = vp.DisplayName };
"""

FOCUS_SELECTION = r"""
if (Doc.CurrentSelection.SelectedItems.Count == 0) throw new InvalidOperationException("Chua chon item nao de zoom toi.");
Doc.ActiveView.FocusOnCurrentSelection();
return new JObject { ["focused"] = Doc.CurrentSelection.SelectedItems.Count };
"""

# Chup viewport 3D (khong gom ribbon/cay). Ham tra ve anh trong lop View khac nhau giua cac ban nen duyet
# bang reflection: thu cac ham tra ve System.Drawing.Image co 0 tham so hoac (int, int).
CAPTURE_VIEWPORT = r"""
object view = Doc.GetType().GetProperty("ActiveView") != null ? Doc.GetType().GetProperty("ActiveView").GetValue(Doc, null) : null;
if (view == null) throw new InvalidOperationException("Khong lay duoc Doc.ActiveView.");
int w = Arg<int>("width", 1600), h = Arg<int>("height", 900);
var tried = new JArray();
System.Drawing.Image img = null;
string usedMethod = null;
foreach (var m in view.GetType().GetMethods())
{
    if (!typeof(System.Drawing.Image).IsAssignableFrom(m.ReturnType)) continue;
    var ps = m.GetParameters();
    object[] callArgs;
    if (ps.Length == 0) callArgs = new object[0];
    else if (ps.Length == 2 && ps[0].ParameterType == typeof(int) && ps[1].ParameterType == typeof(int)) callArgs = new object[] { w, h };
    else continue;
    tried.Add(m.Name + "(" + ps.Length + ")");
    try
    {
        img = (System.Drawing.Image)m.Invoke(view, callArgs);
        if (img != null) { usedMethod = m.Name; break; }
    }
    catch (Exception ex) { tried.Add("  loi: " + (ex.InnerException != null ? ex.InnerException.Message : ex.Message)); }
}
if (img == null)
    throw new InvalidOperationException("Khong ham nao cua " + view.GetType().FullName + " tra ve anh (da thu: " + tried.ToString(Newtonsoft.Json.Formatting.None) + "). Dung nw_explore_api(type_filter='.View') de tim ham.");
using (img)
using (var ms = new MemoryStream())
{
    img.Save(ms, System.Drawing.Imaging.ImageFormat.Png);
    return new JObject { ["method"] = usedMethod, ["width"] = img.Width, ["height"] = img.Height, ["data_base64"] = Convert.ToBase64String(ms.ToArray()) };
}
"""

# --------------------------------------------------------------------------- selection set
SELECTION_SET_LIST = _SAVED_WALK + r"""
return new JObject { ["selection_sets"] = WalkSaved(Doc.SelectionSets.Value, "") };
"""

SELECTION_SET_CREATE = r"""
string name = Arg<string>("name");
ModelItemCollection items = Resolve(Args["selector"]);
if (items.Count == 0) throw new InvalidOperationException("selector khong khop item nao.");
var set = new SelectionSet(items);
set.DisplayName = name;
Doc.SelectionSets.AddCopy(set);
return new JObject { ["created"] = name, ["items"] = items.Count };
"""

SELECTION_SET_SELECT = _SAVED_WALK + r"""
string name = Arg<string>("name");
var set = FindSaved(Doc.SelectionSets.Value, name, "") as SelectionSet;
if (set == null) throw new ArgumentException("Khong tim thay selection set '" + name + "'.");
ModelItemCollection items = set.GetSelectedItems();
Doc.CurrentSelection.Clear();
Doc.CurrentSelection.CopyFrom(items);
return new JObject { ["selected"] = items.Count, ["set"] = set.DisplayName };
"""

# --------------------------------------------------------------------------- clash detective
# Cac bien the dong using thu lan luot (vi tri lop DocumentClash/GetClash khac nhau giua cac ban).
CLASH_HEADERS = (
    "using Autodesk.Navisworks.Api.Clash;\n",
    "using Autodesk.Navisworks.Api.Clash;\nusing Autodesk.Navisworks.Api.DocumentParts;\n",
    "using Autodesk.Navisworks.Api.DocumentParts;\n",
)

_CLASH_COMMON = r"""
string Pr(object o, string name)
{
    if (o == null) return null;
    var p = o.GetType().GetProperty(name);
    if (p == null) return null;
    try { var v = p.GetValue(o, null); return v == null ? null : v.ToString(); } catch { return null; }
}

IEnumerable<ClashTest> AllTests(IEnumerable<SavedItem> col)
{
    foreach (SavedItem si in col)
    {
        var t = si as ClashTest;
        if (t != null) yield return t;
        var g = si as GroupItem;
        if (g != null && t == null) foreach (var x in AllTests(g.Children)) yield return x;
    }
}

ClashTest FindTest(DocumentClashTests tests, string name)
{
    foreach (var t in AllTests(tests.Tests))
        if (string.Equals(t.DisplayName, name, StringComparison.OrdinalIgnoreCase)) return t;
    throw new ArgumentException("Khong tim thay clash test '" + name + "' (dung nw_clash_list_tests).");
}

JObject Summary(ClashTest t)
{
    var s = t.Summary;
    return new JObject
    {
        ["total"] = Pr(s, "Total"), ["new"] = Pr(s, "New"), ["active"] = Pr(s, "Active"),
        ["reviewed"] = Pr(s, "Reviewed"), ["approved"] = Pr(s, "Approved"), ["resolved"] = Pr(s, "Resolved")
    };
}

// Cho phep selector {"selection_set": "ten"} ben canh selector thong thuong.
ModelItemCollection ResolveAny(JToken sel)
{
    var o = sel as JObject;
    if (o != null && o["selection_set"] != null)
    {
        string name = (string)o["selection_set"];
        SelectionSet found = null;
        void Find(IEnumerable<SavedItem> col)
        {
            foreach (SavedItem si in col)
            {
                var ss = si as SelectionSet;
                if (ss != null && string.Equals(ss.DisplayName, name, StringComparison.OrdinalIgnoreCase)) { found = ss; return; }
                var g = si as GroupItem;
                if (g != null) { Find(g.Children); if (found != null) return; }
            }
        }
        Find(Doc.SelectionSets.Value);
        if (found == null) throw new ArgumentException("Khong tim thay selection set '" + name + "'.");
        return found.GetSelectedItems();
    }
    return Resolve(sel);
}

DocumentClash dc = Doc.GetClash();
DocumentClashTests tests = dc.TestsData;
"""

CLASH_LIST_TESTS = _CLASH_COMMON + r"""
var arr = new JArray();
foreach (var t in AllTests(tests.Tests))
    arr.Add(new JObject
    {
        ["name"] = t.DisplayName, ["status"] = Pr(t, "Status"), ["type"] = Pr(t, "TestType"),
        ["tolerance_m"] = double.TryParse(Pr(t, "Tolerance"), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double tol) ? (double?)(tol * MetersPerUnit) : null,
        ["summary"] = Summary(t)
    });
return new JObject { ["tests"] = arr };
"""

CLASH_CREATE_TEST = _CLASH_COMMON + r"""
string name = Arg<string>("name");
string type = Arg<string>("test_type", "hard");
double tolM = Arg<double>("tolerance_m", 0.0);
ModelItemCollection a = ResolveAny(Args["selection_a"]);
ModelItemCollection b = ResolveAny(Args["selection_b"]);
if (a.Count == 0) throw new InvalidOperationException("selection_a khong khop item nao.");
if (b.Count == 0) throw new InvalidOperationException("selection_b khong khop item nao.");

var test = new ClashTest();
test.DisplayName = name;
test.TestType = (ClashTestType)Enum.Parse(typeof(ClashTestType), type, true);
test.Tolerance = tolM / MetersPerUnit;
test.SelectionA.Selection.CopyFrom(a);
test.SelectionB.Selection.CopyFrom(b);
if (Arg<bool>("self_intersect_a", false)) test.SelectionA.SelfIntersect = true;
if (Arg<bool>("self_intersect_b", false)) test.SelectionB.SelfIntersect = true;
tests.TestsAddCopy(test);

string note = null;
if (Arg<bool>("run", true))
{
    var added = FindTest(tests, name);
    tests.TestsRunTest(added);
    return new JObject { ["created"] = name, ["a_items"] = a.Count, ["b_items"] = b.Count, ["ran"] = true, ["summary"] = Summary(FindTest(tests, name)) };
}
return new JObject { ["created"] = name, ["a_items"] = a.Count, ["b_items"] = b.Count, ["ran"] = false, ["note"] = note };
"""

CLASH_RUN_TEST = _CLASH_COMMON + r"""
string name = Arg<string>("name");
if (string.IsNullOrEmpty(name)) { tests.TestsRunAllTests(); return new JObject { ["ran"] = "all" }; }
var t = FindTest(tests, name);
tests.TestsRunTest(t);
return new JObject { ["ran"] = name, ["summary"] = Summary(FindTest(tests, name)) };
"""

CLASH_RESULTS = _CLASH_COMMON + r"""
string name = Arg<string>("name");
string statusFilter = Arg<string>("status");
int limit = Math.Max(Arg<int>("limit", 200), 1);
var test = FindTest(tests, name);

var results = new List<ClashResult>();
void Collect(IEnumerable<SavedItem> col)
{
    foreach (SavedItem si in col)
    {
        var r = si as ClashResult;
        if (r != null) { results.Add(r); continue; }
        var g = si as GroupItem;
        if (g != null) Collect(g.Children);
    }
}
Collect(test.Children);

string Where(ModelItem it)
{
    if (it == null) return null;
    var names = new List<string>();
    for (ModelItem c = it; c != null; c = c.Parent) names.Add(c.DisplayName);
    names.Reverse();
    return string.Join(" > ", names.Where(n => !string.IsNullOrEmpty(n)));
}

var arr = new JArray();
int matched = 0;
foreach (var r in results)
{
    string st = Pr(r, "Status");
    if (!string.IsNullOrEmpty(statusFilter) && !string.Equals(st, statusFilter, StringComparison.OrdinalIgnoreCase)) continue;
    matched++;
    if (arr.Count >= limit) continue;
    var o = new JObject { ["name"] = r.DisplayName, ["status"] = st };
    double d;
    if (double.TryParse(Pr(r, "Distance"), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out d)) o["distance_m"] = Math.Round(d * MetersPerUnit, 5);
    var c = r.Center;
    if (c != null) o["point_m"] = new JArray(Math.Round(c.X * MetersPerUnit, 4), Math.Round(c.Y * MetersPerUnit, 4), Math.Round(c.Z * MetersPerUnit, 4));
    o["item1"] = new JObject { ["ref"] = r.Item1 != null ? RefOf(r.Item1) : null, ["name"] = r.Item1 != null ? r.Item1.DisplayName : null, ["path"] = Where(r.Item1) };
    o["item2"] = new JObject { ["ref"] = r.Item2 != null ? RefOf(r.Item2) : null, ["name"] = r.Item2 != null ? r.Item2.DisplayName : null, ["path"] = Where(r.Item2) };
    arr.Add(o);
}
return new JObject { ["test"] = test.DisplayName, ["total_results"] = results.Count, ["matched"] = matched, ["returned"] = arr.Count, ["results"] = arr };
"""

# --------------------------------------------------------------------------- timeliner
TIMELINER_HEADERS = (
    "using Autodesk.Navisworks.Api.Timeliner;\n",
    "using Autodesk.Navisworks.Api.Timeliner;\nusing Autodesk.Navisworks.Api.DocumentParts;\n",
)

TIMELINER_TASKS = r"""
string Pr(object o, string name)
{
    if (o == null) return null;
    var p = o.GetType().GetProperty(name);
    if (p == null) return null;
    try { var v = p.GetValue(o, null); return v == null ? null : v.ToString(); } catch { return null; }
}

DocumentTimeliner tl = Doc.GetTimeliner();
int limit = Math.Max(Arg<int>("limit", 500), 1);
int count = 0;

JArray Walk(IEnumerable<SavedItem> col, int depth)
{
    var arr = new JArray();
    foreach (SavedItem si in col)
    {
        if (++count > limit) break;
        var o = new JObject
        {
            ["name"] = si.DisplayName, ["depth"] = depth,
            ["task_type"] = Pr(si, "SimulationTaskTypeName"),
            ["planned_start"] = Pr(si, "PlannedStartDate"), ["planned_end"] = Pr(si, "PlannedEndDate"),
            ["actual_start"] = Pr(si, "ActualStartDate"), ["actual_end"] = Pr(si, "ActualEndDate"),
            ["progress"] = Pr(si, "Progress")
        };
        var g = si as GroupItem;
        if (g != null && g.Children.Count > 0) o["children"] = Walk(g.Children, depth + 1);
        arr.Add(o);
    }
    return arr;
}

return new JObject { ["tasks"] = Walk(tl.Tasks, 0), ["truncated"] = count > limit };
"""
