using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;

namespace TEDI_Ham_chui_model.Models
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
        //
        // Shape thuc te (theo ban ve S5-D16-250): doan cheo B GIU NGUYEN dung cong
        // thuc CU - keo dai theo dung phuong cheo cho toi khi cham mat cover cua
        // TUONG (1 dau) va NAP (dau kia), KHONG doi. Chi THEM 2 chan noi tiep tai 2
        // dau do, mo rong VAO TRONG LONG HAM (khong phai dam sau them vao be tong):
        // dau sat TUONG noi tiep 1 chan chay DOC theo tuong (doc -Zv, huong xuong,
        // lap voi thep doc H) dai extendMm ("vuon"); dau sat NAP noi tiep 1 chan chay
        // DOC theo nap (doc Wv, huong ve tim ham, lap voi S1) CUNG dai extendMm - 1
        // gia tri "vuon" DUY NHAT dung chung cho ca 2 chan.
        //
        // lOffsetMm: offset vi tri bat dau doc Lv (giong het co che "luot 2" cua dai C
        // trong RebarStirrupCLogic.cs - xem lLvOffsetPass2Ft/tieCrossEntries o do) - o
        // day dung 1 luot DUY NHAT nhung neo lech so voi loSafe 1 khoang bang duong
        // kinh thep S2 (Rebar_21 mat Nap), de S5 khong rai trung dung vi tri L cua
        // Rebar_21.
        public static void CreateChamferCornerBars(
            Document d, RebarBarType bt, FamilyInstance inst, Solid solid,
            XYZ Lv, XYZ Wv, XYZ Zv,
            Func<double, double, double, XYZ> L2G,
            List<double> wOff, List<double> zOff,
            double chamferFt, double coverFt,
            double lMinRaw, double lMaxRaw, double lSpacingFt,
            double extendMm, double lOffsetMm,
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

            // towardCenter = huong (doc Wv) tu goc DO ve phia TIM ham, dung cho chan noi
            // tiep tai dau NAP (Trai -> ve phia w3, Phai -> ve phia w0 - NGUOC voi phia
            // tuong cua chinh goc do). aIsWallSide = true neu diem "a" (theo aWZ) la diem
            // sat TUONG (z = z2 - chamferFt); false neu diem "a" la diem sat NAP
            // (z = z2) - xem so do trong ham nay.
            var corners = new (string name, double[] aWZ, double[] bWZ, XYZ into, XYZ towardCenter, bool aIsWallSide)[]
            {
                ("Goc vat trai (Tuong trai - Nap)", new[]{ w1,             z2 - chamferFt }, new[]{ w1 + chamferFt, z2 }, intoConcreteTrai, Wv, true),
                ("Goc vat phai (Tuong phai - Nap)", new[]{ w2 - chamferFt, z2 },             new[]{ w2,             z2 - chamferFt }, intoConcretePhai, -Wv, false),
            };

            double extendFt = MmToFt(extendMm);

            double loSafe = lMinRaw + coverFt;
            double hiSafe = lMaxRaw - coverFt;
            double lLen = hiSafe - loSafe;
            if (lLen < MmToFt(20))
            {
                report.Add($"{hostId}: chieu dai L qua ngan, bo qua thep cheo goc vat.");
                return;
            }

            // Rai dung THEO DUNG khoang cach thiet ke lSpacingFt tinh tu loSafe + lOffsetFt -
            // KHONG chia deu lai lLen (khoang cach phai dung bang gia tri dau vao). Phan du
            // con lai o dau xa (hiSafe) neu khong vua het 1 buoc thi BO TRONG.
            double lOffsetFt = MmToFt(lOffsetMm);
            var lPositions = new List<double>();
            for (double p = loSafe + lOffsetFt; p <= hiSafe; p += lSpacingFt)
                lPositions.Add(p);

            foreach (var c in corners)
            {
                int made = 0;
                foreach (double lPos in lPositions)
                {

                    // Tính điểm A, B trên mặt vát (đã lùi vào bê tông).
                    XYZ a = L2G(lPos, c.aWZ[0], c.aWZ[1]) + c.into * coverFt;
                    XYZ b = L2G(lPos, c.bWZ[0], c.bWZ[1]) + c.into * coverFt;

                    if (a.DistanceTo(b) < MmToFt(10)) continue;

                    // Đoạn chéo B: kéo dài a/b dọc theo đúng phương chéo cho tới khi chạm
                    // mặt Tường (1 đầu) và Nắp (đầu kia) - dùng ĐÚNG cover CỦA CHÍNH
                    // Rebar_21 (RebarCommon.DefaultCoverMm, xem RebarOuterShapeLogic.cs)
                    // thay vì coverFt riêng của S5, để điểm chạm nằm ĐÚNG mặt phẳng mà
                    // thanh Rebar_21 thật sự nằm - nhờ đó 2 chân "vươn" nối tiếp sau đó
                    // chạy TRÙNG (không lệch vài chục mm) với Rebar_21.
                    double rebar21CoverFt = MmToFt(RebarCommon.DefaultCoverMm);
                    XYZ dir = (b - a).Normalize();
                    XYZ a_ext = a;
                    XYZ b_ext = b;
                    if (c.name.Contains("trai"))
                    {
                        double tA = ((w0 + rebar21CoverFt) - a.DotProduct(Wv)) / dir.DotProduct(Wv);
                        a_ext = a + dir * tA;
                        double tB = ((z3 - rebar21CoverFt) - b.DotProduct(Zv)) / dir.DotProduct(Zv);
                        b_ext = b + dir * tB;
                    }
                    else
                    {
                        double tA = ((z3 - rebar21CoverFt) - a.DotProduct(Zv)) / dir.DotProduct(Zv);
                        a_ext = a + dir * tA;
                        double tB = ((w3 - rebar21CoverFt) - b.DotProduct(Wv)) / dir.DotProduct(Wv);
                        b_ext = b + dir * tB;
                    }

                    if (a_ext.DistanceTo(b_ext) < MmToFt(20)) continue;

                    // Xac dinh diem nao sat TUONG (nhan chan "vuon" chay DOC theo tuong,
                    // -Zv, xuong long ham) va diem nao sat NAP (nhan chan "vuon" chay DOC
                    // theo nap, ve tim ham) - CHI THEM 2 chan noi tiep nay, doan cheo o
                    // giua khong doi.
                    XYZ wallPt = c.aIsWallSide ? a_ext : b_ext;
                    XYZ napPt = c.aIsWallSide ? b_ext : a_ext;

                    XYZ wallLegEnd = wallPt - Zv * extendFt;
                    XYZ napLegEnd = napPt + c.towardCenter * extendFt;

                    var curves = new List<Curve>();
                    if (extendFt > MmToFt(1)) curves.Add(Line.CreateBound(wallLegEnd, wallPt));
                    curves.Add(Line.CreateBound(wallPt, napPt));
                    if (extendFt > MmToFt(1)) curves.Add(Line.CreateBound(napPt, napLegEnd));

                    var rebar = RebarCommon.CreateFromCurvesNoHooks(d, RebarStyle.Standard, bt, inst, Lv, curves);

                    if (rebar == null) continue;
                    rebar.GetShapeDrivenAccessor().SetLayoutAsSingle();
                    made++;
                }
                report.Add($"{hostId}: {c.name} - da tao {made} thanh (vuon {extendMm:F0}mm moi dau).");
                totalCount += made;
            }
        }
    }
}
