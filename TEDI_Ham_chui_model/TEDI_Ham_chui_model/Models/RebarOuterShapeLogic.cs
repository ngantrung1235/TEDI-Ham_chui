using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;

namespace TEDI_Ham_chui_model.Models
{
    // Bo 2 cua LOP NGOAI tren 2 mat Day/Nap, dung RebarShape "Rebar_21" dang chu Z
    // de noi lien mach thep ngoai cua ban voi thep ngoai cua tuong qua goc. Xem
    // chi tiet trong ShapeDrivenOuterRebar ben duoi.
    //
    // KHONG con la nut rieng (IExternalCommand) - chi con RunOnPrepared() de
    // RebarAllInOneCommand goi voi 1 List<PreparedHost> da pick san (xem
    // RebarAllInOneCommand.cs, nut "Vẽ tất cả thép" duy nhat).
    public static class RebarOuterShapeLogic
    {
        // diamS2Mm/spaceS2Mm = thanh Rebar_21 tai mat Nap ("S2" theo ban ve), diamF2Mm/
        // spaceF2Mm = tai mat Day ("F2"). Moi mat co RebarBarType RIENG (ten dat theo
        // duong kinh thuc, vd "D25") de tranh nham lan neu 2 mat dung duong kinh khac
        // nhau. shapeUTipMm/shapeCEndCompensationMm = 2 hang so hieu chinh hinh hoc cua
        // RebarShape "Rebar_21" (xem ghi chu trong ShapeDrivenOuterRebar ben duoi) -
        // nguoi dung tu do dac/nhap lai neu doi B/duong kinh thanh. Nguoi goi
        // (RebarAllInOneViewModel) LUON truyen du cac gia tri nay.
        public static string RunOnPrepared(
            Document doc, List<PreparedHost> prepared, List<string> report,
            double diamS2Mm, double spaceS2Mm,
            double diamF2Mm, double spaceF2Mm,
            double shapeUTipMm, double shapeCEndCompensationMm)
        {
            double coverFt = RebarCommon.MmToFt(RebarCommon.DefaultCoverMm);

            int totalCount = 0;
            using (Transaction t = new Transaction(doc, "Tạo thép Rebar_21 (Nắp/Đáy)"))
            {
                t.Start();

                RebarShape rebarShape0;
                try
                {
                    rebarShape0 = ShapeDrivenOuterRebar.FindOrLoadRebarShape(doc);
                    report.Add("Đã load RebarShape 'Rebar_21'.");
                }
                catch (Exception ex)
                {
                    t.RollBack();
                    throw new InvalidOperationException($"Lỗi load RebarShape 'Rebar_21': {ex.Message}", ex);
                }

                var barTypeS2 = RebarCommon.GetOrCreateBarType(doc, $"S2-D{diamS2Mm:F0}-{spaceS2Mm:F0}", diamS2Mm, report);
                var barTypeF2 = RebarCommon.GetOrCreateBarType(doc, $"F2-D{diamF2Mm:F0}-{spaceF2Mm:F0}", diamF2Mm, report);
                double spaceFtS2 = RebarCommon.MmToFt(spaceS2Mm);
                double spaceFtF2 = RebarCommon.MmToFt(spaceF2Mm);

                    foreach (var h in prepared)
                    {
                        int instCount = 0;
                        foreach (var fd in h.FacesDef.Where(f => f.IsSlab)) // chi Day/Nap
                        {
                            bool isNap = (fd.Name == "Nap");
                            bool bLegAtW0Side = isNap;
                            double bLegDefaultMm = 3500;
                            double heightN_ft = (h.Inst.LookupParameter("Height_N") ?? h.Inst.Symbol?.LookupParameter("Height_N"))?.AsDouble()
                                                 ?? (h.ZOff[3] - h.ZOff[0]);

                            var barType = isNap ? barTypeS2 : barTypeF2;
                            double spaceFt = isNap ? spaceFtS2 : spaceFtF2;
                            double diamMmFace = isNap ? diamS2Mm : diamF2Mm;

                            // Mat ngoai cua lop doi dien (Nap<->Day), dung de giu Wv GIONG HET
                            // nhau giua 2 lop (lay giao cua be tong do duoc o CA HAI cao do Z).
                            double otherOuterZ = isNap
                                ? h.FacesDef.First(f => f.Name == "Day").OuterPos
                                : h.FacesDef.First(f => f.Name == "Nap").OuterPos;

                            // Lop Day (duoi) lui vao sau hon lop Nap (tren) theo Lv: lop Nap
                            // dung dung coverFt (50mm), lop Day dung them (duong kinh thep cua
                            // chinh no + 10mm) de 2 lop dat xen ke nhau.
                            double lStartExtraFt = isNap ? 0.0 : RebarCommon.MmToFt(diamMmFace + 10.0);

                            int made = ShapeDrivenOuterRebar.CreateShapeDrivenBars(
                                doc, rebarShape0, barType, h.Inst, h.Solid,
                                h.L2G, h.Wv, h.Zv, h.WOff, fd.OuterPos, otherOuterZ, isNap, bLegAtW0Side,
                                coverFt, lStartExtraFt, h.LMinRaw, h.LMaxRaw, spaceFt, heightN_ft, bLegDefaultMm,
                                shapeUTipMm, shapeCEndCompensationMm, report, h.Id);
                            instCount += made;
                        }
                        report.Add($"{h.Id}: đã tạo {instCount} thanh Rebar_21 (Nắp+Đáy).");
                        totalCount += instCount;
                    }

                    t.Commit();
                }

            return $"Đã tạo tổng cộng {totalCount} thanh Rebar_21.\n\nChi tiết:\n" + string.Join("\n", report);
        }
    }

    // ============================================================================
    // Thay the cho BO 2 (thep chay phuong Wv - song song chieu rong cong) cua
    // LOP NGOAI tren 2 mat Day/Nap: thay vi ve thanh thep thang don gian, dung
    // RebarShape "Rebar_21" (family "Rebar_21.rfa", 3 tham so hinh A/B/C, dang
    // chu Z: 1 chan dai B neo sau vao 1 tuong, doan thang C chay ngang, 1 chan
    // ngan A neo vao tuong con lai) de noi lien mach thep ngoai cua ban voi
    // thep ngoai cua tuong qua goc.
    //
    // *** CAC HANG SO HIEU CHINH HINH HOC (CALIBRATION) ***
    // shapeUTipMm la toa do LOCAL (trong mat phang rieng cua RebarShape "Rebar_21", he
    // truc (xVec,yVec) tu chon khi goi CreateFromRebarShape) cua diem MUI CHAN B (dau
    // neo sau nhat, xa doan C nhat). Do dac THUC NGHIEM bang cach tao thu 1 thanh trong
    // Revit that (B=3500mm), doi chieu toa do voi 2 thanh mau nguoi dung da dat tay san
    // trong model du an (elementId 415621 - mau mat Nap, 416154 - mau mat Day) - KHOP
    // TUYET DOI (sai lech 0mm) o ca 2 cach dat, VOI B=3500mm + thanh D20. shapeCEndCompensationMm
    // la do hut chieu dai doan C (bend deduction) tai dau chan A - do dac THUC NGHIEM
    // tuong tu, voi C~5892mm + D20 thi do hut ~27.5mm. Neu doi B/duong kinh thanh/shape
    // khac, 2 gia tri nay co the KHONG con dung nua - vi vay giao cho nguoi dung tu nhap
    // lai qua UI (xem RebarAllInOneViewModel) thay vi hard-code.
    // ============================================================================
    public static class ShapeDrivenOuterRebar
    {
        private static double MmToFt(double mm) => UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters);
        private static double FtToMm(double ft) => UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Millimeters);

        private class RebarShapeLoadOptions : IFamilyLoadOptions
        {
            public bool OnFamilyFound(bool familyInUse, out bool overwriteParameterValues)
            {
                overwriteParameterValues = true;
                return true;
            }

            public bool OnSharedFamilyFound(Family sharedFamily, bool familyInUse, out FamilySource source, out bool overwriteParameterValues)
            {
                source = FamilySource.Family;
                overwriteParameterValues = true;
                return true;
            }
        }

        // Tim RebarShape ten "Rebar_21" trong document hien tai; neu chua co (vi
        // du chay tren 1 file du an khac chua tung load family nay), tu dong
        // LoadFamily tu duong dan .rfa mac dinh ben duoi.
        public static RebarShape FindOrLoadRebarShape(
            Document doc,
            string shapeName = "Rebar_21",
            string rfaPath = null)
        {
            if (string.IsNullOrEmpty(rfaPath))
            {
                string dllFolder = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                rfaPath = Path.Combine(dllFolder, "Rebar_21.rfa");
            }

            var existing = new FilteredElementCollector(doc)
                .OfClass(typeof(RebarShape))
                .Cast<RebarShape>()
                .FirstOrDefault(rs => rs.Name.Trim().Equals(shapeName.Trim(), StringComparison.OrdinalIgnoreCase));
            if (existing != null) return existing;

            if (!File.Exists(rfaPath))
                throw new InvalidOperationException(
                    $"Khong tim thay RebarShape '{shapeName}' trong model, va cung khong tim thay file " +
                    $"'{rfaPath}' de tu dong load. Hay load family 'Rebar_21.rfa' vao model truoc.");

            Family loadedFamily;
            doc.LoadFamily(rfaPath, new RebarShapeLoadOptions(), out loadedFamily);
            if (loadedFamily == null)
                throw new InvalidOperationException($"Load family tu '{rfaPath}' that bai.");

            foreach (ElementId typeId in loadedFamily.GetFamilySymbolIds())
                if (doc.GetElement(typeId) is RebarShape rs) return rs;

            // fallback: tim lai theo ten sau khi load (phong khi ten type ben trong khac ten family)
            var reloaded = new FilteredElementCollector(doc)
                .OfClass(typeof(RebarShape))
                .Cast<RebarShape>()
                .FirstOrDefault(rs => rs.Name.Trim().Equals(shapeName.Trim(), StringComparison.OrdinalIgnoreCase));
            if (reloaded == null)
                throw new InvalidOperationException($"Da load family '{rfaPath}' nhung khong tim thay RebarShape '{shapeName}' ben trong.");
            return reloaded;
        }

        public static int CreateShapeDrivenBars(
            Document d, RebarShape rebarShape, RebarBarType barType, FamilyInstance inst, Solid solid,
            Func<double, double, double, XYZ> L2G, XYZ Wv, XYZ Zv,
            List<double> wOff, double faceOuterZ, double otherFaceOuterZ, bool isNap, bool bLegAtW0Side,
            double coverFt, double lStartExtraFt, double lMinRaw, double lMaxRaw, double spaceFt,
            double heightN_ft, double bLegDefaultMm, double shapeUTipMm, double shapeCEndCompensationMm,
            List<string> report, ElementId hostId)
        {
            double diamMm = FtToMm(barType.BarModelDiameter);
            double heightN_mm = FtToMm(heightN_ft);

            // A = (Height_N - B) + 40*D
            double A_mm = (heightN_mm - bLegDefaultMm) + 40.0 * diamMm;
            double B_mm = bLegDefaultMm;

            double w0 = wOff[0], w3 = wOff[3];

            XYZ yVec = isNap ? Zv : -Zv;
            double tipZft = isNap ? (faceOuterZ - MmToFt(B_mm)) : (faceOuterZ + MmToFt(B_mm));

            double loSafe = lMinRaw + coverFt + lStartExtraFt;
            double hiSafe = lMaxRaw - coverFt;
            double lLen = hiSafe - loSafe;
            if (lLen < MmToFt(20))
            {
                report.Add($"{hostId}: chieu dai L qua ngan, bo qua thep {(isNap ? "Nap" : "Day")} (Rebar_21).");
                return 0;
            }
            // Rai dung THEO DUNG khoang cach thiet ke spaceFt (150mm) tinh tu loSafe - KHONG
            // chia deu lai lLen (khoang cach phai dung bang gia tri dau vao). Phan du con lai
            // o dau xa (hiSafe) neu khong vua het 1 buoc thi BO TRONG.
            var lRows = new List<double>();
            for (double p = loSafe; p <= hiSafe; p += spaceFt)
                lRows.Add(p);
            int nRows = lRows.Count;

            int made = 0;
            foreach (double lRow in lRows)
            {

                // Do be tong theo Wv o CA HAI cao do (mat ngoai cua lop nay va lop doi
                // dien), roi lay GIAO cua 2 khoang -> wLoSafe/wHiSafe luon nam trong be
                // tong that o ca 2 cao do, va KHONG con lech giua Nap/Day do vat/thu hep
                // tiet dien theo Z (ly do gay lech ngang truoc day).
                XYZ probeA = L2G(lRow, w0, faceOuterZ);
                XYZ probeB = L2G(lRow, w3, faceOuterZ);
                var wRangeSelf = RebarCommon.ProbeSolidLRange(solid, probeA, probeB, Wv);

                XYZ probeA2 = L2G(lRow, w0, otherFaceOuterZ);
                XYZ probeB2 = L2G(lRow, w3, otherFaceOuterZ);
                var wRangeOther = RebarCommon.ProbeSolidLRange(solid, probeA2, probeB2, Wv);

                if (wRangeSelf == null || wRangeOther == null)
                {
                    report.Add($"{hostId}: hang L={FtToMm(lRow):F0}mm khong do duoc be tong (Rebar_21) - bo qua.");
                    continue;
                }

                double wLoRaw = Math.Max(wRangeSelf.Value.lo, wRangeOther.Value.lo);
                double wHiRaw = Math.Min(wRangeSelf.Value.hi, wRangeOther.Value.hi);

                double wLoSafe = wLoRaw + coverFt;
                double wHiSafe = wHiRaw - coverFt;
                double C_ft = wHiSafe - wLoSafe;
                double C_mm = FtToMm(C_ft);
                if (C_mm < 100)
                {
                    report.Add($"{hostId}: hang L={FtToMm(lRow):F0}mm C qua ngan ({C_mm:F0}mm) - bo qua.");
                    continue;
                }

                double wB_pos = bLegAtW0Side ? wLoSafe : wHiSafe;
                double wA_pos = bLegAtW0Side ? wHiSafe : wLoSafe;

                XYZ ptB = L2G(lRow, wB_pos, faceOuterZ);
                XYZ ptA = L2G(lRow, wA_pos, faceOuterZ);
                XYZ xVec = new XYZ(ptB.X - ptA.X, ptB.Y - ptA.Y, 0).Normalize();

                XYZ qTip = L2G(lRow, wB_pos, tipZft);
                // Gốc toạ độ (origin) của family Rebar thực chất nằm ở mũi chân thép (V=0),
                // còn cạnh ngang C nằm ở toạ độ V = B. Do đó không cộng/trừ SHAPE_V_TIP_MM nữa!
                XYZ origin = qTip - MmToFt(shapeUTipMm) * xVec;

                Rebar rebar;
                try
                {
                    rebar = Rebar.CreateFromRebarShape(d, rebarShape, barType, inst, origin, xVec, yVec);
                }
                catch (Exception ex)
                {
                    report.Add($"{hostId}: loi tao Rebar_21 tai L={FtToMm(lRow):F0}mm: {ex.Message}");
                    continue;
                }
                if (rebar == null) continue;

                rebar.LookupParameter("A")?.Set(MmToFt(A_mm));
                rebar.LookupParameter("B")?.Set(MmToFt(B_mm));
                rebar.LookupParameter("C")?.Set(C_ft + MmToFt(shapeCEndCompensationMm));

                made++;
            }

            report.Add($"{hostId}: {(isNap ? "Nap" : "Day")} Ngoai (Rebar_21) - da tao {made}/{nRows} thanh. " +
                       $"A={A_mm:F0}mm B={B_mm:F0}mm (C thay doi theo tung hang theo be tong thuc te).");
            return made;
        }
    }
}
