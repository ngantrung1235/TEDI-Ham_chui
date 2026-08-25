using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.UI;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Nut "Tao thep doc + dai C": lam lai toan bo viec cua RebarLongitudinalCommand
    // (thep doc chay theo Lv, tung thanh rieng bam sat bien solid, ca 4 mat x 2 lop
    // Ngoai/Trong), sau do voi MOI HANG (moi crossPos) TAO THEM 1 dai chu C noi thanh
    // lop Ngoai voi thanh lop Trong TAI CHINH crossPos DO (khong noi 2 thanh canh nhau
    // trong cung 1 lop), rai doc theo Lv voi khoang cach RebarStirrupCCommon.DefaultCTieSpacingMm.
    //
    // Dai C hinh chu "C": than dai chay doc truc do sau (tu OuterPos toi InnerPos),
    // 2 dau bo mop cung 1 huong ngang (cross) - dung 3 doan thang (hook - than - hook)
    // vi ban Revit API dang dung KHONG con enum RebarHookOrientation nen khong the
    // dung tham so hook rieng cho CreateFromCurves nhu ban cu (xem ghi chu tuong tu
    // trong RebarOuterShapeCommand.cs).
    [Transaction(TransactionMode.Manual)]
    public class RebarStirrupCCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIDocument uidoc = commandData.Application.ActiveUIDocument;
            Document doc = uidoc.Document;

            try
            {
                var selectedIds = uidoc.Selection.GetElementIds();
                if (selectedIds.Count == 0)
                {
                    message = "Vui lòng chọn ít nhất 1 cấu kiện trước khi chạy tool.";
                    return Result.Failed;
                }

                double coverFt = RebarCommon.MmToFt(RebarCommon.DefaultCoverMm);
                double spaceFt = RebarCommon.MmToFt(RebarStirrupCCommon.DefaultLongSpaceMm);
                double tieSpaceFt = RebarCommon.MmToFt(RebarStirrupCCommon.DefaultCTieSpacingMm);

                var report = new List<string>();
                var prepared = RebarCommon.PickAndPrepareHosts(uidoc, doc, selectedIds, coverFt, report);
                if (prepared.Count == 0)
                {
                    message = "Không có cấu kiện hợp lệ nào để tạo thép sau bước pick.";
                    return Result.Failed;
                }

                int totalLong = 0, totalTie = 0;
                using (Transaction t = new Transaction(doc, "Tạo thép dọc + đai C"))
                {
                    t.Start();

                    var barType = RebarCommon.GetOrCreateBarType(doc, "D20", RebarCommon.DefaultDiamMm, report);
                    var tieBarType = RebarStirrupCCommon.GetOrCreateTightBendTieType(
                        doc, RebarCommon.GetOrCreateBarType(doc, "D8", RebarStirrupCCommon.DefaultCTieDiamMm, report),
                        RebarCommon.DefaultDiamMm, RebarStirrupCCommon.DefaultCTieDiamMm, report);

                    foreach (var h in prepared)
                    {
                        int instCount = 0, tieCount = 0;
                        foreach (var fd in h.FacesDef)
                        {
                            double crossLen = fd.CrossMax - fd.CrossMin;
                            int nRows = (int)Math.Ceiling(crossLen / spaceFt) + 1;
                            if (nRows < 2) nRows = 2;
                            double rowSpacing = crossLen / (nRows - 1);

                            // Sau khi loc con i%2==0, khoang cach thuc te giua 2 dai C ke nhau la
                            // 2*rowSpacing. TCVN 11823 Muc 10.6.3 gioi han khoang cach toi da giua
                            // cac moc giu cu doc chu vi dai la 610mm - canh bao neu vuot.
                            double effectiveCrossSpacingMm = RebarCommon.FtToMm(rowSpacing * 2.0);
                            if (effectiveCrossSpacingMm > 610.0)
                            {
                                report.Add($"{h.Id} mặt {fd.Name}: CẢNH BÁO - khoảng cách đai C theo phương ngang sau khi lọc i%2==0 là {effectiveCrossSpacingMm:F0}mm, vượt quá 610mm (TCVN 11823 Mục 10.6.3 - khoảng cách tối đa giữa các móc giữ cữ dọc theo chu vi cốt đai).");
                            }

                            for (int i = 0; i < nRows; i++)
                            {
                                double crossPos = fd.CrossMin + i * rowSpacing;

                                XYZ outerProbeA = RebarStirrupCCommon.Pt(h, fd, h.LMinRaw, crossPos, fd.OuterPos);
                                XYZ outerProbeB = RebarStirrupCCommon.Pt(h, fd, h.LMaxRaw, crossPos, fd.OuterPos);
                                var outerRange = RebarCommon.ProbeSolidLRange(h.Solid, outerProbeA, outerProbeB, h.Lv);

                                XYZ innerProbeA = RebarStirrupCCommon.Pt(h, fd, h.LMinRaw, crossPos, fd.InnerPos);
                                XYZ innerProbeB = RebarStirrupCCommon.Pt(h, fd, h.LMaxRaw, crossPos, fd.InnerPos);
                                var innerRange = RebarCommon.ProbeSolidLRange(h.Solid, innerProbeA, innerProbeB, h.Lv);

                                if (outerRange == null || innerRange == null) continue;

                                double oLo = outerRange.Value.lo + coverFt, oHi = outerRange.Value.hi - coverFt;
                                double iLo = innerRange.Value.lo + coverFt, iHi = innerRange.Value.hi - coverFt;
                                if (oHi - oLo < RebarCommon.MmToFt(20) || iHi - iLo < RebarCommon.MmToFt(20)) continue;

                                // --- Thep doc lop Ngoai va lop Trong tai hang nay ---
                                XYZ oP1 = RebarStirrupCCommon.Pt(h, fd, oLo, crossPos, fd.OuterPos);
                                XYZ oP2 = RebarStirrupCCommon.Pt(h, fd, oHi, crossPos, fd.OuterPos);
                                XYZ iP1 = RebarStirrupCCommon.Pt(h, fd, iLo, crossPos, fd.InnerPos);
                                XYZ iP2 = RebarStirrupCCommon.Pt(h, fd, iHi, crossPos, fd.InnerPos);

                                XYZ normalOuter = RebarCommon.SafeNormalFor(oP1, oP2, h.Zv, h.Wv);
                                RebarCommon.CreateSingleBar(doc, barType, h.Inst, oP1, oP2, normalOuter);

                                XYZ normalInner = RebarCommon.SafeNormalFor(iP1, iP2, h.Zv, h.Wv);
                                RebarCommon.CreateSingleBar(doc, barType, h.Inst, iP1, iP2, normalInner);
                                instCount += 2;

                                // --- Dai C noi lop Ngoai - lop Trong tai chinh hang nay, rai doc Lv ---
                                // (1) Bo qua dung 2 hang GOC TUYET DOI (i=0 va i=nRows-1, chinh xac tai
                                // CrossMin/CrossMax) vi day la vi tri GOC VUONG giao voi mat ben canh -
                                // thep doc goc da duoc lien ket bang thep dai vuong/thep cheo goc rieng,
                                // dat them dai C ngay tai do se bi trung/chong cheo cau kien.
                                if (i == 0 || i == nRows - 1) continue;

                                // (2) Trong cac hang con lai, chi giu dai C tai hang CHAN (i%2==0) de
                                // giam mat do dai du thua - moi thanh thep doc khong nhat thiet phai co
                                // rieng 1 dai C, mien khoang cach giua 2 diem giu cu ke nhau (2*rowSpacing,
                                // da kiem tra + canh bao o tren) khong vuot 610mm theo TCVN 11823 Muc 10.6.3.
                                if (i % 2 != 0) continue;

                                double tieLo = Math.Max(oLo, iLo);
                                double tieHi = Math.Min(oHi, iHi);
                                if (tieHi - tieLo < RebarCommon.MmToFt(20)) continue;

                                int made = RebarStirrupCCommon.CreateOuterInnerTies(
                                    doc, h, fd, crossPos, tieLo, tieHi, tieBarType, RebarCommon.DefaultDiamMm, tieSpaceFt, report);
                                tieCount += made;
                            }
                        }
                        report.Add($"{h.Id}: đã tạo {instCount} thanh thép dọc (4 mặt x 2 lớp) + {tieCount} đai C.");
                        totalLong += instCount;
                        totalTie += tieCount;
                    }

                    t.Commit();
                }

                TaskDialog.Show("Thành công",
                    $"Đã tạo tổng cộng {totalLong} thanh thép dọc và {totalTie} đai C.\n\nChi tiết:\n" + string.Join("\n", report));
                return Result.Succeeded;
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                return Result.Cancelled;
            }
            catch (Exception ex)
            {
                message = ex.Message + "\n" + ex.StackTrace;
                return Result.Failed;
            }
        }
    }

    // ============================================================================
    // Helper rieng cho dai chu C - noi thanh thep doc lop Ngoai voi lop Trong tren
    // cung 1 mat (Day/Nap/Trai/Phai), tai CHINH crossPos hien tai (khong phai 2 hang
    // canh nhau). Dai nam trong mat phang (cross, do sau) tai 1 vi tri L co dinh.
    //
    // MAT DO THEO PHUONG NGANG (chieu rong mat, bien i o Execute): chi dat dai C tai
    // cac hang CHAN (i%2==0), bo qua 2 hang goc tuyet doi (i=0, i=nRows-1) da co dai
    // rieng - xem giai thich + canh bao TCVN 11823 Muc 10.6.3 (610mm) trong Execute().
    //
    // QUAN TRONG (fix rai lech khi host bi xien goc >3 do):
    // Truoc day dai C duoc tao 1 LAN duy nhat bang Rebar.CreateFromCurves roi rai
    // bang SetLayoutAsNumberWithSpacing(..., normal). Ham nay CHI rai dung huong theo
    // vector "normal" truyen vao khi mat phang chua duong cong That SU vuong goc voi
    // no; con voi cach tinh Pt() cua ta, huong di chuyen thuc te khi doi "l" la
    // (Wv.Y, -Wv.X)/detA - chi trung voi Lv khi Wv vuong goc TUYET DOI voi Lv. Voi
    // host bi xien (Wv khong vuong goc that su voi Lv, vi du canh bao ">3 do" trong
    // RebarCommon), 2 huong nay lech nhau that -> dai bi rai lech dan khoi thep doc.
    //
    // Cach sua: BO HAN co che rai bang SetLayoutAsNumberWithSpacing. Thay vao do, voi
    // moi vi tri "l" thuc te (tinh truoc, cach deu nhau ~tieSpacingFt trong doan
    // [lLo, lHi]) ta goi lai dung ham Pt(h, fd, l, cross, depth) - CHINH XAC cong thuc
    // ma thep doc (RebarStirrupCCommand.Execute) da dung de dung diem oP1/oP2/iP1/iP2
    // - roi tao TUNG dai C RIENG LE bang Rebar.CreateFromCurves tai vi tri do. Vi moi
    // dai deu tu tinh diem bang Pt() (chinh cong thuc L2G that, khong suy dien qua
    // vector normal co dinh), dai C se LUON bam dung theo thep doc du Lv/Wv co xien
    // goc bao nhieu di nua. Tham so "normal" truyen cho CreateFromCurves chi dung de
    // Revit xac dinh mat phang cua bien dang chu C (h.Lv la dung vi 3 diem cua 1 dai
    // don le - pOuterHook, pOuter, pInner, pInnerHook - deu nam co dinh tai 1 "l", nen
    // mat phang chu C luon vuong goc that voi Lv tai diem do, khong bi anh huong boi
    // do xien cua Wv).
    // ============================================================================
    public static class RebarStirrupCCommon
    {
        // ============================================================================
        // TODO: các giá trị này sẽ được người dùng NHẬP TỪ GIAO DIỆN (form nhập liệu) ở
        // phiên bản sau, thay vì hard-code như hiện tại - đây là nguồn duy nhất cho cả
        // Execute() lẫn CreateOuterInnerTies() bên dưới, chỉ cần sửa các dòng này (hoặc
        // đổi thành tham số truyền vào) khi có form nhập liệu, không cần sửa gì khác.
        // Trước mắt: spacing thép dọc mặc định 150mm, đường kính đai C mặc định 8mm
        // (giữ như cũ), khoảng cách đai C 600mm. Spacing thép dọc dùng riêng cho nút
        // "Tạo thép dọc + đai C" này, KHÔNG dùng chung với RebarLongitudinalCommand hay
        // các nút thép khác.
        // ============================================================================
        public const double DefaultLongSpaceMm = 150.0;
        public const double DefaultCTieDiamMm = 8.0;
        public const double DefaultCTieSpacingMm = 600.0;

        // Quy doi (l, cross, depth) ve toa do global theo dung quy uoc cua RebarCommon:
        // mat San (IsSlab=true) dung L2G(l, w=cross, z=depth); mat Tuong (IsSlab=false)
        // dung L2G(l, w=depth, z=cross).
        public static XYZ Pt(PreparedHost h, FaceDef fd, double l, double crossVal, double depthVal)
        {
            return fd.IsSlab ? h.L2G(l, crossVal, depthVal) : h.L2G(l, depthVal, crossVal);
        }

        // Tao (hoac tim lai) 1 RebarBarType nhan ban tu tieBarType nhung bop nho
        // StirrupTieBendDiameter de goc bo cua dai C OM SAT vao than thep doc (barDiamMm)
        // thay vi dung ban kinh bo mac dinh cua Type (thuong lon hon nhieu so voi D20) -
        // giong het cach lam trong Dai_C.cs/SV_VeThepGia.txt goc.
        public static RebarBarType GetOrCreateTightBendTieType(
            Document doc, RebarBarType tieBarType, double barDiamMm, double tieDiamMm, List<string> report)
        {
            double tightHookLenMm = barDiamMm + tieDiamMm + 2.0; // vua du om quanh thep doc + thep dai
            double maxBendDiameterMm = tightHookLenMm - 5.0; // chua lai 5mm doan thang an toan

            string newTypeName = $"{tieBarType.Name}_C_Tie_Tight";
            var existing = new FilteredElementCollector(doc)
                .OfClass(typeof(RebarBarType))
                .Cast<RebarBarType>()
                .FirstOrDefault(t => t.Name == newTypeName);
            if (existing != null) return existing;

            try
            {
                var duped = tieBarType.Duplicate(newTypeName) as RebarBarType;
                if (duped != null)
                {
                    duped.StirrupTieBendDiameter = RebarCommon.MmToFt(maxBendDiameterMm);
                    return duped;
                }
            }
            catch (Exception ex)
            {
                report.Add($"Không tạo được RebarBarType bo góc khít '{newTypeName}': {ex.Message}. Dùng lại Type '{tieBarType.Name}' mặc định.");
            }
            return tieBarType;
        }

        // Tao NHIEU dai C rieng le, moi dai tai 1 vi tri "l" thuc te trong doan
        // [lLo, lHi], cach deu ~tieSpacingFt (so luong va khoang cach thuc duoc chia
        // deu giong SetLayoutAsNumberWithSpacing cu, nhung moi vi tri deu goi Pt()
        // rieng nen KHONG con phu thuoc vao do chinh xac vuong goc cua h.Lv/h.Wv).
        //
        // Hinh dang moi dai (5 doan thang, giong mau "41A": A-B-C-D-E) thay cho ban
        // 3 doan truoc day. Ly do doi: ban 3 doan (hook - than - hook) dung 1 doan
        // THANG DUY NHAT lam moc, chay xuyen qua dung vi tri "cross" cua tam thanh
        // thep doc -> ve mat hinh hoc doan do CAM VAO giua than thanh thep doc that
        // (dai bi "dinh" vao thanh) thay vi om vong quanh no. Ban 5 doan nay om that
        // quanh tung thanh thep doc theo dung kieu cua SV_VeThepGia.txt (ham
        // VeThepGia, doan ve dai C 5-diem p1..p6 dung 2 truc "cross"/"up"):
        //   - C (than dai, giua) : chay doc truc SAU (OuterPos -> InnerPos), lech ra
        //     mep NGOAI (tiep tuyen) theo truc NGANG (cross) 1 khoang rCenterFt.
        //   - B/D (canh om)      : chay doc truc NGANG (cross), TU mep tiep tuyen o
        //     1 ben SANG HET mep tiep tuyen ben doi dien cua thanh thep doc - tuc la
        //     om vong QUA CA 2 BEN thanh, khong con doan nao chay xuyen qua tam.
        //   - A/E (moc gap vao)  : tu mep tiep tuyen doi dien, be tiep VE PHIA thanh
        //     thep doc (doc truc SAU) 1 doan dung bang 10 lan duong kinh thep dai
        //     (10*DefaultCTieDiamMm) de mocneo chac, KHONG con vuot qua tam thanh.
        // rCenterFt dung dung StirrupTieBendDiameter cua tieBarType (ban kinh bo goc
        // THAT Revit se ve) + ban kinh thep dai, thay vi ban kinh thep doc truoc day,
        // de diem dat va cung bo goc luon khop nhau (khong con lech gay dai chong
        // chan thanh thep tai goc bo).
        public static int CreateOuterInnerTies(
            Document doc, PreparedHost h, FaceDef fd, double crossPos,
            double lLo, double lHi, RebarBarType tieBarType, double barDiamMm, double tieSpacingFt,
            List<string> report)
        {
            try
            {
                double tieDiamFt = RebarCommon.MmToFt(DefaultCTieDiamMm);
                double tieRadiusFt = tieDiamFt / 2.0;

                double rInnerFt = tieBarType.StirrupTieBendDiameter / 2.0;
                double rCenterFt = rInnerFt + tieRadiusFt;
                double marginFt = RebarCommon.MmToFt(5.0);
                double halfMarginFt = marginFt / 2.0;

                // Doan B/D om vong het 2 ben thanh thep doc -> lech het 1 khoang
                // (rCenterFt + halfMarginFt) ve moi phia so voi crossPos.
                double crossHalfSpanFt = rCenterFt + halfMarginFt;
                double crossNear = crossPos + crossHalfSpanFt;   // phia dai bat dau tu than C
                double crossFar = crossPos - crossHalfSpanFt;    // phia doi dien, noi be moc A/E

                // Moc A/E: dung 10 lan duong kinh thep dai theo yeu cau.
                double hookFootFt = RebarCommon.MmToFt(10.0 * DefaultCTieDiamMm);

                // QUAN TRONG: FaceDef.OuterPos/InnerPos KHONG co dinh chieu - voi mat "Day"/
                // "Trai" thi OuterPos < InnerPos, nhung voi mat "Nap"/"Phai" (xem
                // PickAndPrepareHosts trong RebarCommon.cs) thi OuterPos > InnerPos (nguoc
                // lai), vi 2 mat nay lay OuterPos tu dau ben KIA cua mang zOff/wOff. Cong
                // thuc truoc day gia dinh co dinh OuterPos < InnerPos (dung "-rCenterFt" cho
                // Outer va "+rCenterFt" cho Inner de "di ra xa nhau") -> voi Nap/Phai thi
                // "-rCenterFt" lai chay VAO TRONG (ve phia Inner) thay vi ra ngoai, khien
                // than dai C dam vao thanh thay vi tiep tuyen ben ngoai, va moc A/E cung be
                // sai huong (khong quap vao trong) - dung "depthSign" de tu dong doi chieu
                // theo dung tuong quan Outer/Inner THAT cua tung mat.
                double depthSign = fd.OuterPos >= fd.InnerPos ? 1.0 : -1.0;

                double spanFt = lHi - lLo;
                int count = (int)(spanFt / tieSpacingFt) + 1;
                if (count < 1) count = 1;
                double actualSpacingFt = count > 1 ? spanFt / (count - 1) : 0.0;

                var terminations = new BarTerminationsData(doc);
                int made = 0;

                for (int i = 0; i < count; i++)
                {
                    double l = count > 1 ? lLo + i * actualSpacingFt : lLo;

                    // Kiem tra nhanh: 2 tam thep (Ngoai/Trong) tai vi tri l nay co du xa
                    // nhau khong (tranh dai C bi op sat/trung nhau khi bien dang qua mong).
                    XYZ pOuterCenter = Pt(h, fd, l, crossPos, fd.OuterPos);
                    XYZ pInnerCenter = Pt(h, fd, l, crossPos, fd.InnerPos);
                    if (pOuterCenter.DistanceTo(pInnerCenter) < RebarCommon.MmToFt(20)) continue;

                    // C - than dai: tiep tuyen mep ngoai 2 thanh, di CHUYEN RA XA nhau theo
                    // dung chieu that (depthSign) cua tung mat, co dinh tai crossNear.
                    double outerFarDepth = fd.OuterPos + depthSign * rCenterFt;
                    double innerFarDepth = fd.InnerPos - depthSign * rCenterFt;
                    XYZ pSpineOuter = Pt(h, fd, l, crossNear, outerFarDepth);
                    XYZ pSpineInner = Pt(h, fd, l, crossNear, innerFarDepth);

                    // B/D - canh om: cung do sau voi C, quet tu crossNear sang crossFar
                    // (om qua het chieu ngang thanh thep doc, khong dung lai giua chung).
                    XYZ pWrapOuter = Pt(h, fd, l, crossFar, outerFarDepth);
                    XYZ pWrapInner = Pt(h, fd, l, crossFar, innerFarDepth);

                    // A/E - moc gap: tu crossFar, be NGUOC LAI (ve phia thanh thep doc,
                    // nguoc voi depthSign) 1 doan hookFootFt (KHONG vuot qua tam thanh).
                    XYZ pHookOuter = Pt(h, fd, l, crossFar, outerFarDepth - depthSign * hookFootFt);
                    XYZ pHookInner = Pt(h, fd, l, crossFar, innerFarDepth + depthSign * hookFootFt);

                    var tieCurves = new List<Curve>
                    {
                        Line.CreateBound(pHookOuter, pWrapOuter),
                        Line.CreateBound(pWrapOuter, pSpineOuter),
                        Line.CreateBound(pSpineOuter, pSpineInner),
                        Line.CreateBound(pSpineInner, pWrapInner),
                        Line.CreateBound(pWrapInner, pHookInner),
                    };

                    try
                    {
                        // normal = h.Lv: dung vi 4 diem cua dai don le nay deu co dinh tai
                        // 1 "l", nen mat phang bien dang thuc su vuong goc voi Lv tai diem
                        // do - khong con anh huong boi do xien cua Wv nhu khi rai bang
                        // SetLayoutAsNumberWithSpacing truoc day.
                        var tieRebar = Rebar.CreateFromCurves(
                            doc, RebarStyle.StirrupTie, tieBarType, h.Inst, h.Lv,
                            tieCurves, terminations,
                            useExistingShapeIfPossible: false, createNewShape: true);

                        if (tieRebar != null) made++;
                    }
                    catch (Exception exInner)
                    {
                        report.Add($"{h.Id} mặt {fd.Name} tại cross={RebarCommon.FtToMm(crossPos):F0}mm, l={RebarCommon.FtToMm(l):F0}mm: lỗi tạo đai C: {exInner.Message}");
                    }
                }

                return made;
            }
            catch (Exception ex)
            {
                report.Add($"{h.Id} mặt {fd.Name} tại cross={RebarCommon.FtToMm(crossPos):F0}mm: lỗi tạo đai C: {ex.Message}");
                return 0;
            }
        }
    }
}