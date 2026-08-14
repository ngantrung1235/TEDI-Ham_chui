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
    [Regeneration(RegenerationOption.Manual)]
    public class RebarT13Command : IExternalCommand
    {
        double MmToFt(double mm) => UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters);
        double FtToMm(double ft) => UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Millimeters);

        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIApplication uiapp = commandData.Application;
            UIDocument uidoc = uiapp.ActiveUIDocument;
            Document doc = uidoc.Document;

            if (doc == null)
            {
                message = "Không tìm thấy Active Document.";
                return Result.Failed;
            }

            try
            {
                // =========================================================================
                // BƯỚC 1: NGƯỜI DÙNG CHỌN CÁC ĐỐI TƯỢNG ĐẦU VÀO (TƯƠNG ĐƯƠNG DYNAMO INPUTS)
                // =========================================================================

                // 1.1. Chọn Host (cấu kiện bê tông)
                Reference hostRef = uidoc.Selection.PickObject(ObjectType.Element, "1/6. Chọn Host cấu kiện bê tông (Trụ / Hầm / Mố)");
                Element hostElem = doc.GetElement(hostRef);
                if (hostElem == null) return Result.Cancelled;

                // 1.2. Chọn các mặt cong
                IList<Reference> faceRefs = uidoc.Selection.PickObjects(ObjectType.Face, "2/6. Chọn các mặt cong bố trí thép (Nhấn Finish khi chọn xong)");
                if (faceRefs == null || faceRefs.Count == 0) return Result.Cancelled;

                // 1.3. Chọn cạnh theo phương ngang cầu lấy vector rải
                Reference edgeRef = uidoc.Selection.PickObject(ObjectType.Edge, "3/6. Chọn cạnh theo phương ngang cầu để xác định vector rải");
                GeometryObject edgeGeom = hostElem.GetGeometryObjectFromReference(edgeRef) ?? doc.GetElement(edgeRef).GetGeometryObjectFromReference(edgeRef);
                Edge edge = edgeGeom as Edge;
                if (edge == null)
                {
                    TaskDialog.Show("Lỗi", "Không lấy được hình học cạnh đã chọn.");
                    return Result.Failed;
                }
                Curve edgeCurve = edge.AsCurve();
                XYZ pStartEdge = edgeCurve.GetEndPoint(0);
                XYZ pEndEdge = edgeCurve.GetEndPoint(1);
                // Vector rải theo Dynamo: Vector.ByTwoPoints(start=EndPoint, end=StartPoint) -> (StartPoint - EndPoint)
                XYZ dirV = (pStartEdge - pEndEdge).Normalize();

                // 1.4. Chọn Ref.Plane tạo thanh thép ban đầu
                Reference planeStartRef = uidoc.Selection.PickObject(ObjectType.Element, "4/6. Chọn Ref.Plane định vị mặt cắt tạo thép ban đầu");
                ReferencePlane refPlaneStart = doc.GetElement(planeStartRef) as ReferencePlane;
                if (refPlaneStart == null)
                {
                    TaskDialog.Show("Lỗi", "Đối tượng chọn không phải là ReferencePlane.");
                    return Result.Failed;
                }

                // 1.5. Chọn Ref.Plane Đỉnh trụ
                Reference planeTopRef = uidoc.Selection.PickObject(ObjectType.Element, "5/6. Chọn Ref.Plane Đỉnh trụ (để cắt 2 râu thép đứng)");
                ReferencePlane refPlaneTop = doc.GetElement(planeTopRef) as ReferencePlane;
                if (refPlaneTop == null)
                {
                    TaskDialog.Show("Lỗi", "Đối tượng chọn không phải là ReferencePlane.");
                    return Result.Failed;
                }

                // 1.6. Chọn Ref.Plane Mirror (tùy chọn, có thể nhấn ESC nếu không mirror)
                ReferencePlane refPlaneMirror = null;
                try
                {
                    Reference planeMirrorRef = uidoc.Selection.PickObject(ObjectType.Element, "6/6. Chọn Ref.Plane Mirror đối xứng (Hoặc nhấn ESC để bỏ qua Mirror)");
                    refPlaneMirror = doc.GetElement(planeMirrorRef) as ReferencePlane;
                }
                catch (Autodesk.Revit.Exceptions.OperationCanceledException)
                {
                    // Người dùng không muốn mirror
                    refPlaneMirror = null;
                }

                // =========================================================================
                // BƯỚC 2: TÌM HOẶC TẠO LOẠI THÉP T13
                // =========================================================================
                double diamFt = MmToFt(13); // T13 = 13mm
                double coverOffsetFt = MmToFt(-81); // Dynamo Offset -81mm

                RebarBarType barType = new FilteredElementCollector(doc)
                    .OfClass(typeof(RebarBarType))
                    .Cast<RebarBarType>()
                    .FirstOrDefault(x => x.Name.Equals("T13", StringComparison.OrdinalIgnoreCase)
                                      || x.Name.Equals("D13", StringComparison.OrdinalIgnoreCase)
                                      || x.Name.Contains("13")
                                      || x.Name.Contains("16"));

                using (Transaction trans = new Transaction(doc, "Tạo cốt thép Rebar T13 theo mặt cong"))
                {
                    trans.Start();

                    if (barType == null)
                    {
                        var newId = RebarBarType.CreateDefaultRebarBarType(doc);
                        barType = doc.GetElement(newId) as RebarBarType;
                        barType.Name = "T13";
                        barType.BarModelDiameter = diamFt;
                        barType.BarNominalDiameter = diamFt;
                    }

                    // =========================================================================
                    // BƯỚC 3: TÍNH TOÁN CÁC MẶT PHẲNG CẮT DỌC THEO VECTOR V
                    // Dynamo: Sequence(start: 0, step: 150, amount: 58) và Reverse Range(0, 800, 150)
                    // =========================================================================
                    Plane basePlane = refPlaneStart.GetPlane();
                    XYZ planeOrigin = basePlane.Origin;
                    XYZ planeNormal = basePlane.Normal.Normalize();

                    double spacingFt = MmToFt(150);
                    int countMain = 58; // 58 thanh dải chính
                    List<double> distances = new List<double>();

                    // Dải chính: 0, 150, 300, ... (58 thanh)
                    for (int i = 0; i < countMain; i++)
                    {
                        distances.Add(i * spacingFt);
                    }

                    // Dải ngược từ thanh đầu tiên: 150, 300, 450, 600, 750 (6 thanh ngược lại)
                    double maxReverseFt = MmToFt(800);
                    for (double d = spacingFt; d <= maxReverseFt; d += spacingFt)
                    {
                        distances.Add(-d);
                    }

                    // Lấy danh sách các Face thực tế
                    List<Face> targetFaces = new List<Face>();
                    foreach (var fRef in faceRefs)
                    {
                        GeometryObject gObj = hostElem.GetGeometryObjectFromReference(fRef) ?? doc.GetElement(fRef).GetGeometryObjectFromReference(fRef);
                        if (gObj is Face f) targetFaces.Add(f);
                    }

                    if (targetFaces.Count == 0)
                    {
                        TaskDialog.Show("Lỗi", "Không tìm thấy hình học mặt cong từ các đối tượng đã chọn.");
                        trans.RollBack();
                        return Result.Failed;
                    }

                    // Plane đỉnh trụ
                    Plane topPlane = refPlaneTop.GetPlane();
                    XYZ topOrigin = topPlane.Origin;
                    XYZ topNormal = topPlane.Normal.Normalize();

                    List<ElementId> createdRebarIds = new List<ElementId>();

                    // =========================================================================
                    // BƯỚC 4: DUYỆT TỪNG MẶT PHẲNG CẮT, TÍNH GIAO TUYẾN & TẠO THANH REBAR
                    // =========================================================================
                    foreach (double dist in distances)
                    {
                        XYZ currentOrigin = planeOrigin + dist * dirV;

                        // Tìm các đoạn giao tuyến giữa mặt phẳng này và các targetFaces
                        List<XYZ> intersectPoints = IntersectFacesWithPlane(targetFaces, currentOrigin, planeNormal, coverOffsetFt);

                        if (intersectPoints.Count < 2) continue;

                        // Sắp xếp các điểm theo thứ tự liên tục dọc theo đường cong
                        List<XYZ> sortedPoints = SortPointsAlongCurve(intersectPoints, planeNormal);
                        if (sortedPoints.Count < 2) continue;

                        XYZ pStartCurve = sortedPoints.First();
                        XYZ pEndCurve = sortedPoints.Last();

                        // Tìm giao điểm kéo thẳng đứng lên theo trục Z với RefPlane Đỉnh trụ
                        XYZ? topStart = RayIntersectPlane(pStartCurve, XYZ.BasisZ, topOrigin, topNormal);
                        XYZ? topEnd = RayIntersectPlane(pEndCurve, XYZ.BasisZ, topOrigin, topNormal);

                        if (topStart == null || topEnd == null) continue;

                        // Lắp ráp danh sách điểm tạo Rebar: TopStart -> PStart -> ... -> PEnd -> TopEnd
                        List<XYZ> rebarPoints = new List<XYZ>();
                        rebarPoints.Add(topStart);
                        rebarPoints.AddRange(sortedPoints);
                        rebarPoints.Add(topEnd);

                        // Lọc các điểm quá gần nhau (< 2mm)
                        List<XYZ> cleanedPoints = new List<XYZ> { rebarPoints[0] };
                        for (int i = 1; i < rebarPoints.Count; i++)
                        {
                            if (rebarPoints[i].DistanceTo(cleanedPoints.Last()) > MmToFt(2))
                            {
                                cleanedPoints.Add(rebarPoints[i]);
                            }
                        }

                        if (cleanedPoints.Count < 2) continue;

                        // Tạo danh sách Curve từ các điểm
                        List<Curve> curves = new List<Curve>();
                        for (int i = 0; i < cleanedPoints.Count - 1; i++)
                        {
                            curves.Add(Line.CreateBound(cleanedPoints[i], cleanedPoints[i + 1]));
                        }

                        if (curves.Count == 0) continue;

                        // Vector pháp tuyến cho Rebar
                        XYZ rebarNormal = planeNormal;

                        var terminations = new BarTerminationsData(doc);
                        var rebar = Rebar.CreateFromCurves(
                            doc,
                            RebarStyle.Standard,
                            barType,
                            hostElem,
                            rebarNormal,
                            curves,
                            terminations,
                            useExistingShapeIfPossible: false,
                            createNewShape: true);

                        if (rebar != null)
                        {
                            var accessor = rebar.GetShapeDrivenAccessor();
                            accessor.SetLayoutAsSingle();

                            // Gán Comments = "T13" theo Dynamo
                            var commentParam = rebar.LookupParameter("Comments") ?? rebar.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS);
                            if (commentParam != null && !commentParam.IsReadOnly)
                            {
                                commentParam.Set("T13");
                            }

                            createdRebarIds.Add(rebar.Id);
                        }
                    }

                    // =========================================================================
                    // BƯỚC 5: MIRROR SANG PHÍA ĐỐI DIỆN NẾU CÓ CHỌN REF.PLANE MIRROR
                    // =========================================================================
                    int mirrorCount = 0;
                    if (refPlaneMirror != null && createdRebarIds.Count > 0)
                    {
                        Plane mirrorPlane = refPlaneMirror.GetPlane();
                        var mirroredIds = ElementTransformUtils.MirrorElements(doc, createdRebarIds, mirrorPlane, true);

                        if (mirroredIds != null && mirroredIds.Count > 0)
                        {
                            mirrorCount = mirroredIds.Count;
                            foreach (var mId in mirroredIds)
                            {
                                var mElem = doc.GetElement(mId);
                                if (mElem != null)
                                {
                                    var commentParam = mElem.LookupParameter("Comments") ?? mElem.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS);
                                    if (commentParam != null && !commentParam.IsReadOnly)
                                    {
                                        commentParam.Set("T13");
                                    }
                                }
                            }
                        }
                    }

                    trans.Commit();

                    TaskDialog.Show("Thành công",
                        $"Đã tạo thành công {createdRebarIds.Count} thanh thép Rebar T13." +
                        (mirrorCount > 0 ? $"\nĐã Mirror thêm {mirrorCount} thanh sang phía đối diện (Tổng: {createdRebarIds.Count + mirrorCount} thanh)." : ""));

                    return Result.Succeeded;
                }
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                return Result.Cancelled;
            }
            catch (Exception ex)
            {
                message = ex.ToString();
                return Result.Failed;
            }
        }

        /// <summary>
        /// Cắt các Face với mặt phẳng (Origin, Normal) và offset theo lớp bảo vệ
        /// </summary>
        private List<XYZ> IntersectFacesWithPlane(List<Face> faces, XYZ planeOrigin, XYZ planeNormal, double offsetFt)
        {
            List<XYZ> pts = new List<XYZ>();
            double tolFt = MmToFt(0.5);

            foreach (var face in faces)
            {
                Mesh mesh = face.Triangulate();
                if (mesh == null) continue;

                int numTriangles = mesh.NumTriangles;
                for (int i = 0; i < numTriangles; i++)
                {
                    MeshTriangle tri = mesh.get_Triangle(i);
                    XYZ v0 = tri.get_Vertex(0);
                    XYZ v1 = tri.get_Vertex(1);
                    XYZ v2 = tri.get_Vertex(2);

                    double d0 = (v0 - planeOrigin).DotProduct(planeNormal);
                    double d1 = (v1 - planeOrigin).DotProduct(planeNormal);
                    double d2 = (v2 - planeOrigin).DotProduct(planeNormal);

                    // Kiểm tra giao cắt cạnh v0-v1, v1-v2, v2-v0
                    var segPts = new List<XYZ>();
                    CheckEdgeIntersect(v0, v1, d0, d1, segPts);
                    CheckEdgeIntersect(v1, v2, d1, d2, segPts);
                    CheckEdgeIntersect(v2, v0, d2, d0, segPts);

                    foreach (var p in segPts)
                    {
                        // Project điểm lên Face để lấy pháp tuyến chính xác và offset
                        IntersectionResult ir = face.Project(p);
                        XYZ finalPt = p;
                        if (ir != null)
                        {
                            XYZ normalAtPt = face.ComputeNormal(ir.UVPoint).Normalize();
                            finalPt = ir.XYZPoint + offsetFt * normalAtPt;
                        }

                        // Tránh điểm trùng lặp
                        if (!pts.Any(existing => existing.DistanceTo(finalPt) < tolFt))
                        {
                            pts.Add(finalPt);
                        }
                    }
                }
            }

            return pts;
        }

        private void CheckEdgeIntersect(XYZ p0, XYZ p1, double d0, double d1, List<XYZ> results)
        {
            if (Math.Abs(d0) < 1e-7)
            {
                results.Add(p0);
                return;
            }
            if ((d0 > 0 && d1 < 0) || (d0 < 0 && d1 > 0))
            {
                double t = d0 / (d0 - d1);
                XYZ pt = p0 + t * (p1 - p0);
                results.Add(pt);
            }
        }

        /// <summary>
        /// Sắp xếp các điểm liên tục dọc theo cung cong
        /// </summary>
        private List<XYZ> SortPointsAlongCurve(List<XYZ> rawPoints, XYZ planeNormal)
        {
            if (rawPoints.Count <= 2) return rawPoints;

            // Tìm điểm đầu tiên (điểm có khoảng cách xa nhất tới trọng tâm hoặc điểm cực biên theo trục Z)
            XYZ center = new XYZ(rawPoints.Average(p => p.X), rawPoints.Average(p => p.Y), rawPoints.Average(p => p.Z));
            XYZ current = rawPoints.OrderByDescending(p => p.DistanceTo(center)).First();

            List<XYZ> sorted = new List<XYZ> { current };
            List<XYZ> remaining = new List<XYZ>(rawPoints.Where(p => p != current));

            while (remaining.Count > 0)
            {
                XYZ nearest = remaining.OrderBy(p => p.DistanceTo(current)).First();
                sorted.Add(nearest);
                remaining.Remove(nearest);
                current = nearest;
            }

            // Đảm bảo chiều của cung theo thứ tự hợp lý
            return sorted;
        }

        /// <summary>
        /// Bắn tia (Ray) từ điểm xuất phát theo hướng dir, tìm giao điểm với mặt phẳng (planeOrigin, planeNormal)
        /// </summary>
        private XYZ? RayIntersectPlane(XYZ rayOrigin, XYZ rayDir, XYZ planeOrigin, XYZ planeNormal)
        {
            double denom = rayDir.DotProduct(planeNormal);
            if (Math.Abs(denom) < 1e-7) return null; // Song song với mặt phẳng

            double t = (planeOrigin - rayOrigin).DotProduct(planeNormal) / denom;
            return rayOrigin + t * rayDir;
        }
    }
}
