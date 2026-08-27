using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Thep gia cuong tai 2 goc vat TREN (trai + phai) noi tuong Trong gap Nap
    // Trong, dung cho tiet dien bi vat goc (Chamfer). Xem chi tiet trong
    // ChamferCornerReinforcement.cs.
    //
    // KHONG con la nut rieng (IExternalCommand) - chi con RunOnPrepared() de
    // RebarAllInOneCommand goi voi 1 List<PreparedHost> da pick san (xem
    // RebarAllInOneCommand.cs, nut "Vẽ tất cả thép" duy nhat).
    public static class RebarChamferCommand
    {
        public static string RunOnPrepared(Document doc, List<PreparedHost> prepared, List<string> report)
        {
            double coverFt = RebarCommon.MmToFt(RebarCommon.LongitudinalCoverMm);
            double chamferSpaceFt = RebarCommon.MmToFt(600); // khop voi "S6-D12-600(AS)" trong ban ve

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

            return $"Đã tạo tổng cộng {totalCount} thanh thép chéo góc vát.\n\nChi tiết:\n" + string.Join("\n", report);
        }
    }
}
