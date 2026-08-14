using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Selection;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    [Transaction(TransactionMode.Manual)]
    public class RebarByHostSelectionCommand : IExternalCommand
    {
        double MmToFt(double mm) => UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters);
        double FtToMm(double ft) => UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Millimeters);

        Solid GetSolid(FamilyInstance inst)
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

        PlanarFace PickPlanarFaceOn(UIDocument uidoc, Document d, Element hostElem, string prompt)
        {
            Reference r = uidoc.Selection.PickObject(ObjectType.Face, prompt);
            GeometryObject go = hostElem.GetGeometryObjectFromReference(r)
                                 ?? d.GetElement(r)?.GetGeometryObjectFromReference(r);
            if (go is PlanarFace pf) return pf;
            throw new InvalidOperationException("Mặt vừa chọn không phải là mặt phẳng (PlanarFace). Chạy lại lệnh và chọn đúng mặt phẳng.");
        }

        (XYZ Lv, XYZ Wv, XYZ Zv) DeriveAxesFromPickedFaces(PlanarFace planFace, PlanarFace elevFace, PlanarFace sideFace)
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
        // Neu Lv/Wv KHONG vuong goc chinh xac (rat de xay ra vi day la 2 mat pick RIENG
        // BIET, khac voi cach suy truc tu dong bang tich co huong truoc day), normal tinh
        // san tu Lv/Wv co the sai lech du nho van khien Rebar.CreateFromCurves am tham
        // tra ve null (khong throw) thay vi bao loi ro rang.
        XYZ SafeNormalFor(XYZ p1, XYZ p2, XYZ Zv, XYZ fallbackHorizontal)
        {
            var dir = (p2 - p1).Normalize();
            var n = Zv.CrossProduct(dir);
            if (n.GetLength() < 1e-6) // thanh gan nhu thang dung (song song Zv) -> Zv x dir suy bien
                return fallbackHorizontal.Normalize(); // bat ky vector ngang nao cung vuong goc voi Zv
            return n.Normalize();
        }

        List<double> GetOffsetsFiltered(Solid sld, XYZ axis)
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
        (double lo, double hi)? ProbeSolidLRange(Solid solid, XYZ p1, XYZ p2, XYZ Lv)
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
        ElementId CreateSingleBar(
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

                double coverFt = MmToFt(50);
                double diamFt = MmToFt(20);
                double spaceFt = MmToFt(200);

                var report = new List<string>();
                int totalCount = 0;

                // =====================================================================
                // GIAI DOAN 1 - PICK: lam TRUOC khi mo Transaction (dung thong le Revit -
                // khong pick trong luc dang co transaction dang mo). Voi MOI cau kien da
                // chon, yeu cau pick 3 mat (mat bang / mat dung / mat canh) de suy Lv/Wv/Zv
                // truc tiep tu hinh hoc that, khong con phu thuoc Adaptive Component hay
                // tham so o element khac.
                // =====================================================================
                var prepared = new List<(ElementId id, FamilyInstance inst, Solid solid, XYZ Lv, XYZ Wv, XYZ Zv)>();

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
                    prepared.Add((id, inst, solid, Lv, Wv, Zv));
                }

                if (prepared.Count == 0)
                {
                    message = "Không có cấu kiện hợp lệ nào để tạo thép sau bước pick.";
                    return Result.Failed;
                }

                // =====================================================================
                // GIAI DOAN 2 - TAO THEP: mo 1 Transaction duy nhat, dung Lv/Wv/Zv da
                // pick o Giai doan 1 cho tung cau kien.
                // =====================================================================
                using (Transaction t = new Transaction(doc, "Tạo lưới thép hầm chui"))
                {
                    t.Start();

                    var barType = new FilteredElementCollector(doc)
                        .OfClass(typeof(RebarBarType))
                        .Cast<RebarBarType>()
                        .FirstOrDefault(x => x.Name == "D20");
                    if (barType == null)
                    {
                        var newId = RebarBarType.CreateDefaultRebarBarType(doc);
                        barType = doc.GetElement(newId) as RebarBarType;
                        barType.Name = "D20";
                        barType.BarModelDiameter = diamFt;
                        barType.BarNominalDiameter = diamFt;
                        report.Add("Đã tạo mới RebarBarType 'D20' (20mm).");
                    }

                    foreach (var (id, inst, solid, Lv, Wv, Zv) in prepared)
                    {
                        double detA = Lv.X * Wv.Y - Lv.Y * Wv.X;
                        XYZ L2G(double l, double w, double z)
                        {
                            double px = (l * Wv.Y - w * Lv.Y) / detA;
                            double py = (Lv.X * w - Wv.X * l) / detA;
                            return new XYZ(px, py, z);
                        }

                        // Lv lay TRUC TIEP tu phap tuyen mat canh da pick -> vuong goc CHINH XAC
                        // voi mat canh do -> khong con can he so bu cos(radius) cho lop bao ve
                        // doc truc L nhu ban truoc, dung thang coverFt.

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

                        var facesDef = new (string name, bool isSlab, double outerPos, double innerPos, double crossMin, double crossMax)[]
                        {
                            ("Day",  true,  zOff[0]+coverFt, zOff[1]-coverFt, wOff[0]+coverFt, wOff[3]-coverFt),
                            ("Nap",  true,  zOff[3]-coverFt, zOff[2]+coverFt, wOff[0]+coverFt, wOff[3]-coverFt),
                            ("Trai", false, wOff[0]+coverFt, wOff[1]-coverFt, zOff[0]+coverFt, zOff[3]-coverFt),
                            ("Phai", false, wOff[3]-coverFt, wOff[2]+coverFt, zOff[0]+coverFt, zOff[3]-coverFt),
                        };

                        int instCount = 0;
                        foreach (var fd in facesDef)
                        {
                            var layers = new[] { ("Ngoai", fd.outerPos, fd.innerPos), ("Trong", fd.innerPos, fd.outerPos) };
                            foreach (var (layerName, pos, otherPos) in layers)
                            {
                                // ---- BO 1: chay DOC L - TUNG THANH RIENG, tu bam bien that ----
                                // Moi thanh o vi tri cross khac nhau se co CHIEU DAI KHAC NHAU
                                // (thanh gan goc vat thi ngan hon) -> tao hinh bac thang bam sat
                                // duong cheo that cua hop hinh binh hanh.
                                double crossLen = fd.crossMax - fd.crossMin;
                                int nRows = (int)Math.Ceiling(crossLen / spaceFt) + 1;
                                if (nRows < 2) nRows = 2;
                                double rowSpacing = crossLen / (nRows - 1);

                                int rowsMade = 0;
                                for (int i = 0; i < nRows; i++)
                                {
                                    double crossPos = fd.crossMin + i * rowSpacing;
                                    XYZ probeA = fd.isSlab ? L2G(lMinRaw, crossPos, pos) : L2G(lMinRaw, pos, crossPos);
                                    XYZ probeB = fd.isSlab ? L2G(lMaxRaw, crossPos, pos) : L2G(lMaxRaw, pos, crossPos);
                                    var range = ProbeSolidLRange(solid, probeA, probeB, Lv);
                                    if (range == null) continue;
                                    double rowLo = range.Value.lo + coverFt;
                                    double rowHi = range.Value.hi - coverFt;
                                    if (rowHi - rowLo < MmToFt(20)) continue;

                                    XYZ b1 = fd.isSlab ? L2G(rowLo, crossPos, pos) : L2G(rowLo, pos, crossPos);
                                    XYZ b2 = fd.isSlab ? L2G(rowHi, crossPos, pos) : L2G(rowHi, pos, crossPos);

                                    // Bố 1: Thép chạy dọc theo trục Lv. Normal tính TRỰC TIẾP từ
                                    // huong that cua thanh (b1->b2) - luon vuong goc tuyet doi,
                                    // khong phu thuoc Lv/Wv co vuong goc voi nhau hay khong.
                                    XYZ normal1 = SafeNormalFor(b1, b2, Zv, Wv);
                                    CreateSingleBar(doc, barType, inst, b1, b2, normal1);
                                    rowsMade++;
                                }
                                instCount += rowsMade;

                                // ---- BO 2: chay NGANG (cross), dan deu doc L ----
                                // Chuyển sang dùng Single Bar thay vì Rebar Set để tránh lỗi
                                // mảng chữ nhật bị lòi ra ngoài bản đáy hình bình hành.
                                double dirSign = Math.Sign(otherPos - pos);
                                double posNudged = pos + dirSign * diamFt;

                                double loSafe = lMinRaw + coverFt;
                                double hiSafe = lMaxRaw - coverFt;
                                double lLen = hiSafe - loSafe;
                                int nRows2 = (int)Math.Ceiling(lLen / spaceFt) + 1;
                                if (nRows2 < 2) nRows2 = 2;
                                double rowSpacing2 = lLen / (nRows2 - 1);

                                int rowsMade2 = 0;
                                for (int i = 0; i < nRows2; i++)
                                {
                                    double lPos = loSafe + i * rowSpacing2;
                                    XYZ p2s = fd.isSlab ? L2G(lPos, fd.crossMin, posNudged) : L2G(lPos, posNudged, fd.crossMin);
                                    XYZ p2e = fd.isSlab ? L2G(lPos, fd.crossMax, posNudged) : L2G(lPos, posNudged, fd.crossMax);

                                    // Bố 2: Thép chạy theo trục Wv (Slab) hoặc Zv (Wall). Normal
                                    // tính TRỰC TIẾP từ huong that cua thanh (p2s->p2e); truong hop
                                    // thanh dung (tuong) thi Zv x dir suy bien -> fallback dung Lv
                                    // (luon vuong goc voi phuong dung).
                                    XYZ normal2 = SafeNormalFor(p2s, p2e, Zv, Lv);
                                    CreateSingleBar(doc, barType, inst, p2s, p2e, normal2);
                                    rowsMade2++;
                                }
                                instCount += rowsMade2;
                            }
                        }
                        report.Add($"{id}: đã tạo {instCount} thanh/Set (4 mặt x 2 lớp).");
                        totalCount += instCount;
                    }

                    t.Commit();
                    TaskDialog.Show("Thành công",
                        $"Đã tạo tổng cộng {totalCount} thanh/Set.\n\nChi tiết:\n" + string.Join("\n", report));
                    return Result.Succeeded;
                }
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                // Nguoi dung nhan ESC trong luc pick mat - huy lenh, khong bao loi.
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