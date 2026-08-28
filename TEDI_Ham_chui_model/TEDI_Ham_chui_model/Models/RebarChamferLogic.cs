using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace TEDI_Ham_chui_model.Models
{
    // Thep gia cuong tai 2 goc vat TREN (trai + phai) noi tuong Trong gap Nap
    // Trong, dung cho tiet dien bi vat goc (Chamfer). Xem chi tiet trong
    // ChamferCornerReinforcement.cs.
    //
    // KHONG con la nut rieng (IExternalCommand) - chi con RunOnPrepared() de
    // RebarAllInOneCommand goi voi 1 List<PreparedHost> da pick san (xem
    // RebarAllInOneCommand.cs, nut "Vẽ tất cả thép" duy nhat).
    public static class RebarChamferLogic
    {
        // coverMm PHAI la CUNG gia tri (CoverMm + duong kinh Rebar_21) da dung de
        // PrepareHosts() cho lenh nay - xem RebarAllInOneViewModel.Run(). Nguoi goi LUON
        // truyen du tham so, khong con gia tri mac dinh.
        public static string RunOnPrepared(
            Document doc, List<PreparedHost> prepared, List<string> report,
            double diamS5Mm, double spaceS5Mm, double coverMm)
        {
            double coverFt = RebarCommon.MmToFt(coverMm);
            double chamferSpaceFt = RebarCommon.MmToFt(spaceS5Mm);

            int totalCount = 0;
            using (Transaction t = new Transaction(doc, "Tạo thép chéo góc vát"))
            {
                t.Start();

                var barTypeChamfer = RebarCommon.GetOrCreateBarType(doc, $"S5-D{diamS5Mm:F0}-{spaceS5Mm:F0}", diamS5Mm, report);

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

            return $"Đã tạo tổng cộng {totalCount} thanh thép chéo góc vát.\n\nChi tiết:\n" + string.Join("\n", report);
        }
    }
}
