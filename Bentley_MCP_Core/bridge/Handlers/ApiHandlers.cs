using System;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;

namespace BentleyMcp.Handlers
{
    // Kham pha API .NET dang nap trong san pham bang reflection (chi doc metadata -> an toan
    // tren thread nen). Dung de tim namespace/class cua OpenTunnel/OpenBridge, OpenRoads (CifNET)...
    // truoc khi viet script.csharp, thay vi doan ten API.
    internal static class ApiHandlers
    {
        private const BindingFlags PublicMembers =
            BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly;

        public static void Register(RpcRegistry r)
        {
            r.Add("api.assemblies", false, "Liet ke assembly dang nap (filter)", p =>
            {
                string filter = P.Str(p, "filter");
                return new JArray(AppDomain.CurrentDomain.GetAssemblies()
                    .Select(a => a.GetName())
                    .Where(n => filter == null || n.Name.IndexOf(filter, StringComparison.OrdinalIgnoreCase) >= 0)
                    .OrderBy(n => n.Name)
                    .Select(n => new JObject { ["name"] = n.Name, ["version"] = n.Version?.ToString() }));
            });

            r.Add("api.types", false, "Tim type public (assembly_filter, type_filter, include_members, limit)", p =>
            {
                string asmFilter = P.Str(p, "assembly_filter");
                string typeFilter = P.Str(p, "type_filter");
                bool members = P.Bool(p, "include_members", false);
                int limit = Math.Min(Math.Max(P.Int(p, "limit", 100), 1), 1000);

                var result = new JArray();
                foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
                {
                    if (a.IsDynamic) continue;
                    if (asmFilter != null && a.GetName().Name.IndexOf(asmFilter, StringComparison.OrdinalIgnoreCase) < 0) continue;

                    Type[] types;
                    try { types = a.GetExportedTypes(); }
                    catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null && t.IsPublic).ToArray(); }
                    catch { continue; }

                    foreach (Type t in types)
                    {
                        if (typeFilter != null && (t.FullName ?? "").IndexOf(typeFilter, StringComparison.OrdinalIgnoreCase) < 0) continue;
                        var o = new JObject
                        {
                            ["type"] = t.FullName,
                            ["assembly"] = a.GetName().Name,
                            ["kind"] = t.IsEnum ? "enum" : t.IsInterface ? "interface" : t.IsValueType ? "struct" : "class",
                            ["base"] = t.BaseType?.FullName
                        };
                        if (members) o["members"] = Members(t);
                        result.Add(o);
                        if (result.Count >= limit) return result;
                    }
                }
                return result;
            });
        }

        private static JArray Members(Type t)
        {
            var arr = new JArray();
            try
            {
                if (t.IsEnum)
                {
                    foreach (string n in Enum.GetNames(t)) arr.Add(n);
                    return arr;
                }
                foreach (MemberInfo m in t.GetMembers(PublicMembers).Take(300))
                {
                    switch (m)
                    {
                        case MethodInfo mi when !mi.IsSpecialName:
                            arr.Add($"{(mi.IsStatic ? "static " : "")}{mi.ReturnType.Name} {mi.Name}(" +
                                    string.Join(", ", mi.GetParameters().Select(x => $"{(x.ParameterType.IsByRef ? "ref " : "")}{x.ParameterType.Name} {x.Name}")) + ")");
                            break;
                        case PropertyInfo pi:
                            arr.Add($"prop {pi.PropertyType.Name} {pi.Name} {{{(pi.CanRead ? " get;" : "")}{(pi.CanWrite ? " set;" : "")} }}");
                            break;
                        case ConstructorInfo ci:
                            arr.Add("ctor(" + string.Join(", ", ci.GetParameters().Select(x => $"{x.ParameterType.Name} {x.Name}")) + ")");
                            break;
                        case FieldInfo fi:
                            arr.Add($"field {fi.FieldType.Name} {fi.Name}");
                            break;
                        case EventInfo ei:
                            arr.Add($"event {ei.EventHandlerType?.Name} {ei.Name}");
                            break;
                    }
                }
            }
            catch (Exception ex)
            {
                arr.Add("<loi reflection: " + ex.Message + ">");
            }
            return arr;
        }
    }
}
