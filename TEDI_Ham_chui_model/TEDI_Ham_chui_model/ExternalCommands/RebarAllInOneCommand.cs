using System;
using System.Collections.Generic;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Nut "Ve tat ca thep": PICK 3 mat (mat bang/mat dung/mat canh) CHI 1 LAN DUY
    // NHAT cho moi host da chon (RebarCommon.PickHostGeometry), roi tai su dung ket
    // qua hinh hoc do (HostGeometry - Lv/Wv/Zv, solid, offset W/Z...) de goi lan luot
    // RunOnPrepared() cua 4 lenh ve thep da co san (RebarStirrupCCommand,
    // RebarOuterShapeCommand, RebarInnerSingleCommand, RebarChamferCommand) - khong
    // con bat nguoi dung pick lai 3 mat cho tung lenh nhu truoc.
    //
    // Moi lenh van tu dung coverFt RIENG cua no (RebarOuterShapeCommand dung
    // DefaultCoverMm, 3 lenh con lai dung LongitudinalCoverMm - xem
    // RebarCommon.LongitudinalCoverMm) de xay lai FaceDef rieng tu CUNG 1
    // HostGeometry da pick (RebarCommon.PrepareHosts), KHONG dung chung 1
    // PreparedHost giua cac lenh vi FaceDef.OuterPos/InnerPos/CrossMin/CrossMax phu
    // thuoc coverFt.
    //
    // KHONG goi RebarLongitudinalCommand: RebarStirrupCCommand da tu ve lai toan bo
    // thep doc (4 mat x 2 lop Ngoai/Trong, xem RebarStirrupCCommand.cs) roi tao THEM
    // dai C - goi ca 2 se ve trung thep doc 2 lan.
    //
    // Moi lenh con tu mo/commit Transaction RIENG cua no trong RunOnPrepared, nen neu
    // 1 lenh sau do that bai (throw), cac lenh DA CHAY XONG TRUOC DO van giu nguyen
    // ket qua da tao (khong bi rollback theo), khac voi cach cu goi thang Execute()
    // cua tung lenh (moi lenh tu pick lai + tu show TaskDialog modal rieng, dan den
    // Revit co the lam mat selection giua cac lan Execute() lien tiep - xem lai lich
    // su sua loi truoc do).
    [Transaction(TransactionMode.Manual)]
    public class RebarAllInOneCommand : IExternalCommand
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

                var pickReport = new List<string>();
                var geometries = RebarCommon.PickHostGeometry(uidoc, doc, selectedIds, pickReport);
                if (geometries.Count == 0)
                {
                    message = "Không có cấu kiện hợp lệ nào để tạo thép sau bước pick.\n" + string.Join("\n", pickReport);
                    return Result.Failed;
                }

                double longitudinalCoverFt = RebarCommon.MmToFt(RebarCommon.LongitudinalCoverMm);
                double outerCoverFt = RebarCommon.MmToFt(RebarCommon.DefaultCoverMm);

                var summaries = new List<string>();
                if (pickReport.Count > 0) summaries.Add(string.Join("\n", pickReport));

                var stirrupReport = new List<string>();
                summaries.Add(RebarStirrupCCommand.RunOnPrepared(
                    doc, RebarCommon.PrepareHosts(geometries, longitudinalCoverFt), stirrupReport));

                var outerReport = new List<string>();
                summaries.Add(RebarOuterShapeCommand.RunOnPrepared(
                    doc, RebarCommon.PrepareHosts(geometries, outerCoverFt), outerReport));

                var innerReport = new List<string>();
                summaries.Add(RebarInnerSingleCommand.RunOnPrepared(
                    doc, RebarCommon.PrepareHosts(geometries, longitudinalCoverFt), innerReport));

                var chamferReport = new List<string>();
                summaries.Add(RebarChamferCommand.RunOnPrepared(
                    doc, RebarCommon.PrepareHosts(geometries, longitudinalCoverFt), chamferReport));

                TaskDialog.Show("Vẽ tất cả thép - Thành công", string.Join("\n\n", summaries));
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
