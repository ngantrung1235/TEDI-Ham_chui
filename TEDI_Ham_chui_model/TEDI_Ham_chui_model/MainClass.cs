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

                // Nút Tạo Thép (Lệnh mới thêm vào)
                PushButtonData btnTaoThepData = new PushButtonData("cmdTaoThep",
                   "Tạo thép\n(Rebar)", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.RebarByHostSelectionCommand");

                // Nút Test (Lệnh Rebar T13)
                PushButtonData btnTestData = new PushButtonData("cmdTest",
                   "Test", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.RebarT13Command");

                // Thêm các nút vào Ribbon Panel
                ribbonPanel.AddItem(btnTaoThoData);
                ribbonPanel.AddItem(btnTaoThepData);
                ribbonPanel.AddItem(btnTestData);

                

                return Result.Succeeded;
            }

        public Result OnShutdown(UIControlledApplication application)
        {
            // nothing to clean up in this simple case
            return Result.Succeeded;
        }
    }

}
