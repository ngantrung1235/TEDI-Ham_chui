using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;

namespace TEDI_Ham_chui_model.Models
{
    // Bo 2 cua LOP TRONG (chay ngang theo Wv voi Day/Nap, theo Zv voi Trai/Phai),
    // dung Single Bar (khong phai Rebar Set) de tranh loi mang chu nhat loi ra
    // ngoai ban day hinh binh hanh. Tao cho ca 4 mat (Day/Nap/Trai/Phai).
    //
    // KHONG con la nut rieng (IExternalCommand) - chi con RunOnPrepared() de
    // RebarAllInOneCommand goi voi 1 List<PreparedHost> da pick san (xem
    // RebarAllInOneCommand.cs, nut "Vẽ tất cả thép" duy nhat).
    public static class RebarInnerSingleLogic
    {
        // diamS1Mm/spaceS1Mm = mat Nap ("S1"), diamF1Mm/spaceF1Mm = mat Day ("F1"),
        // diamH1Mm/spaceH1Mm = mat Trai+Phai ("H1"). Moi nhom co RebarBarType RIENG.
        // Nguoi goi (RebarAllInOneViewModel) LUON truyen du ca 6 gia tri nay - khong con
        // gia tri mac dinh de tranh nham tuong co the goi "thieu" tham so.
        public static string RunOnPrepared(
            Document doc, List<PreparedHost> prepared, List<string> report,
            double diamS1Mm, double spaceS1Mm,
            double diamF1Mm, double spaceF1Mm,
            double diamH1Mm, double spaceH1Mm)
        {
            // Cover CHUAN (khong cong them duong kinh Rebar_21) dung rieng cho loSafe/hiSafe
            // ben duoi - khoang cach dau thanh toi dau cat cua host (dau dot) theo Lv, khong
            // lien quan gi den Rebar_21 (chi anh huong huong vuong goc mat).
            double lengthCoverFt = RebarCommon.MmToFt(RebarCommon.DefaultCoverMm);

            int totalCount = 0;
            using (Transaction t = new Transaction(doc, "Tạo thép single lớp Trong"))
            {
                t.Start();

                // Tao RebarBarType (thao tac ghi vao model) PHAI nam trong Transaction da
                // Start() - dat truoc do se nem "Attempt to modify the model outside of
                // transaction".
                var barTypeS1 = RebarCommon.GetOrCreateBarType(doc, $"S1-D{diamS1Mm:F0}-{spaceS1Mm:F0}", diamS1Mm, report);
                var barTypeF1 = RebarCommon.GetOrCreateBarType(doc, $"F1-D{diamF1Mm:F0}-{spaceF1Mm:F0}", diamF1Mm, report);
                var barTypeH1 = RebarCommon.GetOrCreateBarType(doc, $"H1-D{diamH1Mm:F0}-{spaceH1Mm:F0}", diamH1Mm, report);
                double diamFtS1 = RebarCommon.MmToFt(diamS1Mm), spaceFtS1 = RebarCommon.MmToFt(spaceS1Mm);
                double diamFtF1 = RebarCommon.MmToFt(diamF1Mm), spaceFtF1 = RebarCommon.MmToFt(spaceF1Mm);
                double diamFtH1 = RebarCommon.MmToFt(diamH1Mm), spaceFtH1 = RebarCommon.MmToFt(spaceH1Mm);

                foreach (var h in prepared)
                {
                    int instCount = 0;
                    foreach (var fd in h.FacesDef)
                    {
                        RebarBarType barType;
                        double diamFt, spaceFt;
                        if (fd.Name == "Nap") { barType = barTypeS1; diamFt = diamFtS1; spaceFt = spaceFtS1; }
                        else if (fd.Name == "Day") { barType = barTypeF1; diamFt = diamFtF1; spaceFt = spaceFtF1; }
                        else { barType = barTypeH1; diamFt = diamFtH1; spaceFt = spaceFtH1; }

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

            return $"Đã tạo tổng cộng {totalCount} thanh thép single lớp Trong.\n\nChi tiết:\n" + string.Join("\n", report);
        }
    }
}
