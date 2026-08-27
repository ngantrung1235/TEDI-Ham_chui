using System;
using System.Collections.Generic;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Nut "Tao thep single ben trong": Bo 2 cua LOP TRONG (chay ngang theo Wv
    // voi Day/Nap, theo Zv voi Trai/Phai), dung Single Bar (khong phai Rebar
    // Set) de tranh loi mang chu nhat loi ra ngoai ban day hinh binh hanh.
    // Tao cho ca 4 mat (Day/Nap/Trai/Phai).
    [Transaction(TransactionMode.Manual)]
    public class RebarInnerSingleCommand : IExternalCommand
    {
        // TODO: se duoc nguoi dung nhap tu giao dien (form nhap lieu) o phien ban sau -
        // rieng cho nut "Tao thep single ben trong" nay, khong dung chung voi cac nut khac.
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

                // Dung RebarCommon.LongitudinalCoverMm (nguon DUY NHAT cho lop bao ve) thay vi
                // RebarCommon.DefaultCoverMm truc tiep, vi thanh nay cung nam tai InnerPos cua
                // FaceDef - phai dong bo voi vi tri lop Trong cua thep doc (RebarStirrupCCommand/
                // RebarLongitudinalCommand) tren cung 1 host.
                double coverFt = RebarCommon.MmToFt(RebarCommon.LongitudinalCoverMm);
                // Cover CHUAN (khong cong them duong kinh Rebar 0) dung rieng cho loSafe/hiSafe
                // ben duoi - khoang cach dau thanh toi dau cat cua host (dau dot) theo Lv, khong
                // lien quan gi den Rebar 0 (chi anh huong huong vuong goc mat).
                double lengthCoverFt = RebarCommon.MmToFt(RebarCommon.DefaultCoverMm);
                double diamFt = RebarCommon.MmToFt(DefaultDiamMm);
                double spaceFt = RebarCommon.MmToFt(DefaultSpaceMm);

                var report = new List<string>();
                var prepared = RebarCommon.PickAndPrepareHosts(uidoc, doc, selectedIds, coverFt, report);
                if (prepared.Count == 0)
                {
                    message = "Không có cấu kiện hợp lệ nào để tạo thép sau bước pick.";
                    return Result.Failed;
                }

                int totalCount = 0;
                using (Transaction t = new Transaction(doc, "Tạo thép single lớp Trong"))
                {
                    t.Start();

                    var barType = RebarCommon.GetOrCreateBarType(doc, "D20", DefaultDiamMm, report);

                    foreach (var h in prepared)
                    {
                        int instCount = 0;
                        foreach (var fd in h.FacesDef)
                        {
                            double pos = fd.InnerPos;
                            double otherPos = fd.OuterPos;

                            double dirSign = Math.Sign(otherPos - pos);
                            double posNudged = pos + dirSign * diamFt;

                            double loSafe = h.LMinRaw + lengthCoverFt;
                            double hiSafe = h.LMaxRaw - lengthCoverFt;

                            // Rai dung THEO DUNG khoang cach thiet ke spaceFt (150mm) tinh tu
                            // loSafe - KHONG chia deu lai lLen (khoang cach phai dung bang gia tri
                            // dau vao). Phan du con lai o dau xa (hiSafe) neu khong vua het 1 buoc
                            // thi BO TRONG.
                            var lPositions = new List<double>();
                            for (double p = loSafe; p <= hiSafe; p += spaceFt)
                                lPositions.Add(p);

                            foreach (double lPos in lPositions)
                            {
                                XYZ p2s = fd.IsSlab ? h.L2G(lPos, fd.CrossMin, posNudged) : h.L2G(lPos, posNudged, fd.CrossMin);
                                XYZ p2e = fd.IsSlab ? h.L2G(lPos, fd.CrossMax, posNudged) : h.L2G(lPos, posNudged, fd.CrossMax);

                                // Normal tinh TRUC TIEP tu huong that cua thanh (p2s->p2e); truong
                                // hop thanh dung (tuong) thi Zv x dir suy bien -> fallback dung Lv
                                // (luon vuong goc voi phuong dung).
                                XYZ normal = RebarCommon.SafeNormalFor(p2s, p2e, h.Zv, h.Lv);
                                RebarCommon.CreateSingleBar(doc, barType, h.Inst, p2s, p2e, normal);
                                instCount++;
                            }
                        }
                        report.Add($"{h.Id}: đã tạo {instCount} thanh thép single lớp Trong (4 mặt).");
                        totalCount += instCount;
                    }

                    t.Commit();
                }

                TaskDialog.Show("Thành công",
                    $"Đã tạo tổng cộng {totalCount} thanh thép single lớp Trong.\n\nChi tiết:\n" + string.Join("\n", report));
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
