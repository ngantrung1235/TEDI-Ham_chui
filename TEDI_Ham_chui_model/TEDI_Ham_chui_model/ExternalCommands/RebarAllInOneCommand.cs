using System;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.UI;
using TEDI_Ham_chui_model.ViewModels;
using TEDI_Ham_chui_model.Views;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Nut "Ve tat ca thep" - entry point Revit mong: mo form nhap D/spacing/cover
    // (Views/RebarAllInOneInput.xaml), roi giao toan bo logic pick + tao thep cho
    // RebarAllInOneViewModel (xem ViewModels/RebarAllInOneViewModel.cs).
    [Transaction(TransactionMode.Manual)]
    public class RebarAllInOneCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, Autodesk.Revit.DB.ElementSet elements)
        {
            try
            {
                var viewModel = new RebarAllInOneViewModel();

                var inputWindow = new RebarAllInOneInput { DataContext = viewModel };
                bool? dialogResult = inputWindow.ShowDialog();
                if (dialogResult != true)
                    return Result.Cancelled;

                string summary = viewModel.Run(commandData.Application.ActiveUIDocument);

                TaskDialog.Show("Vẽ tất cả thép - Thành công", summary);
                return Result.Succeeded;
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                return Result.Cancelled;
            }
            catch (InvalidOperationException ex)
            {
                message = ex.Message;
                return Result.Failed;
            }
            catch (Exception ex)
            {
                message = ex.Message + "\n" + ex.StackTrace;
                return Result.Failed;
            }
        }
    }
}
