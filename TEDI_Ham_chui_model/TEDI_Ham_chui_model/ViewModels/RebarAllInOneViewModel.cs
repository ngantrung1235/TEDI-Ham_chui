using System.Windows;
using System.Windows.Input;
using TEDI_Ham_chui_model.Models;

namespace TEDI_Ham_chui_model.ViewModels
{
    // ViewModel cho form "Ve tat ca thep" (Views/RebarAllInOneInput.xaml): toan bo thong so
    // (CoverMm, D/spacing tung loai thep...) va ham Run() nam o Models/RebarAllInOneSettings.cs;
    // lop nay chi them lenh OK/Cancel cho cua so.
    public class RebarAllInOneViewModel : RebarAllInOneSettings
    {
        public ICommand OkCommand { get; }
        public ICommand CancelCommand { get; }

        public RebarAllInOneViewModel()
        {
            OkCommand = new RelayCommand(ExecuteOk);
            CancelCommand = new RelayCommand(ExecuteCancel);
        }

        private void ExecuteOk(object parameter)
        {
            if (parameter is Window window)
            {
                window.DialogResult = true;
                window.Close();
            }
        }

        private void ExecuteCancel(object parameter)
        {
            if (parameter is Window window)
            {
                window.DialogResult = false;
                window.Close();
            }
        }
    }
}
