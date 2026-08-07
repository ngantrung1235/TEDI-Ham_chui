using Autodesk.Revit.Attributes;
using Autodesk.Revit.UI;
using TEDI_Ham_chui.Views;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace TEDI_Ham_chui.ExternalCommands
{
    [Transaction(TransactionMode.Manual)]
    public class Tao_tho:IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, Autodesk.Revit.DB.ElementSet elements)
        {
            try
            {
                
                Window1 viewBoctach=new Window1();
                viewBoctach.Show();

                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.Message;
                return Result.Failed;
            }
        }
    }
}
