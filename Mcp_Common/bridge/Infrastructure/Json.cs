using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace McpBridge.Infrastructure
{
    internal static class Json
    {
        // Doi tuong cua SDK (Bentley.* : Element, DgnModel...; Autodesk.* : ModelItem, Document...)
        // co do thi tham chieu rat lon/vong va getter co the nem loi -> chi ghi ToString()
        // thay vi serialize sau.
        private sealed class VendorToStringConverter : JsonConverter
        {
            public override bool CanConvert(Type t) =>
                t.Namespace != null
                && (t.Namespace.StartsWith("Bentley", StringComparison.Ordinal)
                    || t.Namespace.StartsWith("Autodesk", StringComparison.Ordinal));

            public override void WriteJson(JsonWriter writer, object value, JsonSerializer serializer) =>
                writer.WriteValue(value?.ToString());

            public override object ReadJson(JsonReader r, Type t, object v, JsonSerializer s) =>
                throw new NotSupportedException();

            public override bool CanRead => false;
        }

        private static readonly JsonSerializer Serializer = JsonSerializer.Create(new JsonSerializerSettings
        {
            ReferenceLoopHandling = ReferenceLoopHandling.Ignore,
            Converters = { new VendorToStringConverter() },
            Error = (s, e) => e.ErrorContext.Handled = true
        });

        public static JToken ToToken(object value)
        {
            if (value == null) return JValue.CreateNull();
            if (value is JToken token) return token;
            try { return JToken.FromObject(value, Serializer); }
            catch { return new JValue(value.ToString()); }
        }
    }

    // Doc tham so tu JObject, bao loi ro rang bang tieng Viet cho LLM tu sua.
    internal static class P
    {
        public static bool Has(JObject p, string key) => p[key] != null && p[key].Type != JTokenType.Null;

        public static string Str(JObject p, string key, string def = null) => Has(p, key) ? (string)p[key] : def;

        public static string ReqStr(JObject p, string key)
        {
            string s = Str(p, key);
            if (string.IsNullOrWhiteSpace(s)) throw new ArgumentException($"Thieu tham so bat buoc '{key}'.");
            return s;
        }

        public static double Dbl(JObject p, string key, double def) => Has(p, key) ? (double)p[key] : def;

        public static int Int(JObject p, string key, int def) => Has(p, key) ? (int)p[key] : def;

        public static bool Bool(JObject p, string key, bool def) => Has(p, key) ? (bool)p[key] : def;

        public static List<string> StrList(JObject p, string key)
        {
            if (!Has(p, key)) return new List<string>();
            if (p[key].Type == JTokenType.String) return new List<string> { (string)p[key] };
            return p[key].Select(t => (string)t).ToList();
        }

        public static List<long> LongList(JObject p, string key)
        {
            if (!Has(p, key)) return new List<long>();
            if (p[key].Type != JTokenType.Array) return new List<long> { (long)p[key] };
            return p[key].Select(t => (long)t).ToList();
        }

        // Chap nhan [x, y, z] hoac {"x":..,"y":..,"z":..}; thieu z -> 0.
        public static double[] Xyz(JToken t, string what)
        {
            if (t == null || t.Type == JTokenType.Null) throw new ArgumentException($"Thieu toa do '{what}'.");
            if (t.Type == JTokenType.Array)
            {
                var a = t.Select(v => (double)v).ToArray();
                if (a.Length < 2) throw new ArgumentException($"Toa do '{what}' can it nhat [x, y].");
                return new[] { a[0], a[1], a.Length > 2 ? a[2] : 0.0 };
            }
            return new[] { (double)t["x"], (double)t["y"], t["z"] != null ? (double)t["z"] : 0.0 };
        }

        public static double[] ReqXyz(JObject p, string key) => Xyz(p[key], key);
    }
}
