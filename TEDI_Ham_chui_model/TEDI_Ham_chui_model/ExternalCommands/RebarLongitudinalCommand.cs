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

                    var barType = RebarCommon.GetOrCreateBarType(doc, "D20", RebarCommon.DefaultDiamMm, report);

                    foreach (var h in prepared)
                    {
                        int instCount = 0;
                        foreach (var fd in h.FacesDef)
                        {
                            foreach (var pos in new[] { fd.OuterPos, fd.InnerPos })
                            {
                                double crossLen = fd.CrossMax - fd.CrossMin;
                                int nRows = (int)Math.Ceiling(crossLen / spaceFt) + 1;
                                if (nRows < 2) nRows = 2;
                                double rowSpacing = crossLen / (nRows - 1);

                                for (int i = 0; i < nRows; i++)
                                {
                                    double crossPos = fd.CrossMin + i * rowSpacing;
                                    XYZ probeA = fd.IsSlab ? h.L2G(h.LMinRaw, crossPos, pos) : h.L2G(h.LMinRaw, pos, crossPos);
                                    XYZ probeB = fd.IsSlab ? h.L2G(h.LMaxRaw, crossPos, pos) : h.L2G(h.LMaxRaw, pos, crossPos);
                                    var range = RebarCommon.ProbeSolidLRange(h.Solid, probeA, probeB, h.Lv);
                                    if (range == null) continue;
                                    double rowLo = range.Value.lo + coverFt;
                                    double rowHi = range.Value.hi - coverFt;
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
