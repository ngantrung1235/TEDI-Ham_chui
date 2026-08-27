using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Selection;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Dinh nghia 1 trong 4 mat cua host (Day/Nap/Trai/Phai) sau khi da tru lop
    // bao ve (cover): OuterPos/InnerPos la vi tri lop Ngoai/Trong doc theo truc
    // vuong goc mat (Zv cho Day/Nap, Wv cho Trai/Phai); CrossMin/CrossMax la
    // pham vi con lai theo truc song song mat do.
    public struct FaceDef
    {
        public string Name;
        public bool IsSlab;
        public double OuterPos;
        public double InnerPos;
        public double CrossMin;
        public double CrossMax;
    }

    // Ket qua Giai doan 1 (pick + suy truc) cho 1 host, dung chung cho ca 4 lenh
    // tao thep (thep doc, Rebar 0, thep single lop Trong, thep cheo goc vat).
    public class PreparedHost
    {
        public ElementId Id;
        public FamilyInstance Inst;
        public Solid Solid;
        public XYZ Lv, Wv, Zv;
        public List<double> WOff;
        public List<double> ZOff;
        public double LMinRaw, LMaxRaw;
        public Func<double, double, double, XYZ> L2G;
        public FaceDef[] FacesDef;
    }

    // ====================================================================
    // Ham/du lieu DUNG CHUNG cho toan bo cac lenh tao thep ham chui. Truoc day
    // gop chung trong 1 lenh "Tao thep" duy nhat; nay tach thanh nhieu nut rieng
    // (moi nut = 1 loai thep) nhung van dung chung buoc pick 3 mat + suy
    // Lv/Wv/Zv + do offset W/Z, de tranh lap code va dam bao cac loai thep khop
    // he toa do voi nhau khi chay tren cung 1 cau kien.
    // ====================================================================
    public static class RebarCommon
    {
        public const double DefaultCoverMm = 50.0;
        public const double DefaultTieDiamMm = 8.0;
        public const double DefaultTieSpaceMm = 200.0;

        // Lop bao ve DUNG CHUNG cho moi thanh thep nam trong "long ho thep" o Outer/InnerPos
        // cua FaceDef (thep doc RebarLongitudinalCommand/RebarStirrupCCommand, thep single lop
        // Trong RebarInnerSingleCommand, thep cheo goc vat RebarChamferCommand...) - TRU Rebar 0
        // (RebarOuterShapeCommand), vi Rebar 0 la lop THEP NGOAI CUNG tai Nap/Day nen no la
        // MOC THAM CHIEU (dung dung DefaultCoverMm) chu khong dung cong thuc nay.
        // = DefaultCoverMm (lop bao ve be tong that su, cung la cover cua Rebar 0) CONG THEM
        // TRON duong kinh Rebar 0 (RebarOuterShapeCommand.DefaultDiamMm) - vi cac thanh thep khac
        // deu nam PHIA TRONG Rebar 0 nen phai lui vao qua HET be day thanh Rebar 0 (khong phai chi
        // nua duong kinh) de khong dam/de len no.
        // CHI SUA O DAY khi doi cong thuc lop bao ve - moi noi khac PHAI goi lai property nay,
        // KHONG tu tinh rieng tu DefaultCoverMm, de tat ca cac nut tao thep luon dong bo voi nhau.
        public static double LongitudinalCoverMm => DefaultCoverMm + RebarOuterShapeCommand.DefaultDiamMm;

        public static double MmToFt(double mm) => UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters);
        public static double FtToMm(double ft) => UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Millimeters);

        public static Solid GetSolid(FamilyInstance inst)
        {
            var opt = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };
            foreach (GeometryObject go in inst.get_Geometry(opt))
                if (go is Solid s && s.Volume > 0) return s;
            return null;
        }

        // ====================================================================
        // SUY TRUC L/W/Z BANG CACH PICK TRUC TIEP 3 MAT TREN CHINH HOST -
        // thay cho cach cu (Adaptive Placement Points + doc tham so "Radius" tu
        // 1 instance KHAC ten trong ban ve, rat gion vi phu thuoc ca adaptive
        // component lan 1 element dat ten dung quy uoc o noi khac).
        //
        //   - "Mat bang"  (day/nap, nam ngang) -> chi dung de canh bao neu cau
        //     kien khong thuc su nam ngang. Z luon lay la XYZ.BasisZ (dung
        //     tuyet doi) vi ban ve quy uoc H do theo phuong dung.
        //   - "Mat dung"  (tuong trai/phai)     -> Wv = phap tuyen mat nay
        //     (ep ve mat phang ngang, phong truong hop tuong hoi nghieng).
        //   - "Mat canh"  (dau dot, vuong goc
        //     phuong doc)                       -> Lv = phap tuyen mat nay.
        //     Vi Lv lay TRUC TIEP tu mat canh nen no VUONG GOC CHINH XAC voi
        //     mat canh do -> KHONG can he so bu cos(radius) cho lop bao ve
        //     doc truc L nua (khac voi ban truoc), chi can dung thang coverFt.
        //
        // Co doi chieu cheo: goc lech giua Lv (tu mat canh) va huong vuong goc
        // that cua tuong (Zv x Wv) duoc canh bao neu > 3 do (vd dau dot bi cat
        // xien/khong vuong goc tuong that su) de nguoi dung tu kiem tra lai.
        // ====================================================================

        public static PlanarFace PickPlanarFaceOn(UIDocument uidoc, Document d, Element hostElem, string prompt)
        {
            Reference r = uidoc.Selection.PickObject(ObjectType.Face, prompt);
            GeometryObject go = hostElem.GetGeometryObjectFromReference(r)
                                 ?? d.GetElement(r)?.GetGeometryObjectFromReference(r);
            if (go is PlanarFace pf) return pf;
            throw new InvalidOperationException("Mặt vừa chọn không phải là mặt phẳng (PlanarFace). Chạy lại lệnh và chọn đúng mặt phẳng.");
        }

        public static (XYZ Lv, XYZ Wv, XYZ Zv) DeriveAxesFromPickedFaces(PlanarFace planFace, PlanarFace elevFace, PlanarFace sideFace)
        {
            XYZ Zv = XYZ.BasisZ;

            var planN = planFace.FaceNormal.Normalize();
            double tiltDeg = Math.Acos(Math.Min(1.0, Math.Abs(planN.Z))) * 180.0 / Math.PI;
            if (tiltDeg > 2.0)
                TaskDialog.Show("Cảnh báo",
                    $"Mặt bằng đã chọn lệch {tiltDeg:F1}° so với phương ngang tuyệt đối.\n" +
                    "Code vẫn dùng trục đứng Z = XYZ.BasisZ (thẳng tuyệt đối) - kiểm tra lại nếu cấu kiện có độ dốc dọc thật sự.");

            var Wv3 = elevFace.FaceNormal.Normalize();
            var Wv = new XYZ(Wv3.X, Wv3.Y, 0);
            if (Wv.GetLength() < 1e-6)
                throw new InvalidOperationException("Mặt đứng đã chọn có pháp tuyến gần như thẳng đứng - có thể chọn nhầm mặt bằng/mặt đứng.");
            Wv = Wv.Normalize();

            var LvSide3 = sideFace.FaceNormal.Normalize();
            var LvSide = new XYZ(LvSide3.X, LvSide3.Y, 0);
            if (LvSide.GetLength() < 1e-6)
                throw new InvalidOperationException("Mặt cạnh đã chọn có pháp tuyến gần như thẳng đứng - có thể chọn nhầm mặt.");
            LvSide = LvSide.Normalize();

            var LvCross = Zv.CrossProduct(Wv).Normalize();
            if (LvSide.DotProduct(LvCross) < 0) LvSide = -LvSide;

            double angDeg = LvSide.AngleTo(LvCross) * 180.0 / Math.PI;
            if (angDeg > 3.0)
                TaskDialog.Show("Cảnh báo",
                    $"Trục dọc suy từ MẶT CẠNH lệch {angDeg:F1}° so với trục vuông góc thật của MẶT ĐỨNG.\n" +
                    "Có thể đầu đốt bị cắt xiên (không vuông góc tường), hoặc chọn nhầm mặt.\n" +
                    "Vẫn tiếp tục dùng trục dọc lấy từ MẶT CẠNH.");

            return (LvSide, Wv, Zv);
        }

        // Tinh normal AN TOAN cho 1 thanh thep tu chinh 2 diem dau/cuoi cua no (khong
        // dung Lv/Wv tinh san) -> luon vuong goc TUYET DOI voi huong thanh thep that,
        // bat ke Lv (tu mat canh) va Wv (tu mat dung) co vuong goc voi nhau hay khong.
        public static XYZ SafeNormalFor(XYZ p1, XYZ p2, XYZ Zv, XYZ fallbackHorizontal)
        {
            var dir = (p2 - p1).Normalize();
            var n = Zv.CrossProduct(dir);
            if (n.GetLength() < 1e-6) // thanh gan nhu thang dung (song song Zv) -> Zv x dir suy bien
                return fallbackHorizontal.Normalize(); // bat ky vector ngang nao cung vuong goc voi Zv
            return n.Normalize();
        }

        public static List<double> GetOffsetsFiltered(Solid sld, XYZ axis)
        {
            var groups = new List<(double offset, double area)>();
            foreach (Face f in sld.Faces)
                if (f is PlanarFace pf)
                {
                    double dot = pf.FaceNormal.Normalize().DotProduct(axis);
                    if (Math.Abs(Math.Abs(dot) - 1.0) < 0.02 && pf.Area > 0.05)
                    {
                        double o = pf.Origin.DotProduct(axis);
                        double tolFt = MmToFt(5);
                        int idx = groups.FindIndex(g => Math.Abs(g.offset - o) < tolFt);
                        if (idx >= 0) groups[idx] = (groups[idx].offset, groups[idx].area + pf.Area);
                        else groups.Add((o, pf.Area));
                    }
                }
            if (groups.Count == 0) return new List<double>();
            double maxArea = groups.Max(g => g.area);
            return groups.Where(g => g.area >= 0.3 * maxArea).OrderBy(g => g.offset).Select(g => g.offset).ToList();
        }

        // Do 1 duong thang doc L tai 1 vi tri cross cu the, giao voi solid THAT -> tra ve
        // khoang L nam BEN TRONG solid tai dung vi tri do (ngan hon o gan goc vat).
        public static (double lo, double hi)? ProbeSolidLRange(Solid solid, XYZ p1, XYZ p2, XYZ Lv)
        {
            if (p1.DistanceTo(p2) < MmToFt(1)) return null;
            var probeCurve = Line.CreateBound(p1, p2);
            var sco = new SolidCurveIntersectionOptions { ResultType = SolidCurveIntersectionMode.CurveSegmentsInside };
            SolidCurveIntersection sci;
            try { sci = solid.IntersectWithCurve(probeCurve, sco); } catch { return null; }
            if (sci == null || sci.SegmentCount == 0) return null;
            double lo = double.MaxValue, hi = double.MinValue;
            for (int i = 0; i < sci.SegmentCount; i++)
            {
                var seg = sci.GetCurveSegment(i);
                double a = seg.GetEndPoint(0).DotProduct(Lv);
                double b = seg.GetEndPoint(1).DotProduct(Lv);
                lo = Math.Min(lo, Math.Min(a, b));
                hi = Math.Max(hi, Math.Max(a, b));
            }
            return (lo, hi);
        }

        // Tao 1 thanh DON LE (khong array) chay tu p1->p2.
        public static ElementId CreateSingleBar(
            Document d, RebarBarType bt, Element host,
            XYZ p1, XYZ p2, XYZ normal)
        {
            var curve = Line.CreateBound(p1, p2);
            var terminations = new BarTerminationsData(d);
            var rebar = Rebar.CreateFromCurves(
                d, RebarStyle.Standard, bt, host, normal,
                new List<Curve> { curve }, terminations,
                useExistingShapeIfPossible: false, createNewShape: true);
            if (rebar == null)
                throw new InvalidOperationException($"CreateFromCurves (single) tra ve null. p1={p1} p2={p2}");

            var accessor = rebar.GetShapeDrivenAccessor();
            accessor.SetLayoutAsSingle();
            return rebar.Id;
        }

        // Tim (hoac tao moi neu chua co) 1 RebarBarType theo ten + duong kinh (mm).
        public static RebarBarType GetOrCreateBarType(Document doc, string name, double diamMm, List<string> report)
        {
            var barType = new FilteredElementCollector(doc)
                .OfClass(typeof(RebarBarType))
                .Cast<RebarBarType>()
                .FirstOrDefault(x => x.Name == name);
            if (barType == null)
            {
                var newId = RebarBarType.CreateDefaultRebarBarType(doc);
                barType = doc.GetElement(newId) as RebarBarType;
                barType.Name = name;
                barType.BarModelDiameter = MmToFt(diamMm);
                barType.BarNominalDiameter = MmToFt(diamMm);
                report.Add($"Đã tạo mới RebarBarType '{name}' ({diamMm:F0}mm).");
            }
            return barType;
        }

        // =====================================================================
        // GIAI DOAN 1 - PICK: lam TRUOC khi mo Transaction (dung thong le Revit -
        // khong pick trong luc dang co transaction dang mo). Voi MOI cau kien da
        // chon, yeu cau pick 3 mat (mat bang / mat dung / mat canh) de suy Lv/Wv/Zv
        // truc tiep tu hinh hoc that, roi do offset W/Z va dung san facesDef/L2G.
        // Dung chung cho ca 4 lenh tao thep.
        // =====================================================================
        public static List<PreparedHost> PickAndPrepareHosts(
            UIDocument uidoc, Document doc, ICollection<ElementId> selectedIds,
            double coverFt, List<string> report)
        {
            var result = new List<PreparedHost>();

            foreach (var id in selectedIds)
            {
                var inst = doc.GetElement(id) as FamilyInstance;
                if (inst == null) { report.Add($"{id}: không phải FamilyInstance."); continue; }

                var solid = GetSolid(inst);
                if (solid == null) { report.Add($"{id}: không tìm thấy solid."); continue; }

                var planFace = PickPlanarFaceOn(uidoc, doc, inst, $"[{id}] 1/3 - Chọn MẶT BẰNG (đáy hoặc nắp - mặt nằm ngang)");
                var elevFace = PickPlanarFaceOn(uidoc, doc, inst, $"[{id}] 2/3 - Chọn MẶT ĐỨNG (tường trái hoặc phải)");
                var sideFace = PickPlanarFaceOn(uidoc, doc, inst, $"[{id}] 3/3 - Chọn MẶT CẠNH (đầu đốt, vuông góc phương dọc)");

                var (Lv, Wv, Zv) = DeriveAxesFromPickedFaces(planFace, elevFace, sideFace);

                double detA = Lv.X * Wv.Y - Lv.Y * Wv.X;
                XYZ L2G(double l, double w, double z)
                {
                    double px = (l * Wv.Y - w * Lv.Y) / detA;
                    double py = (Lv.X * w - Wv.X * l) / detA;
                    return new XYZ(px, py, z);
                }

                // pham vi L THO (rong, chi dung lam bien tren de do - se bi thu hep lai sau)
                double lMinRaw = double.MaxValue, lMaxRaw = double.MinValue;
                foreach (Edge e in solid.Edges)
                {
                    var c = e.AsCurve();
                    foreach (var pt in new[] { c.GetEndPoint(0), c.GetEndPoint(1) })
                    {
                        double v = pt.DotProduct(Lv);
                        if (v < lMinRaw) lMinRaw = v;
                        if (v > lMaxRaw) lMaxRaw = v;
                    }
                }

                var wOff = GetOffsetsFiltered(solid, Wv);
                var zOff = GetOffsetsFiltered(solid, Zv);
                if (wOff.Count != 4 || zOff.Count != 4)
                {
                    report.Add($"{id}: SỐ LƯỢNG OFFSET BẤT THƯỜNG (W={wOff.Count}, Z={zOff.Count}) - bỏ qua.");
                    continue;
                }

                // CrossMin/CrossMax (hang dau/cuoi duoc phep cach mep bao nhieu doc theo mat) PHAI
                // dung CUNG coverFt (co the la LongitudinalCoverMm, da cong them duong kinh Rebar 0)
                // NHU OuterPos/InnerPos, KHONG duoc dung cover tron rieng: Rebar 0 (Nap/Day) nam tai
                // dung mat phang Z = zOff[3]-DefaultCoverMm (Nap) hoac zOff[0]+DefaultCoverMm (Day) -
                // day CHINH LA gia tri CrossMax/CrossMin cua Trai/Phai neu dung cover tron (vi Trai/
                // Phai lay CrossMin/CrossMax tu chinh zOff[0]/zOff[3] do). Neu Trai/Phai dung cover
                // tron cho CrossMin/CrossMax, hang dau/cuoi cua chung se ROI DUNG VAO mat phang Z ma
                // dai C/thep dọc cua Rebar 0 chiem - trung khop hoan toan thay vi tranh nhau. Tuong
                // tu, hang dau/cuoi cua Nap/Day (CrossMin/CrossMax theo Wv) cung phai tranh dung mat
                // phang W ma chan Rebar 0 (leg) chiem tai Trai/Phai. Vi vay CA 4 mat deu phai dung
                // coverFt (LongitudinalCoverMm) cho CrossMin/CrossMax, giong het OuterPos/InnerPos.
                var facesDef = new[]
                {
                    new FaceDef { Name = "Day",  IsSlab = true,  OuterPos = zOff[0]+coverFt, InnerPos = zOff[1]-coverFt, CrossMin = wOff[0]+coverFt, CrossMax = wOff[3]-coverFt },
                    new FaceDef { Name = "Nap",  IsSlab = true,  OuterPos = zOff[3]-coverFt, InnerPos = zOff[2]+coverFt, CrossMin = wOff[0]+coverFt, CrossMax = wOff[3]-coverFt },
                    new FaceDef { Name = "Trai", IsSlab = false, OuterPos = wOff[0]+coverFt, InnerPos = wOff[1]-coverFt, CrossMin = zOff[0]+coverFt, CrossMax = zOff[3]-coverFt },
                    new FaceDef { Name = "Phai", IsSlab = false, OuterPos = wOff[3]-coverFt, InnerPos = wOff[2]+coverFt, CrossMin = zOff[0]+coverFt, CrossMax = zOff[3]-coverFt },
                };

                result.Add(new PreparedHost
                {
                    Id = id,
                    Inst = inst,
                    Solid = solid,
                    Lv = Lv,
                    Wv = Wv,
                    Zv = Zv,
                    WOff = wOff,
                    ZOff = zOff,
                    LMinRaw = lMinRaw,
                    LMaxRaw = lMaxRaw,
                    L2G = L2G,
                    FacesDef = facesDef,
                });
            }

            return result;
        }
    }
}
