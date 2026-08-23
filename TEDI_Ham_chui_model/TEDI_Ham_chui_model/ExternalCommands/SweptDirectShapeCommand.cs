// SweptDirectShapeCommand.cs
//
// Ví dụ External Command cho Revit: tạo 1 DirectShape bằng cách "extrude" (thực chất là SWEEP)
// một profile (shape) tuỳ ý dọc theo 1 đường path đã xác định trước (chuỗi Line/Arc bất kỳ).
//
// Tham chiếu cần add vào project: RevitAPI.dll, RevitAPIUI.dll (Copy Local = False)
// Target framework: theo đúng version Revit bạn dùng (Revit 2022+ dùng .NET Framework 4.8,
// Revit 2025+ dùng .NET 8).
//
// Đăng ký add-in qua file .addin (xem ghi chú cuối file).

using System;
using System.Collections.Generic;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    [Transaction(TransactionMode.Manual)]
    public class SweptDirectShapeCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIDocument uidoc = commandData.Application.ActiveUIDocument;
            Document doc = uidoc.Document;

            try
            {
                // ============================================================
                // BƯỚC 1 — Định nghĩa PATH (đường dẫn đã xác định trước)
                // Đơn vị nội bộ Revit luôn là FEET, dù project đang hiển thị mm/m.
                // Path có thể gồm nhiều Line/Arc/Spline nối tiếp nhau, KHÔNG cần khép kín.
                // ============================================================
                XYZ p0 = new XYZ(0, 0, 0);
                XYZ p1 = new XYZ(10, 0, 0);
                XYZ p2 = new XYZ(15, 5, 0);

                Line line1 = Line.CreateBound(p0, p1);
                Arc arc1 = Arc.Create(p1, p2, new XYZ(15, 0, 0)); // arc đi qua điểm giữa (15,0,0)

                CurveLoop path = new CurveLoop();
                path.Append(line1);
                path.Append(arc1);
                // path.Append(...) thêm bao nhiêu đoạn tuỳ theo path thực tế của bạn

                // ============================================================
                // BƯỚC 2 — Chọn điểm "gắn" (attachment point) cho profile trên path.
                // Thường là điểm đầu tiên: curve index = 0, tham số = điểm đầu của curve đó.
                // Lưu ý: attachmentParameter phải là tham số GỐC (raw) của curve, không phải
                // giá trị chuẩn hoá 0..1.
                // ============================================================
                int pathCurveIndex = 0;
                Curve firstCurve = line1; // phải trùng với curve tại index 0 trong path
                double attachParam = firstCurve.GetEndParameter(0);

                // Lấy hệ toạ độ cục bộ tại điểm gắn để dựng mặt phẳng vuông góc với path.
                // Không dùng trực tiếp BasisY/BasisZ của ComputeDerivatives vì với Line,
                // đạo hàm bậc 2 bằng 0 -> các basis đó có thể suy biến.
                Transform frameAtStart = firstCurve.ComputeDerivatives(attachParam, false);
                XYZ origin = frameAtStart.Origin;
                XYZ tangent = frameAtStart.BasisX.Normalize();

                XYZ helper = Math.Abs(tangent.DotProduct(XYZ.BasisZ)) < 0.999 ? XYZ.BasisZ : XYZ.BasisY;
                XYZ profileX = tangent.CrossProduct(helper).Normalize();
                XYZ profileY = tangent.CrossProduct(profileX).Normalize();

                // ============================================================
                // BƯỚC 3 — Vẽ PROFILE (cái "shape" sẽ được sweep dọc path).
                // Định nghĩa bằng toạ độ 2D cục bộ (u, v) rồi map sang mặt phẳng 3D
                // vuông góc với path tại điểm gắn. Thay đổi danh sách UV này để có
                // shape tuỳ ý (chữ nhật, đa giác, chữ I, v.v.). Đơn vị: feet.
                // ============================================================
                List<UV> profile2D = new List<UV>
                {
                    new UV(-0.5, -0.25),
                    new UV( 0.5, -0.25),
                    new UV( 0.5,  0.25),
                    new UV(-0.5,  0.25),
                };

                List<Curve> profileCurves = new List<Curve>();
                for (int i = 0; i < profile2D.Count; i++)
                {
                    UV a = profile2D[i];
                    UV b = profile2D[(i + 1) % profile2D.Count];
                    XYZ pa = origin + a.U * profileX + a.V * profileY;
                    XYZ pb = origin + b.U * profileX + b.V * profileY;
                    profileCurves.Add(Line.CreateBound(pa, pb));
                }
                CurveLoop profileLoop = CurveLoop.Create(profileCurves);
                IList<CurveLoop> profileLoops = new List<CurveLoop> { profileLoop };

                // ============================================================
                // BƯỚC 4 — Sweep profile dọc theo path để tạo Solid
                // ============================================================
                Solid sweptSolid = GeometryCreationUtilities.CreateSweptGeometry(
                    path, pathCurveIndex, attachParam, profileLoops);

                // ============================================================
                // BƯỚC 5 — Đưa Solid vào DirectShape để hiển thị trong model Revit
                // ============================================================
                using (Transaction t = new Transaction(doc, "Create Swept DirectShape"))
                {
                    t.Start();

                    DirectShape ds = DirectShape.CreateElement(
                        doc, new ElementId(BuiltInCategory.OST_GenericModel));
                    ds.ApplicationId = "SweepAlongPathSample";
                    ds.ApplicationDataId = Guid.NewGuid().ToString();
                    ds.SetShape(new GeometryObject[] { sweptSolid });

                    t.Commit();
                }

                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = "Tạo swept geometry thất bại: " + ex.Message;
                return Result.Failed;
            }
        }
    }
}

// ============================================================
// GHI CHÚ TRIỂN KHAI (.addin manifest)
// ============================================================
// Tạo file SweepAlongPathSample.addin cạnh file .dll build ra, đặt trong:
//   %APPDATA%\Autodesk\Revit\Addins\<version>\
//
// <?xml version="1.0" encoding="utf-8" standalone="no"?>
// <RevitAddIns>
//   <AddIn Type="Command">
//     <Name>Swept DirectShape Sample</Name>
//     <Assembly>C:\path\to\SweepAlongPathSample.dll</Assembly>
//     <AddInId>PUT-A-NEW-GUID-HERE</AddInId>
//     <FullClassName>SweepAlongPathSample.SweptDirectShapeCommand</FullClassName>
//     <VendorId>ABCD</VendorId>
//     <VendorDescription>Your Name</VendorDescription>
//   </AddIn>
// </RevitAddIns>
