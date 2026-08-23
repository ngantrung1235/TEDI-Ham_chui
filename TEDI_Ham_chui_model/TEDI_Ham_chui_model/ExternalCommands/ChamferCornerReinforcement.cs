using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // ============================================================================
    // Class chuyen dung de ve THANH THEP CHEO GIA CUONG GOC VAT (Chamfer)
    // tai 2 goc TREN cua long ham (noi TUONG TRONG gap NAP TRONG)
    // dung cho truong hop tiet dien bi vat goc nhu trong ban ve (S6-D12-600(AS)).
    // ============================================================================
    public static class ChamferCornerReinforcement
    {
        private static double MmToFt(double mm) => UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters);
        private static double FtToMm(double ft) => UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Millimeters);

        // Doc tham so Type "Chamfer" (mm) tu FamilyCongHamChui-HT, tra ve DON VI FT
        // (internal units) de dung thang trong tinh toan hinh hoc.
        public static double GetChamferFt(FamilyInstance inst)
        {
            var p = inst.Symbol.LookupParameter("Chamfer");
            if (p == null || !p.HasValue) return 0.0;
            return p.AsDouble(); // da la internal units (ft), giong cach BarModelDiameter dang dung
        }

        // Probe 1 doan ngan tu "diem" theo "candidateDir": neu doan nay cat vao solid
        // (co segment INSIDE) thi candidateDir dung la huong "vao trong be tong";
        // nguoc lai tra ve huong doi dau. Dung SolidCurveIntersection THAT thay vi
        // suy luan hinh hoc tay, de KHONG BAO GIO doan sai chieu (nguyen nhan gay
        // loi thep loi ra ngoai truoc do: huong lui vao be tong tinh tay bi nguoc).
        public static XYZ ResolveIntoConcreteDir(Solid solid, XYZ pointOnEdge, XYZ candidateDir, double probeLenFt)
        {
            var sco = new SolidCurveIntersectionOptions { ResultType = SolidCurveIntersectionMode.CurveSegmentsInside };
            try
            {
                var line = Line.CreateBound(pointOnEdge, pointOnEdge + candidateDir * probeLenFt);
                var sci = solid.IntersectWithCurve(line, sco);
                if (sci != null && sci.SegmentCount > 0) return candidateDir;
            }
            catch { }
            return -candidateDir; // huong nguoc lai
        }

        // Ve thep cheo gia cuong tai 2 goc vat TREN (trai + phai), lap doc theo Lv
        // voi khoang cach lSpacingFt, dung barType/duong kinh rieng (vd D12) va
        // coverFt rieng cho lop nay neu can (mac dinh truyen coverFt chung).
        public static void CreateChamferCornerBars(
            Document d, RebarBarType bt, FamilyInstance inst, Solid solid,
            XYZ Lv, XYZ Wv, XYZ Zv,
            Func<double, double, double, XYZ> L2G,
            List<double> wOff, List<double> zOff,
            double chamferFt, double coverFt,
            double lMinRaw, double lMaxRaw, double lSpacingFt,
            List<string> report, ElementId hostId, ref int totalCount)
        {
            if (chamferFt <= MmToFt(1)) return; // khong co vat goc (Chamfer = 0) -> bo qua

            double w0 = wOff[0], w1 = wOff[1], w2 = wOff[2], w3 = wOff[3];
            double z2 = zOff[2], z3 = zOff[3];

            double lMid = (lMinRaw + lMaxRaw) / 2.0; // vi tri L dai dien de "hoi" solid 1 lan duy nhat
            double probeLenFt = coverFt * 3.0;

            // Diem tho tren canh cheo (chua tru cover) tai vi tri L dai dien, dung de probe.
            XYZ aTraiRaw = L2G(lMid, w1,             z2 - chamferFt);
            XYZ bTraiRaw = L2G(lMid, w1 + chamferFt, z2);
            XYZ midTrai = (aTraiRaw + bTraiRaw) / 2.0;

            XYZ aPhaiRaw = L2G(lMid, w2 - chamferFt, z2);
            XYZ bPhaiRaw = L2G(lMid, w2,             z2 - chamferFt);
            XYZ midPhai = (aPhaiRaw + bPhaiRaw) / 2.0;

            // 2 huong ung vien vuong goc voi canh cheo 45 do (chi khac dau).
            XYZ candTrai = (Wv - Zv).Normalize();
            XYZ candPhai = (-Wv - Zv).Normalize();

            // HOI SOLID THAT de biet huong nao moi la "vao trong be tong" - khong doan tay nua.
            XYZ intoConcreteTrai = ResolveIntoConcreteDir(solid, midTrai, candTrai, probeLenFt);
            XYZ intoConcretePhai = ResolveIntoConcreteDir(solid, midPhai, candPhai, probeLenFt);

            var corners = new (string name, double[] aWZ, double[] bWZ, XYZ into)[]
            {
                ("Goc vat trai (Tuong trai - Nap)", new[]{ w1,             z2 - chamferFt }, new[]{ w1 + chamferFt, z2 }, intoConcreteTrai),
                ("Goc vat phai (Tuong phai - Nap)", new[]{ w2 - chamferFt, z2 },             new[]{ w2,             z2 - chamferFt }, intoConcretePhai),
            };

            double loSafe = lMinRaw + coverFt;
            double hiSafe = lMaxRaw - coverFt;
            double lLen = hiSafe - loSafe;
            if (lLen < MmToFt(20))
            {
                report.Add($"{hostId}: chieu dai L qua ngan, bo qua thep cheo goc vat.");
                return;
            }

            int nRows = (int)Math.Ceiling(lLen / lSpacingFt) + 1;
            if (nRows < 2) nRows = 2;
            double rowSpacing = lLen / (nRows - 1);

            foreach (var c in corners)
            {
                int made = 0;
                for (int i = 0; i < nRows; i++)
                {
                    double lPos = loSafe + i * rowSpacing;

                    // Tính điểm A, B trên mặt vát (đã lùi vào bê tông)
                    XYZ a = L2G(lPos, c.aWZ[0], c.aWZ[1]) + c.into * coverFt;
                    XYZ b = L2G(lPos, c.bWZ[0], c.bWZ[1]) + c.into * coverFt;

                    if (a.DistanceTo(b) < MmToFt(10)) continue;

                    XYZ dir = (b - a).Normalize();
                    XYZ a_ext = a;
                    XYZ b_ext = b;

                    // Kéo dài thanh thép đâm sâu vào bê tông cho đến khi chạm các mặt ngoài (trừ cover)
                    if (c.name.Contains("trai")) // Góc trái
                    {
                        // A kéo về tường trái ngoài cùng (w0 + cover)
                        double tA = ((w0 + coverFt) - a.DotProduct(Wv)) / dir.DotProduct(Wv);
                        a_ext = a + dir * tA;

                        // B kéo lên nắp trên ngoài cùng (z3 - cover)
                        double tB = ((z3 - coverFt) - b.DotProduct(Zv)) / dir.DotProduct(Zv);
                        b_ext = b + dir * tB;
                    }
                    else // Góc phải
                    {
                        // A kéo lên nắp trên ngoài cùng (z3 - cover)
                        double tA = ((z3 - coverFt) - a.DotProduct(Zv)) / dir.DotProduct(Zv);
                        a_ext = a + dir * tA;

                        // B kéo về tường phải ngoài cùng (w3 - cover)
                        double tB = ((w3 - coverFt) - b.DotProduct(Wv)) / dir.DotProduct(Wv);
                        b_ext = b + dir * tB;
                    }

                    if (a_ext.DistanceTo(b_ext) < MmToFt(20)) continue;

                    var curve = Line.CreateBound(a_ext, b_ext);
                    var terminations = new BarTerminationsData(d);
                    var rebar = Rebar.CreateFromCurves(
                        d, RebarStyle.Standard, bt, inst, Lv,
                        new List<Curve> { curve }, terminations,
                        useExistingShapeIfPossible: false, createNewShape: true);

                    if (rebar == null) continue;
                    rebar.GetShapeDrivenAccessor().SetLayoutAsSingle();
                    made++;
                }
                report.Add($"{hostId}: {c.name} - da tao {made} thanh (đã cắm sâu chạm ranh giới ngoài).");
                totalCount += made;
            }
        }
    }
}
