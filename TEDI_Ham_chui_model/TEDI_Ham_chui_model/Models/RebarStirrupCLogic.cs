using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;

namespace TEDI_Ham_chui_model.Models
{
    // Thep doc chay theo Lv, tung thanh rieng bam sat bien solid, ca 4 mat x 2 lop
    // Ngoai/Trong, cong THEM cac dai chu C noi thanh lop Ngoai voi thanh lop Trong
    // (khong noi 2 thanh canh nhau trong cung 1 lop). Dai C dung 2 spacing DOC LAP
    // voi spacing thep doc: theo phuong ngang mat (Wv/cross) cac hang dai C duoc
    // chia deu theo spacing dai C nguoi dung nhap (giong het cach
    // spaceFt chia hang thep doc), va theo phuong Lv cung rai deu voi cung
    // spacing do (xem CreateOuterInnerTies).
    //
    // Dai C hinh chu "C": than dai chay doc truc do sau (tu OuterPos toi InnerPos),
    // 2 dau bo mop cung 1 huong ngang (cross) - dung 3 doan thang (hook - than - hook)
    // vi ban Revit API dang dung KHONG con enum RebarHookOrientation nen khong the
    // dung tham so hook rieng cho CreateFromCurves nhu ban cu (xem ghi chu tuong tu
    // trong RebarOuterShapeLogic.cs).
    //
    // KHONG con la nut rieng (IExternalCommand) - chi con RunOnPrepared() de
    // RebarAllInOneCommand goi voi 1 List<PreparedHost> da pick san (xem
    // RebarAllInOneCommand.cs, nut "Vẽ tất cả thép" duy nhat).
    public static class RebarStirrupCLogic
    {
        // diamS4Mm/spaceS4Mm = thep doc mat Nap ("S4"), diamF4Mm/spaceF4Mm = mat Day
        // ("F4"), diamH2Mm/spaceH2Mm = mat Trai+Phai ("H2"). diamS6Mm/spaceS6Mm = dai C
        // mat Nap ("S6"), diamF6Mm/spaceF6Mm = mat Day ("F6"), diamH3Mm/spaceH3Mm = mat
        // Trai+Phai ("H3"). Moi nhom co RebarBarType RIENG. Nguoi goi (RebarAllInOneViewModel)
        // LUON truyen du ca 12 gia tri nay.
        public static string RunOnPrepared(
            Document doc, List<PreparedHost> prepared, List<string> report,
            double diamS4Mm, double spaceS4Mm,
            double diamF4Mm, double spaceF4Mm,
            double diamH2Mm, double spaceH2Mm,
            double diamS6Mm, double spaceS6Mm,
            double diamF6Mm, double spaceF6Mm,
            double diamH3Mm, double spaceH3Mm)
        {
            // Cover CHUAN (khong cong them duong kinh Rebar_21) dung rieng cho cac cho CAT
            // THEO CHIEU DAI Lv (oLo/oHi/iLo/iHi ben duoi) - day la khoang cach dau thanh
            // thep toi dau cat cua host (dau dot), KHONG lien quan gi den Rebar_21 (Rebar_21
            // chi anh huong huong vuong goc mat, khong anh huong doc Lv).
            double lengthCoverFt = RebarCommon.MmToFt(RebarCommon.DefaultCoverMm);

            int totalLong = 0, totalTie = 0;
            using (Transaction t = new Transaction(doc, "Tạo thép dọc + đai C"))
            {
                t.Start();

                // Tao RebarBarType (thao tac ghi vao model) PHAI nam trong Transaction da
                // Start() - dat truoc do se nem "Attempt to modify the model outside of
                // transaction".
                var barTypeS4 = RebarCommon.GetOrCreateBarType(doc, $"S4-D{diamS4Mm:F0}-{spaceS4Mm:F0}", diamS4Mm, report);
                var barTypeF4 = RebarCommon.GetOrCreateBarType(doc, $"F4-D{diamF4Mm:F0}-{spaceF4Mm:F0}", diamF4Mm, report);
                var barTypeH2 = RebarCommon.GetOrCreateBarType(doc, $"H2-D{diamH2Mm:F0}-{spaceH2Mm:F0}", diamH2Mm, report);
                double spaceFtS4 = RebarCommon.MmToFt(spaceS4Mm);
                double spaceFtF4 = RebarCommon.MmToFt(spaceF4Mm);
                double spaceFtH2 = RebarCommon.MmToFt(spaceH2Mm);

                var tieBarTypeS6 = RebarStirrupCCommon.GetOrCreateTightBendTieType(
                    doc, RebarCommon.GetOrCreateBarType(doc, $"S6-D{diamS6Mm:F0}-{spaceS6Mm:F0}", diamS6Mm, report), diamS4Mm, diamS6Mm, report);
                var tieBarTypeF6 = RebarStirrupCCommon.GetOrCreateTightBendTieType(
                    doc, RebarCommon.GetOrCreateBarType(doc, $"F6-D{diamF6Mm:F0}-{spaceF6Mm:F0}", diamF6Mm, report), diamF4Mm, diamF6Mm, report);
                var tieBarTypeH3 = RebarStirrupCCommon.GetOrCreateTightBendTieType(
                    doc, RebarCommon.GetOrCreateBarType(doc, $"H3-D{diamH3Mm:F0}-{spaceH3Mm:F0}", diamH3Mm, report), diamH2Mm, diamH3Mm, report);
                double tieSpaceFtS6 = RebarCommon.MmToFt(spaceS6Mm);
                double tieSpaceFtF6 = RebarCommon.MmToFt(spaceF6Mm);
                double tieSpaceFtH3 = RebarCommon.MmToFt(spaceH3Mm);

                    foreach (var h in prepared)
                    {
                        int instCount = 0;
                        var tieRecords = new List<RebarStirrupCCommon.TieRecord>();
                        foreach (var fd in h.FacesDef)
                        {
                            RebarBarType barType; double spaceFt; double barDiamMmFace;
                            RebarBarType tieBarType; double tieSpaceFt; double tieDiamMmFace;
                            if (fd.Name == "Nap")
                            {
                                barType = barTypeS4; spaceFt = spaceFtS4; barDiamMmFace = diamS4Mm;
                                tieBarType = tieBarTypeS6; tieSpaceFt = tieSpaceFtS6; tieDiamMmFace = diamS6Mm;
                            }
                            else if (fd.Name == "Day")
                            {
                                barType = barTypeF4; spaceFt = spaceFtF4; barDiamMmFace = diamF4Mm;
                                tieBarType = tieBarTypeF6; tieSpaceFt = tieSpaceFtF6; tieDiamMmFace = diamF6Mm;
                            }
                            else
                            {
                                barType = barTypeH2; spaceFt = spaceFtH2; barDiamMmFace = diamH2Mm;
                                tieBarType = tieBarTypeH3; tieSpaceFt = tieSpaceFtH3; tieDiamMmFace = diamH3Mm;
                            }

                            // --- Thep doc: rai dung THEO DUNG khoang cach thiet ke spaceFt (150mm)
                            // tinh tu CrossMin - KHONG chia deu lai crossLen (giong het nguyen tac
                            // da ap dung cho dai C: khoang cach phai dung bang gia tri dau vao,
                            // khong duoc tu dong co gian). Phan du con lai o dau xa (CrossMax) neu
                            // khong vua het 1 buoc thi BO TRONG, khong ep them hang nao ca. Vi
                            // spacing dai C (mac dinh 600mm) = 4 x spacing thep doc (mac dinh 150mm) NEU dung so mac dinh, cu moi
                            // 4 hang thep doc se co 1 hang trung khop voi 1 hang dai C.
                            var rowCrossPositions = new List<double>();
                            for (double p = fd.CrossMin; p <= fd.CrossMax; p += spaceFt)
                                rowCrossPositions.Add(p);

                            foreach (double crossPos in rowCrossPositions)
                            {

                                XYZ outerProbeA = RebarStirrupCCommon.Pt(h, fd, h.LMinRaw, crossPos, fd.OuterPos);
                                XYZ outerProbeB = RebarStirrupCCommon.Pt(h, fd, h.LMaxRaw, crossPos, fd.OuterPos);
                                var outerRange = RebarCommon.ProbeSolidLRange(h.Solid, outerProbeA, outerProbeB, h.Lv);

                                XYZ innerProbeA = RebarStirrupCCommon.Pt(h, fd, h.LMinRaw, crossPos, fd.InnerPos);
                                XYZ innerProbeB = RebarStirrupCCommon.Pt(h, fd, h.LMaxRaw, crossPos, fd.InnerPos);
                                var innerRange = RebarCommon.ProbeSolidLRange(h.Solid, innerProbeA, innerProbeB, h.Lv);

                                if (outerRange == null || innerRange == null) continue;

                                double oLo = outerRange.Value.lo + lengthCoverFt, oHi = outerRange.Value.hi - lengthCoverFt;
                                double iLo = innerRange.Value.lo + lengthCoverFt, iHi = innerRange.Value.hi - lengthCoverFt;
                                if (oHi - oLo < RebarCommon.MmToFt(20) || iHi - iLo < RebarCommon.MmToFt(20)) continue;

                                XYZ oP1 = RebarStirrupCCommon.Pt(h, fd, oLo, crossPos, fd.OuterPos);
                                XYZ oP2 = RebarStirrupCCommon.Pt(h, fd, oHi, crossPos, fd.OuterPos);
                                XYZ iP1 = RebarStirrupCCommon.Pt(h, fd, iLo, crossPos, fd.InnerPos);
                                XYZ iP2 = RebarStirrupCCommon.Pt(h, fd, iHi, crossPos, fd.InnerPos);

                                XYZ normalOuter = RebarCommon.SafeNormalFor(oP1, oP2, h.Zv, h.Wv);
                                RebarCommon.CreateSingleBar(doc, barType, h.Inst, oP1, oP2, normalOuter);

                                XYZ normalInner = RebarCommon.SafeNormalFor(iP1, iP2, h.Zv, h.Wv);
                                RebarCommon.CreateSingleBar(doc, barType, h.Inst, iP1, iP2, normalInner);
                                instCount += 2;
                            }

                            // --- Dai C: rai rieng theo tieSpaceFt (khoang cach dai C), DOC LAP voi
                            // hang thep doc o tren - khong con phu thuoc chi so hang i cua thep doc
                            // (khong con bo hang goc / chi giu hang chan), ma phuong ngang (cross)
                            // cung duoc chia deu theo spacing dai C nguoi dung nhap, giong het cach spaceFt
                            // chia hang thep doc theo phuong Lv.
                            //
                            // Truoc khi chia hang, DO TIM ranh gioi an toan o CA 2 dau CrossMin/
                            // CrossMax (RebarStirrupCCommon.FindSafeCrossEdge) - de tranh cac hang
                            // dai C rot vao vung tiet dien bi VAT GOC (vd 2 goc vat tren cua mat
                            // Trai/Phai, noi giap Nap - xem RebarChamferLogic.cs), la vung tiet
                            // dien thu hep phi tuyen nen RAT nhay cam moi khi doi lop bao ve
                            // (coverFt) - chinh la nguyen nhan gay "lech" hang dai C quan sat duoc.
                            // Dau nao khong dinh vat (vd Day, hoac dau CrossMin cua Trai/Phai giap
                            // goc vuong voi Day) thi ham tra ve NGUYEN dau danh nghia, khong doi gi.
                            double safeCrossMin = RebarStirrupCCommon.FindSafeCrossEdge(h, fd, fd.CrossMin, fd.CrossMax, lengthCoverFt);
                            double safeCrossMax = RebarStirrupCCommon.FindSafeCrossEdge(h, fd, fd.CrossMax, fd.CrossMin, lengthCoverFt);
                            double crossLenSafe = safeCrossMax - safeCrossMin;
                            if (crossLenSafe < RebarCommon.MmToFt(20))
                            {
                                report.Add($"{h.Id} mặt {fd.Name}: bỏ qua đai C - toàn bộ chiều rộng mặt đều nằm trong vùng vát góc/không đo được bê tông hợp lệ.");
                                continue;
                            }

                            // Rai dung THEO DUNG khoang cach thiet ke tieSpaceFt (600mm) - KHONG chia
                            // deu lai crossLenSafe (do se lam sai lech khoang cach thiet ke ket cau).
                            // Cac hang cach nhau CHINH XAC tieSpaceFt tinh tu safeCrossMin, dung het
                            // moi buoc du con vua het trong [safeCrossMin, safeCrossMax]. KHONG ep
                            // them hang tai safeCrossMax de khep bien - phan du con lai o dau xa
                            // (thuong la dinh, giap Nap/Phai/...) duoc BO TRONG, khong tao them
                            // thanh nao ca (dung yeu cau: khoang cach phai dung 600mm nhu dau vao,
                            // khong duoc phep co 1 doan le hut ngan hon o cuoi).
                            //
                            // LUOT 2 (theo thiet ke moi): dai C luot 2 XEN KE GIUA 2 dai C luot 1
                            // theo CA 2 phuong - vua theo phuong cross (Wv/Zv, nhin vao se thay luot 2
                            // nam CHINH GIUA 2 dai luot 1 lien tiep) vua theo phuong doc Lv (dat sau
                            // hon 1 doan tieSpaceFt/2, xem khoi comment ben duoi). Ca 2 luot CUNG neo
                            // tai safeCrossMin (KHONG con neo tai safeCrossMax nua) - luot 2 chi lech
                            // 1 khoang co dinh tieSpaceFt/2 so voi luot 1.
                            //
                            // Vi sao van luon trung dung 1 hang thep doc that (khong con bi "noi troi"
                            // nhu truoc day khi neo tai safeCrossMax): tieSpaceFt (600mm) = 4 x spaceFt
                            // (mac dinh 150mm), nen tieSpaceFt/2
                            // (300mm) = 2 x spaceFt LUON LUON la boi so CHAN cua spaceFt, bat ke hinh
                            // hoc mat cat the nao. Vi luot 1 (neo safeCrossMin, buoc tieSpaceFt) da
                            // dam bao trung luoi thep doc (dong bo voi vong lap "rowCrossPositions" o
                            // tren, cung neo safeCrossMin), luot 2 neo tai "safeCrossMin + spaceFt*2"
                            // roi cung buoc tieSpaceFt se TU DONG trung 1 hang thep doc KHAC (cach hang
                            // luot 1 dung 2 buoc spaceFt = giua 2 hang luot 1 lien tiep cua chinh no,
                            // vi 1 chu ky tieSpaceFt = 4 hang thep doc) - khong can snap/lam tron gi
                            // them, khac voi cach neo tai safeCrossMax (1 diem hinh hoc bat ky, KHONG
                            // dam bao la boi so cua spaceFt tinh tu safeCrossMin) da gay loi dai C
                            // lech luoi 40mm o phien ban truoc.
                            double crossOffsetPass2Ft = tieSpaceFt / 2.0;
                            //
                            // Rieng doc theo phuong Lv (ben trong CreateOuterInnerTies): cac dai C
                            // cua LUOT 2 phai bat dau lech so voi luot 1 mot doan dung bang NUA buoc
                            // tieSpaceFt (vd 600mm -> lech 300mm), tuc diem dau tien theo Lv cua luot 2
                            // = diem dau tien theo Lv cua luot 1 + tieSpaceFt/2. Dung tieCrossEntries
                            // (kem lLvOffsetFt rieng cho tung luot) de truyen xuong CreateOuterInnerTies
                            // ben duoi.
                            double lLvOffsetPass2Ft = tieSpaceFt / 2.0;
                            var tieCrossEntries = new List<(double CrossPos, double LOffsetFt)>();
                            for (double pos = safeCrossMin; pos <= safeCrossMax; pos += tieSpaceFt)
                                tieCrossEntries.Add((pos, 0.0));

                            for (double pos = safeCrossMin + crossOffsetPass2Ft; pos <= safeCrossMax; pos += tieSpaceFt)
                                tieCrossEntries.Add((pos, lLvOffsetPass2Ft));

                            // TCVN 11823 Muc 10.6.3 gioi han khoang cach toi da giua cac moc giu cu
                            // doc chu vi dai la 610mm - canh bao neu tieSpaceFt cau hinh vuot qua
                            // (doan cuoi luon <= tieSpaceFt nen khong can kiem tra rieng).
                            double tieCrossSpacingMm = RebarCommon.FtToMm(tieSpaceFt);
                            if (tieCrossSpacingMm > 610.0)
                            {
                                report.Add($"{h.Id} mặt {fd.Name}: CẢNH BÁO - khoảng cách đai C theo phương ngang là {tieCrossSpacingMm:F0}mm, vượt quá 610mm (TCVN 11823 Mục 10.6.3 - khoảng cách tối đa giữa các móc giữ cữ dọc theo chu vi cốt đai).");
                            }

                            foreach (var tieCrossEntry in tieCrossEntries)
                            {
                                double crossPos = tieCrossEntry.CrossPos;
                                double lOffsetFt = tieCrossEntry.LOffsetFt;

                                XYZ outerProbeA = RebarStirrupCCommon.Pt(h, fd, h.LMinRaw, crossPos, fd.OuterPos);
                                XYZ outerProbeB = RebarStirrupCCommon.Pt(h, fd, h.LMaxRaw, crossPos, fd.OuterPos);
                                var outerRange = RebarCommon.ProbeSolidLRange(h.Solid, outerProbeA, outerProbeB, h.Lv);

                                XYZ innerProbeA = RebarStirrupCCommon.Pt(h, fd, h.LMinRaw, crossPos, fd.InnerPos);
                                XYZ innerProbeB = RebarStirrupCCommon.Pt(h, fd, h.LMaxRaw, crossPos, fd.InnerPos);
                                var innerRange = RebarCommon.ProbeSolidLRange(h.Solid, innerProbeA, innerProbeB, h.Lv);

                                if (outerRange == null || innerRange == null) continue;

                                double oLo = outerRange.Value.lo + lengthCoverFt, oHi = outerRange.Value.hi - lengthCoverFt;
                                double iLo = innerRange.Value.lo + lengthCoverFt, iHi = innerRange.Value.hi - lengthCoverFt;
                                if (oHi - oLo < RebarCommon.MmToFt(20) || iHi - iLo < RebarCommon.MmToFt(20)) continue;

                                double tieLo = Math.Max(oLo, iLo);
                                double tieHi = Math.Min(oHi, iHi);
                                if (tieHi - tieLo < RebarCommon.MmToFt(20)) continue;

                                var madeTies = RebarStirrupCCommon.CreateOuterInnerTies(
                                    doc, h, fd, crossPos, tieLo, tieHi, tieBarType, barDiamMmFace, tieDiamMmFace, tieSpaceFt, report, lOffsetFt);
                                tieRecords.AddRange(madeTies);
                            }
                        }

                        // Sau khi tao het dai C tren CA 4 mat, cac dai o hang giap 2 canh cua 1
                        // goc (vd hang cuoi cua mat Day va hang dau/cuoi cua mat Trai/Phai) co the
                        // rai trung/giao nhau vat ly tai chinh goc do (2 dai tu 2 mat khac nhau
                        // cung ram lay chum thep doc goc). Quet bounding-box theo tung cap dai
                        // trong CUNG 1 host, dai nao giao nhau thi bo CA HAI.
                        int tieCount = RebarStirrupCCommon.RemoveOverlappingTies(doc, tieRecords, report, h.Id);

                        report.Add($"{h.Id}: đã tạo {instCount} thanh thép dọc (4 mặt x 2 lớp) + {tieCount} đai C.");
                        totalLong += instCount;
                        totalTie += tieCount;
                    }

                    t.Commit();
                }

            return $"Đã tạo tổng cộng {totalLong} thanh thép dọc và {totalTie} đai C.\n\nChi tiết:\n" + string.Join("\n", report);
        }
    }

    // ============================================================================
    // Helper rieng cho dai chu C - noi thanh thep doc lop Ngoai voi lop Trong tren
    // cung 1 mat (Day/Nap/Trai/Phai), tai CHINH crossPos hien tai. Dai nam trong mat
    // phang (cross, do sau) tai 1 vi tri L co dinh.
    //
    // MAT DO THEO PHUONG NGANG (chieu rong mat): so hang crossPos duoc Execute() chia
    // deu rieng theo spacing dai C nguoi dung nhap (doc lap voi so hang thep doc, von chia theo
    // spacing thep doc) - xem canh bao TCVN 11823 Muc 10.6.3 (610mm) trong Execute().
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
    // ma thep doc (RebarStirrupCLogic.Execute) da dung de dung diem oP1/oP2/iP1/iP2
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
        // Kiem tra 1 crossPos co "do duoc" hop le hay khong (dung DUNG y het tieu chi ma vong
        // lap rai hang dai C se dung: outer/inner probe khong null, moi lop >=20mm, va phan
        // GIAO 2 lop >=20mm) - dung chung cho ca vong rai THAT lan ham do bien an toan ben duoi.
        public static bool IsCrossPosUsable(PreparedHost h, FaceDef fd, double crossPos, double coverFt)
        {
            XYZ outerA = Pt(h, fd, h.LMinRaw, crossPos, fd.OuterPos);
            XYZ outerB = Pt(h, fd, h.LMaxRaw, crossPos, fd.OuterPos);
            var outerRange = RebarCommon.ProbeSolidLRange(h.Solid, outerA, outerB, h.Lv);

            XYZ innerA = Pt(h, fd, h.LMinRaw, crossPos, fd.InnerPos);
            XYZ innerB = Pt(h, fd, h.LMaxRaw, crossPos, fd.InnerPos);
            var innerRange = RebarCommon.ProbeSolidLRange(h.Solid, innerA, innerB, h.Lv);

            if (outerRange == null || innerRange == null) return false;

            double oLo = outerRange.Value.lo + coverFt, oHi = outerRange.Value.hi - coverFt;
            double iLo = innerRange.Value.lo + coverFt, iHi = innerRange.Value.hi - coverFt;
            if (oHi - oLo < RebarCommon.MmToFt(20) || iHi - iLo < RebarCommon.MmToFt(20)) return false;

            double tieLo = Math.Max(oLo, iLo);
            double tieHi = Math.Min(oHi, iHi);
            return (tieHi - tieLo) >= RebarCommon.MmToFt(20);
        }

        // Neu chinh dau "nominalEdge" (vd CrossMax cua mat Trai/Phai - dau giap goc vat tren voi
        // Nap, xem RebarChamferLogic.cs) da KHONG con do duoc be tong hop le, do BINARY SEARCH
        // lui dan ve phia "otherEdge" (dau con lai, gia dinh luon on dinh) de tim ranh gioi THAT
        // giua vung tiet dien on dinh va vung bi vat/thu hep phi tuyen, roi lui them 1 khoang an
        // toan (20mm) sau vao vung on dinh. Neu nominalEdge van do duoc binh thuong (truong hop
        // Day, hoac CrossMin cua Trai/Phai - dau giap goc vuong voi Day, khong vat) thi tra ve
        // NGUYEN nominalEdge, khong doi gi ca (fast path, khong ton chi phi do them).
        //
        // Muc dich: nTieRows/tieRowSpacing duoc tinh tuyen tinh deu tren [CrossMin,CrossMax] danh
        // nghia - neu 1 dau nam trong vung vat (tiet dien thu hep phi tuyen theo do cao/be rong),
        // cac hang dai C gan dau do se "lech" that thuong moi khi doi lop bao ve (coverFt), vi chi
        // 1 thay doi nho cung du day hang do vao/ra khoi vung con do duoc be tong. Dung bien an
        // toan nay lam moc chia hang thay vi CrossMin/CrossMax danh nghia se giu dai C luon nam
        // gon trong vung tiet dien on dinh, khong con nhay cam voi thay doi coverFt nua.
        public static double FindSafeCrossEdge(PreparedHost h, FaceDef fd, double nominalEdge, double otherEdge, double coverFt)
        {
            if (IsCrossPosUsable(h, fd, nominalEdge, coverFt)) return nominalEdge;

            double dir = Math.Sign(otherEdge - nominalEdge);
            double lo = nominalEdge, hi = otherEdge; // bat bien: lo luon KHONG do duoc, hi luon do duoc
            for (int iter = 0; iter < 20; iter++)
            {
                double mid = (lo + hi) / 2.0;
                if (IsCrossPosUsable(h, fd, mid, coverFt)) hi = mid; else lo = mid;
            }

            double marginFt = RebarCommon.MmToFt(20.0);
            double safeEdge = hi + dir * marginFt;
            if (dir > 0 && safeEdge > otherEdge) safeEdge = otherEdge;
            if (dir < 0 && safeEdge < otherEdge) safeEdge = otherEdge;
            return safeEdge;
        }

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

            // Ten Type gom CA barDiamMm (khong chi tieBarType.Name) vi ban kinh bo goc phu
            // thuoc CA HAI duong kinh - neu chi dat theo tieBarType.Name, 2 nhom co CUNG
            // duong kinh dai nhung KHAC duong kinh thep doc (vd S6/H3 cung D8 nhung S4/H2
            // khac D) se bi trung ten va lay nham ban kinh bo goc cua nhau.
            string newTypeName = $"{tieBarType.Name}_C_Tie_Tight_L{barDiamMm:F0}";
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
        //     (10*duong kinh dai C) de mocneo chac, KHONG con vuot qua tam thanh.
        // rCenterFt dung dung StirrupTieBendDiameter cua tieBarType (ban kinh bo goc
        // THAT Revit se ve) + ban kinh thep dai, thay vi ban kinh thep doc truoc day,
        // de diem dat va cung bo goc luon khop nhau (khong con lech gay dai chong
        // chan thanh thep tai goc bo).
        // Ket qua tao 1 dai C: kem san bounding-box THAT (tinh truc tiep tu 6 diem
        // dung de dung hinh, no ra 1 khoang tieRadiusFt de tinh ca be day thanh thep
        // dai) - dung de RemoveOverlappingTies so sanh MA KHONG can doc lai bbox tu
        // Revit (element.get_BoundingBox(null) tra ve null/sai cho element MOI TAO
        // trong cung 1 Transaction chua Regenerate - day chinh la ly do lan truoc
        // dai o goc van khong bi loc du da co RemoveOverlappingTies).
        public struct TieRecord
        {
            public ElementId Id;
            public XYZ Min;
            public XYZ Max;
        }

        public static List<TieRecord> CreateOuterInnerTies(
            Document doc, PreparedHost h, FaceDef fd, double crossPos,
            double lLo, double lHi, RebarBarType tieBarType, double barDiamMm, double tieDiamMm, double tieSpacingFt,
            List<string> report, double lOffsetFt = 0.0)
        {
            var madeTies = new List<TieRecord>();
            try
            {
                double tieDiamFt = RebarCommon.MmToFt(tieDiamMm);
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
                double hookFootFt = RebarCommon.MmToFt(10.0 * tieDiamMm);

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

                // Rai dung THEO DUNG khoang cach thiet ke tieSpacingFt (600mm) doc Lv - KHONG chia
                // deu lai (spanFt/(count-1)) vi se lam sai lech khoang cach thiet ke ket cau (yeu
                // cau: khoang cach phai dung bang gia tri dau vao, khong duoc tu dong co gian).
                // Cac vi tri cach nhau CHINH XAC tieSpacingFt tinh tu (lLo + lOffsetFt), dung het
                // moi buoc du con vua het trong [lLo, lHi]. KHONG ep them vi tri tai lHi de khep
                // bien - phan du con lai o dau xa bi BO TRONG, khong tao them dai nao (dung yeu
                // cau: khoang cach phai dung 600mm nhu dau vao, khong duoc phep co 1 doan le hut
                // ngan hon). lOffsetFt dung cho LUOT 2 (dai C tu safeCrossMax) trong
                // RebarStirrupCLogic.Execute() - lech nua buoc (tieSpacingFt/2) so voi diem dau
                // tien cua luot 1, de dai luot 2 xen ke giua cac dai luot 1 doc theo Lv.
                var lPositions = new List<double>();
                for (double lp = lLo + lOffsetFt; lp <= lHi; lp += tieSpacingFt)
                    lPositions.Add(lp);

                var terminations = new BarTerminationsData(doc);

                foreach (double l in lPositions)
                {

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

                        if (tieRebar != null)
                        {
                            XYZ[] pts = { pHookOuter, pWrapOuter, pSpineOuter, pSpineInner, pWrapInner, pHookInner };
                            var boxMin = new XYZ(
                                pts.Min(p => p.X) - tieRadiusFt, pts.Min(p => p.Y) - tieRadiusFt, pts.Min(p => p.Z) - tieRadiusFt);
                            var boxMax = new XYZ(
                                pts.Max(p => p.X) + tieRadiusFt, pts.Max(p => p.Y) + tieRadiusFt, pts.Max(p => p.Z) + tieRadiusFt);
                            madeTies.Add(new TieRecord { Id = tieRebar.Id, Min = boxMin, Max = boxMax });
                        }
                    }
                    catch (Exception exInner)
                    {
                        report.Add($"{h.Id} mặt {fd.Name} tại cross={RebarCommon.FtToMm(crossPos):F0}mm, l={RebarCommon.FtToMm(l):F0}mm: lỗi tạo đai C: {exInner.Message}");
                    }
                }

                return madeTies;
            }
            catch (Exception ex)
            {
                report.Add($"{h.Id} mặt {fd.Name} tại cross={RebarCommon.FtToMm(crossPos):F0}mm: lỗi tạo đai C: {ex.Message}");
                return madeTies;
            }
        }

        // Sau khi TAT CA dai C cua 1 host (ca 4 mat) da duoc tao, quet tung CAP dai
        // trong danh sach, dung bounding-box TU TINH SAN luc tao (Min/Max trong
        // TieRecord - KHONG doc lai tu Revit bang element.get_BoundingBox(null), vi
        // ham do tra ve null/sai cho element MOI TAO trong cung 1 Transaction chua
        // Regenerate) de phat hien 2 dai giao/trung nhau vat ly - thuong xay ra tai
        // hang giap goc, noi dai cua 2 mat ke nhau cung ram vao chum thep doc goc.
        // Cap nao giao nhau thi XOA CA HAI (khong giu lai thanh nao), dung y muon
        // "dai C ma trung nhau thi bo ca 2" thay vi co gang chon giu 1 trong 2.
        public static int RemoveOverlappingTies(Document doc, List<TieRecord> ties, List<string> report, ElementId hostId)
        {
            var toDelete = new HashSet<ElementId>();
            for (int i = 0; i < ties.Count; i++)
            {
                for (int j = i + 1; j < ties.Count; j++)
                {
                    if (BoundingBoxesOverlap(ties[i].Min, ties[i].Max, ties[j].Min, ties[j].Max))
                    {
                        toDelete.Add(ties[i].Id);
                        toDelete.Add(ties[j].Id);
                    }
                }
            }

            if (toDelete.Count > 0)
            {
                doc.Delete(toDelete);
                report.Add($"{hostId}: đã bỏ {toDelete.Count} đai C do bị trùng/giao nhau với đai C khác (thường tại các hàng giáp góc).");
            }

            return ties.Count - toDelete.Count;
        }

        // 2 bounding-box (khong gian model, truc X/Y/Z toan cuc) duoc coi la GIAO nhau
        // khi chung THAT SU chong lan tren CA 3 truc (dung bat dang thuc chat, khong
        // dung "<=" de 2 box chi cham nhau tai 1 mat/canh khong bi tinh nham la giao).
        private static bool BoundingBoxesOverlap(XYZ aMin, XYZ aMax, XYZ bMin, XYZ bMax)
        {
            return aMin.X < bMax.X && aMax.X > bMin.X
                && aMin.Y < bMax.Y && aMax.Y > bMin.Y
                && aMin.Z < bMax.Z && aMax.Z > bMin.Z;
        }
    }
}