using Autodesk.Revit.Attributes;
using Autodesk.Revit.UI;
using TEDI_Ham_chui_model.Views;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    [Transaction(TransactionMode.Manual)]
    public class Tao_tho:IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, Autodesk.Revit.DB.ElementSet elements)
        {
            try
            {
                // Khởi tạo ViewModel
                var viewModel = new TEDI_Ham_chui_model.ViewModels.InputViewModel();

                // Gán ViewModel vào DataContext của giao diện
                Input viewBoctach = new Input();
                viewBoctach.DataContext = viewModel;

                // Mở cửa sổ dạng Modal (bắt buộc để có thể PickPoint sau khi đóng)
                bool? result = viewBoctach.ShowDialog();

                if (result == true)
                {
                    // Thực thi logic Revit API từ ViewModel
                    viewModel.BatchProcessRevitFiles(commandData.Application);
                }

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
