using Newtonsoft.Json.Linq;
using BentleyMcp.Infrastructure;
using BIM = Bentley.Interop.MicroStationDGN;

namespace BentleyMcp.Handlers
{
    // Lop "dung duoc moi cong cu": moi nut tren ribbon OpenTunnel/OpenBridge Designer deu la mot key-in.
    // Gui key-in + data point + reset vao CadInputQueue tuong duong nguoi dung go/click,
    // ke ca cac lenh tunnel/civil KHONG co API cong khai.
    //
    // Luu y: hang doi chi duoc xu ly SAU khi handler tra ve main loop, nen ket qua cua
    // key-in khong thay ngay trong cung request -> MCP server se goi request sau de kiem tra.
    internal static class InputHandlers
    {
        public static void Register(RpcRegistry r)
        {
            r.Add("keyin.send", true, "Gui 1 hoac nhieu key-in vao hang doi (keyins)", p =>
            {
                var queue = Mstn.App.CadInputQueue;
                var sent = new JArray();
                foreach (string keyin in P.StrList(p, "keyins"))
                {
                    if (string.IsNullOrWhiteSpace(keyin)) continue;
                    queue.SendKeyin(keyin);
                    sent.Add(keyin);
                }
                return new JObject { ["queued"] = sent };
            });

            r.Add("input.data_point", true, "Gui data point (click trai) tai toa do met (point, view)", p =>
            {
                double[] m = P.ReqXyz(p, "point");
                var units = Units.Of(Mstn.ActiveModel);
                var pt = new BIM.Point3d
                {
                    X = units.MetersToMaster(m[0]),
                    Y = units.MetersToMaster(m[1]),
                    Z = units.MetersToMaster(m[2])
                };
                Mstn.App.CadInputQueue.SendDataPoint(pt, P.Int(p, "view", 1));
                return new JObject { ["queued"] = "data_point", ["point_m"] = new JArray(m[0], m[1], m[2]) };
            });

            r.Add("input.reset", true, "Gui reset (click phai) - ket thuc/huy buoc hien tai", p =>
            {
                Mstn.App.CadInputQueue.SendReset();
                return new JObject { ["queued"] = "reset" };
            });

            r.Add("cexpr.get", true, "Doc gia tri C expression cua MicroStation (expression, app)", p =>
            {
                string app = P.Str(p, "app");
                object v = string.IsNullOrEmpty(app)
                    ? Mstn.App.GetCExpressionValue(P.ReqStr(p, "expression"))
                    : Mstn.App.GetCExpressionValue(P.ReqStr(p, "expression"), app);
                return new JObject { ["value"] = Json.ToToken(v) };
            });
        }
    }
}
