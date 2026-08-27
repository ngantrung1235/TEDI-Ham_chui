using System;
using System.Collections.Generic;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Nut "Tao thep cheo goc vat": thep gia cuong tai 2 goc vat TREN (trai +
    // phai) noi tuong Trong gap Nap Trong, dung cho tiet dien bi vat goc
    // (Chamfer). Xem chi tiet trong ChamferCornerReinforcement.cs.
    [Transaction(TransactionMode.Manual)]
    public class RebarChamferCommand : IExternalCommand
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

                // Dung RebarCommon.LongitudinalCoverMm (nguon DUY NHAT cho lop bao ve) thay vi
                // RebarCommon.DefaultCoverMm truc tiep, de thep cheo goc dong bo vi tri voi
                // long ho thep doc (Outer/InnerPos cua FaceDef) tren cung 1 host.
                double coverFt = RebarCommon.MmToFt(RebarCommon.LongitudinalCoverMm);
                double chamferSpaceFt = RebarCommon.MmToFt(600); // khop voi "S6-D12-600(AS)" trong ban ve

                var report = new List<string>();
                var prepared = RebarCommon.PickAndPrepareHosts(uidoc, doc, selectedIds, coverFt, report);
                if (prepared.Count == 0)
                {
                    message = "Không có cấu kiện hợp lệ nào để tạo thép sau bước pick.";
                    return Result.Failed;
                }

                int totalCount = 0;
                using (Transaction t = new Transaction(doc, "Tạo thép chéo góc vát"))
                {
                    t.Start();

                    var barTypeChamfer = RebarCommon.GetOrCreateBarType(doc, "D12", 12.0, report);

                    foreach (var h in prepared)
                    {
                        double chamferFt = ChamferCornerReinforcement.GetChamferFt(h.Inst);
                        ChamferCornerReinforcement.CreateChamferCornerBars(
                            doc, barTypeChamfer, h.Inst, h.Solid,
                            h.Lv, h.Wv, h.Zv, h.L2G,
                            h.WOff, h.ZOff,
                            chamferFt, coverFt,
                            h.LMinRaw, h.LMaxRaw, chamferSpaceFt,
                            report, h.Id, ref totalCount);
                    }

                    t.Commit();
                }

                TaskDialog.Show("Thành công",
                    $"Đã tạo tổng cộng {totalCount} thanh thép chéo góc vát.\n\nChi tiết:\n" + string.Join("\n", report));
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
