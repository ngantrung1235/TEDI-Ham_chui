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

                PushButtonData buttonData = new PushButtonData("cmdTaotho",
                   "Tạo thô", thisAssemblyPath, "TEDI_Ham_chui_model.ExternalCommands.Tao_tho");

                PushButton pushButton = ribbonPanel.AddItem(buttonData) as PushButton;

                

                return Result.Succeeded;
            }

        public Result OnShutdown(UIControlledApplication application)
        {
            // nothing to clean up in this simple case
            return Result.Succeeded;
        }
    }

}
