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
        // PrepareHosts() cho lenh nay - xem RebarAllInOneSettings.Run(). Nguoi goi LUON
        // truyen du tham so, khong con gia tri mac dinh.
        // diamS2Mm: duong kinh thep Rebar_21 mat Nap ("S2") - dung de offset vi tri bat
        // dau doc Lv cua S5 mot khoang bang chinh duong kinh nay (xem ghi chu trong
        // ChamferCornerReinforcement.CreateChamferCornerBars), tuong tu co che "luot 2"
        // cua dai C trong RebarStirrupCLogic.cs, de S5 khong rai trung vi tri L voi
        // Rebar_21.
        public static string RunOnPrepared(
            Document doc, List<PreparedHost> prepared, List<string> report,
            double diamS5Mm, double spaceS5Mm, double coverMm,
            double extendMm, double diamS2Mm)
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
                        extendMm, diamS2Mm,
                        report, h.Id, ref totalCount);
                }

                t.Commit();
            }

            return $"Đã tạo tổng cộng {totalCount} thanh thép chéo góc vát.\n\nChi tiết:\n" + string.Join("\n", report);
        }
    }
}
