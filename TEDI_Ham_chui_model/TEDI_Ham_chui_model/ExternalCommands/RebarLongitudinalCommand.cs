using System;
using System.Collections.Generic;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Nut "Tao thep doc": Bo 1 - thanh thep chay doc theo truc Lv, tung thanh
    // rieng bam sat bien that cua solid (chieu dai khac nhau o gan goc vat).
    // Tao cho ca 4 mat (Day/Nap/Trai/Phai) x 2 lop (Ngoai/Trong).
    [Transaction(TransactionMode.Manual)]
    public class RebarLongitudinalCommand : IExternalCommand
    {
        // TODO: se duoc nguoi dung nhap tu giao dien (form nhap lieu) o phien ban sau -
        // rieng cho nut "Tao thep doc" nay, khong dung chung voi cac nut thep khac.
        public const double DefaultSpaceMm = 150.0;
        public const double DefaultDiamMm = 20.0;

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

                // Dung RebarCommon.LongitudinalCoverMm (nguon DUY NHAT cho lop bao ve thep doc,
                // dung chung voi RebarStirrupCCommand) thay vi RebarCommon.DefaultCoverMm truc tiep,
                // de 2 nut tao thep doc (nut rieng nay + nut "thep doc + dai C") luon dong bo vi tri.
                double coverFt = RebarCommon.MmToFt(RebarCommon.LongitudinalCoverMm);
                // Cover CHUAN (khong cong them duong kinh Rebar 0) dung rieng cho rowLo/rowHi ben
                // duoi - khoang cach dau thanh thep toi dau cat cua host (dau dot) theo Lv, khong
                // lien quan gi den Rebar 0 (chi anh huong huong vuong goc mat).
                double lengthCoverFt = RebarCommon.MmToFt(RebarCommon.DefaultCoverMm);
                double spaceFt = RebarCommon.MmToFt(DefaultSpaceMm);

                var report = new List<string>();
                var prepared = RebarCommon.PickAndPrepareHosts(uidoc, doc, selectedIds, coverFt, report);
                if (prepared.Count == 0)
                {
                    message = "Không có cấu kiện hợp lệ nào để tạo thép sau bước pick.";
                    return Result.Failed;
                }

                int totalCount = 0;
                using (Transaction t = new Transaction(doc, "Tạo thép dọc"))
                {
                    t.Start();

                    var barType = RebarCommon.GetOrCreateBarType(doc, "D20", DefaultDiamMm, report);

                    foreach (var h in prepared)
                    {
                        int instCount = 0;
                        foreach (var fd in h.FacesDef)
                        {
                            foreach (var pos in new[] { fd.OuterPos, fd.InnerPos })
                            {
                                // Rai dung THEO DUNG khoang cach thiet ke spaceFt (150mm) tinh tu
                                // CrossMin - KHONG chia deu lai crossLen (khoang cach phai dung
                                // bang gia tri dau vao, khong tu dong co gian). Phan du con lai o
                                // dau xa (CrossMax) neu khong vua het 1 buoc thi BO TRONG.
                                var rowCrossPositions = new List<double>();
                                for (double p = fd.CrossMin; p <= fd.CrossMax; p += spaceFt)
                                    rowCrossPositions.Add(p);

                                foreach (double crossPos in rowCrossPositions)
                                {
                                    XYZ probeA = fd.IsSlab ? h.L2G(h.LMinRaw, crossPos, pos) : h.L2G(h.LMinRaw, pos, crossPos);
                                    XYZ probeB = fd.IsSlab ? h.L2G(h.LMaxRaw, crossPos, pos) : h.L2G(h.LMaxRaw, pos, crossPos);
                                    var range = RebarCommon.ProbeSolidLRange(h.Solid, probeA, probeB, h.Lv);
                                    if (range == null) continue;
                                    double rowLo = range.Value.lo + lengthCoverFt;
                                    double rowHi = range.Value.hi - lengthCoverFt;
                                    if (rowHi - rowLo < RebarCommon.MmToFt(20)) continue;

                                    XYZ b1 = fd.IsSlab ? h.L2G(rowLo, crossPos, pos) : h.L2G(rowLo, pos, crossPos);
                                    XYZ b2 = fd.IsSlab ? h.L2G(rowHi, crossPos, pos) : h.L2G(rowHi, pos, crossPos);

                                    // Normal tinh TRUC TIEP tu huong that cua thanh (b1->b2) - luon
                                    // vuong goc tuyet doi, khong phu thuoc Lv/Wv co vuong goc nhau hay khong.
                                    XYZ normal = RebarCommon.SafeNormalFor(b1, b2, h.Zv, h.Wv);
                                    RebarCommon.CreateSingleBar(doc, barType, h.Inst, b1, b2, normal);
                                    instCount++;
                                }
                            }
                        }
                        report.Add($"{h.Id}: đã tạo {instCount} thanh thép dọc (4 mặt x 2 lớp).");
                        totalCount += instCount;
                    }

                    t.Commit();
                }

                TaskDialog.Show("Thành công",
                    $"Đã tạo tổng cộng {totalCount} thanh thép dọc.\n\nChi tiết:\n" + string.Join("\n", report));
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
}
