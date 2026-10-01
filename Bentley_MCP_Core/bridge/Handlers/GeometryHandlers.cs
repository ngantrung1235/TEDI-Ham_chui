using System;
using System.Collections.Generic;
using System.Linq;
using Bentley.DgnPlatformNET;
using Bentley.DgnPlatformNET.Elements;
using Bentley.GeometryNET;
using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;

namespace BentleyMcp.Handlers
{
    internal static class GeometryHandlers
    {
        public static void Register(RpcRegistry r)
        {
            r.Add("geometry.polyline", true, "Ve line string / shape kin (points [m], closed, level)", Polyline);
            r.Add("geometry.extrusion", true,
                "Dun (extrude) tiet dien 2D theo truc origin->end (loops trong he toa do tiet dien, met)", Extrusion);
        }

        private static object Polyline(JObject p)
        {
            DgnModel model = Mstn.ActiveModel;
            Units units = Units.Of(model);
            List<DPoint3d> pts = ((JArray)p["points"] ?? new JArray()).Select(t => units.ToUor(P.Xyz(t, "points[]"))).ToList();
            bool closed = P.Bool(p, "closed", false);
            if (pts.Count < 2 || (closed && pts.Count < 3)) throw new ArgumentException("Can it nhat 2 diem (3 diem neu closed).");
            if (pts.Count > 5000) throw new ArgumentException("Toi da 5000 diem / element.");

            Element el = closed
                ? (Element)new ShapeElement(model, null, pts.ToArray())
                : new LineStringElement(model, null, pts.ToArray());
            LevelHandlers.ApplyLevel(el, P.Str(p, "level"));
            el.AddToModel();
            return new JObject { ["id"] = Mstn.IdOf(el), ["points"] = pts.Count, ["closed"] = closed };
        }

        // Tham so:
        //   origin, end      : diem dau/cuoi truc dun [x,y,z] (met).
        //   loops            : [{ "role": "outer"|"hole", "points": [[u,v], ...] }] (met)
        //                      u = phuong ngang tiet dien (duong ve ben TRAI chieu origin->end),
        //                      v = phuong dung (len tren).
        //   section_plane    : "vertical" (mac dinh) - tiet dien nam trong mat phang THANG DUNG
        //                      vuong goc hinh chieu bang cua truc -> tuong thang dung khi truc co doc
        //                      (dung cho ham hop/cong hop dat theo doc doc).
        //                      "perpendicular" - tiet dien vuong goc truc 3D (ham co doc lon, TBM...).
        //   level            : ten level (tu tao neu chua co).
        private static object Extrusion(JObject p)
        {
            double[] o = P.ReqXyz(p, "origin");
            double[] e = P.ReqXyz(p, "end");
            double[] d = { e[0] - o[0], e[1] - o[1], e[2] - o[2] };
            double len = Norm(d);
            if (len < 1e-6) throw new ArgumentException("origin trung end - truc dun co chieu dai 0.");

            double[] e1, e2;
            string plane = (P.Str(p, "section_plane", "vertical") ?? "vertical").ToLowerInvariant();
            if (plane == "vertical")
            {
                double h = Math.Sqrt(d[0] * d[0] + d[1] * d[1]);
                if (h < 1e-9) throw new ArgumentException("Truc thang dung: dung section_plane='perpendicular'.");
                e1 = new[] { -d[1] / h, d[0] / h, 0.0 };   // Z x truc_bang
                e2 = new[] { 0.0, 0.0, 1.0 };
            }
            else if (plane == "perpendicular")
            {
                double[] u = { d[0] / len, d[1] / len, d[2] / len };
                e1 = Math.Abs(u[2]) > 0.999999 ? new[] { 1.0, 0.0, 0.0 } : Normalize(Cross(new[] { 0.0, 0.0, 1.0 }, u));
                e2 = Cross(u, e1);
            }
            else throw new ArgumentException("section_plane chi nhan 'vertical' hoac 'perpendicular'.");

            DgnModel model = Mstn.ActiveModel;
            Units units = Units.Of(model);

            var loops = (JArray)p["loops"] ?? throw new ArgumentException("Thieu 'loops'.");
            CurveVector outer = null;
            var holes = new List<CurveVector>();
            foreach (JObject loop in loops.OfType<JObject>())
            {
                var uv = ((JArray)loop["points"] ?? new JArray()).Select(t => new[] { (double)t[0], (double)t[1] }).ToList();
                if (uv.Count < 3) throw new ArgumentException("Moi loop can it nhat 3 diem.");
                double[] first = uv[0], last = uv[uv.Count - 1];
                if (Math.Abs(first[0] - last[0]) > 1e-9 || Math.Abs(first[1] - last[1]) > 1e-9) uv.Add(first);

                var pts = uv.Select(q => units.ToUor(new[]
                {
                    o[0] + q[0] * e1[0] + q[1] * e2[0],
                    o[1] + q[0] * e1[1] + q[1] * e2[1],
                    o[2] + q[0] * e1[2] + q[1] * e2[2]
                })).ToList();

                bool isHole = string.Equals(P.Str(loop, "role", "outer"), "hole", StringComparison.OrdinalIgnoreCase);
                CurveVector cv = CurveVector.CreateLinear(pts, isHole ? CurveVector.BoundaryType.Inner : CurveVector.BoundaryType.Outer, false);
                if (isHole) holes.Add(cv);
                else if (outer == null) outer = cv;
                else throw new ArgumentException("Chi ho tro 1 loop 'outer' moi lan dun; goi nhieu lan cho nhieu khoi.");
            }
            if (outer == null) throw new ArgumentException("Can 1 loop role='outer'.");

            CurveVector profile = outer;
            if (holes.Count > 0)
            {
                profile = new CurveVector(CurveVector.BoundaryType.ParityRegion);
                profile.Add(CurvePrimitive.CreateChildCurveVector(outer));
                foreach (CurveVector h in holes) profile.Add(CurvePrimitive.CreateChildCurveVector(h));
            }

            var sweep = new DVector3d(d[0] * units.UorPerMeter, d[1] * units.UorPerMeter, d[2] * units.UorPerMeter);
            SolidPrimitive solid = SolidPrimitive.CreateDgnExtrusion(new DgnExtrusionDetail(profile, sweep, true));
            Element el = DraftingElementSchema.ToElement(model, solid, null)
                ?? throw new InvalidOperationException("DraftingElementSchema.ToElement tra ve null (tiet dien khong hop le?).");
            LevelHandlers.ApplyLevel(el, P.Str(p, "level"));
            el.AddToModel();

            return new JObject
            {
                ["id"] = Mstn.IdOf(el),
                ["length_m"] = Math.Round(len, 6),
                ["holes"] = holes.Count,
                ["section_plane"] = plane
            };
        }

        private static double Norm(double[] v) => Math.Sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);

        private static double[] Normalize(double[] v)
        {
            double n = Norm(v);
            return new[] { v[0] / n, v[1] / n, v[2] / n };
        }

        private static double[] Cross(double[] a, double[] b) => new[]
        {
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]
        };
    }
}
