using System;
using Bentley.DgnPlatformNET;
using Bentley.DgnPlatformNET.Elements;
using Bentley.GeometryNET;
using Bentley.MstnPlatformNET;
using Newtonsoft.Json.Linq;
using BIM = Bentley.Interop.MicroStationDGN;

namespace BentleyMcp.Infrastructure
{
    // Truy cap nhanh session/model/COM cua san pham. CHI goi tren main thread.
    internal static class Mstn
    {
        public static BIM.Application App => Bentley.MstnPlatformNET.InteropServices.Utilities.ComApp;

        public static DgnFile ActiveFile => Session.Instance.GetActiveDgnFile()
            ?? throw new InvalidOperationException($"Chua mo file DGN nao trong {ProductInfo.Name}.");

        public static DgnModel ActiveModel => Session.Instance.GetActiveDgnModel()
            ?? throw new InvalidOperationException("Khong co model active.");

        public static T Safe<T>(Func<T> f, T fallback = default(T))
        {
            try { return f(); } catch { return fallback; }
        }

        // ElementId <-> long. ToString() cua ElementId tra ve so nguyen 64-bit.
        public static long IdOf(Element el) => long.Parse(el.ElementId.ToString());

        public static Element FindById(DgnModel model, long id)
        {
            var eid = new ElementId(ref id);
            return model.FindElementById(eid)
                ?? throw new ArgumentException($"Khong tim thay element id={id} trong model active.");
        }
    }

    // Quy doi giua UOR (don vi luu tru noi bo) va met theo he toa do hien thi:
    //     toa_do_met = (UOR - GlobalOrigin) / UorPerMeter
    // Moi toa do trao doi voi MCP deu tinh bang MET de khong phu thuoc master unit cua seed.
    internal sealed class Units
    {
        public readonly double UorPerMeter;
        public readonly double UorPerMaster;
        public readonly DPoint3d GlobalOrigin;

        private Units(double uorPerMeter, double uorPerMaster, DPoint3d go)
        {
            UorPerMeter = uorPerMeter;
            UorPerMaster = uorPerMaster;
            GlobalOrigin = go;
        }

        public static Units Of(DgnModel model)
        {
            ModelInfo info = model.GetModelInfo();
            double perMeter = info.UorPerMeter;
            double perMaster = Mstn.Safe(() => info.UorPerMaster, perMeter);
            DPoint3d go = Mstn.Safe(() => info.GlobalOrigin, new DPoint3d(0, 0, 0));
            return new Units(perMeter, perMaster, go);
        }

        public DPoint3d ToUor(double[] m) =>
            new DPoint3d(GlobalOrigin.X + m[0] * UorPerMeter, GlobalOrigin.Y + m[1] * UorPerMeter, GlobalOrigin.Z + m[2] * UorPerMeter);

        public JArray ToMeters(DPoint3d uor) => new JArray(
            Math.Round((uor.X - GlobalOrigin.X) / UorPerMeter, 6),
            Math.Round((uor.Y - GlobalOrigin.Y) / UorPerMeter, 6),
            Math.Round((uor.Z - GlobalOrigin.Z) / UorPerMeter, 6));

        // Interop CadInputQueue nhan toa do theo MASTER UNIT cua file.
        public double MetersToMaster(double meters) => meters * UorPerMeter / UorPerMaster;

        public JObject Describe() => new JObject
        {
            ["uor_per_meter"] = UorPerMeter,
            ["uor_per_master"] = UorPerMaster,
            ["master_units_per_meter"] = UorPerMeter / UorPerMaster,
            ["global_origin_uor"] = new JArray(GlobalOrigin.X, GlobalOrigin.Y, GlobalOrigin.Z)
        };
    }
}
