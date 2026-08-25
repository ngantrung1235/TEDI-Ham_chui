using Autodesk.Revit.UI;
using System.Reflection;
using System.Windows.Media.Imaging;
using System.IO;
namespace TEDI_Ham_chui_model
{
    
        public class MainClass : IExternalApplication
        {
            public Result OnStartup(UIControlledApplication application)
            {
                //Add a new ribbon tab
                application.CreateRibbonTab("Tedi-Ham_chui");

                // Add a new ribbon panel
                RibbonPanel ribbonPanel = application.CreateRibbonPanel("Tedi-Ham_chui", "NewRibbonPanel");


                //tạo 1 nút button tạo phần thô
                // Create a push button to trigger a command add it to the ribbon panel.
                string thisAssemblyPath = Assembly.GetExecutingAssembly().Location;
                string assemblyDir = Path.GetDirectoryName(thisAssemblyPath);

                // Nút Tạo Thô (Đã có từ trước)
                PushButtonData btnTaoThoData = new PushButtonData("cmdTaotho",
                   "Tạo thô", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.Tao_tho");

                // Nút Tạo Thép Dọc (Bố 1 - chạy dọc theo Lv, 4 mặt x 2 lớp)
                PushButtonData btnRebarLongData = new PushButtonData("cmdRebarLong",
                   "Tạo thép\ndọc", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.RebarLongitudinalCommand");

                // Nút Tạo Rebar 0 Nắp/Đáy (Bố 2 lớp Ngoài của Đáy/Nắp - chữ Z)
                PushButtonData btnRebarOuterData = new PushButtonData("cmdRebarOuter",
                   "Tạo Rebar 0\nNắp/Đáy", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.RebarOuterShapeCommand");

                // Nút Tạo Thép Single Bên Trong (Bố 2 lớp Trong, cả 4 mặt)
                PushButtonData btnRebarInnerData = new PushButtonData("cmdRebarInner",
                   "Tạo thép\nsingle trong", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.RebarInnerSingleCommand");

                // Nút Tạo Thép Chéo Góc Vát (Chamfer)
                PushButtonData btnRebarChamferData = new PushButtonData("cmdRebarChamfer",
                   "Tạo thép\nchéo", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.RebarChamferCommand");

                // Nút Tạo Thép Dọc + Đai C (thép dọc 4 mặt x 2 lớp, kèm đai C nối lớp Ngoài-Trong)
                PushButtonData btnRebarStirrupCData = new PushButtonData("cmdRebarStirrupC",
                   "Tạo thép dọc\n+ đai C", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.RebarStirrupCCommand");

                // Thêm các nút vào Ribbon Panel
                ribbonPanel.AddItem(btnTaoThoData);
                ribbonPanel.AddItem(btnRebarLongData);
                ribbonPanel.AddItem(btnRebarOuterData);
                ribbonPanel.AddItem(btnRebarInnerData);
                ribbonPanel.AddItem(btnRebarChamferData);
                ribbonPanel.AddItem(btnRebarStirrupCData);



                return Result.Succeeded;
            }

        public Result OnShutdown(UIControlledApplication application)
        {
            // nothing to clean up in this simple case
            return Result.Succeeded;
        }
    }

}
