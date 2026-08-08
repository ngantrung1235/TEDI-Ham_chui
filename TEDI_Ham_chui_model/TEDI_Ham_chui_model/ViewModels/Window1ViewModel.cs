using System;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Input;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Microsoft.Win32;
using TEDI_Ham_chui_model.Models;

namespace TEDI_Ham_chui_model.ViewModels
{
    public class Window1ViewModel : ViewModelBase
    {
        public ObservableCollection<TypeGroup> TypeGroups { get; set; }
        public ObservableCollection<string> FileHeaders { get; set; }

        private string _outputDirectory;
        public string OutputDirectory
        {
            get => _outputDirectory;
            set => SetProperty(ref _outputDirectory, value);
        }

        public ICommand SelectOutputDirCommand { get; }
        public ICommand AddColumnCommand { get; }
        public ICommand RemoveColumnCommand { get; }
        public ICommand CreateCommand { get; }
        public ICommand CancelCommand { get; }

        public Window1ViewModel()
        {
            TypeGroups = new ObservableCollection<TypeGroup>();
            FileHeaders = new ObservableCollection<string>();

            SelectOutputDirCommand = new RelayCommand(ExecuteSelectOutputDir);
            AddColumnCommand = new RelayCommand(ExecuteAddColumn);
            RemoveColumnCommand = new RelayCommand(ExecuteRemoveColumn, CanExecuteRemoveColumn);
            CreateCommand = new RelayCommand(ExecuteCreate, CanExecuteCreate);
            CancelCommand = new RelayCommand(ExecuteCancel);

            InitializeDefaultData();
        }

        private void InitializeDefaultData()
        {
            // Initial columns
            FileHeaders.Add("Bản sao 1");

            // 1. FamilyCongHamChui-HT (6 parameters)
            var g1 = new TypeGroup("FamilyCongHamChui-HT");
            g1.Parameters.Add(CreateRow("Chamfer"));
            g1.Parameters.Add(CreateRow("Height_N"));
            g1.Parameters.Add(CreateRow("Height_T"));
            g1.Parameters.Add(CreateRow("W_Go"));
            g1.Parameters.Add(CreateRow("Width_N"));
            g1.Parameters.Add(CreateRow("Width_T"));
            g1.Parameters.Add(CreateRow("l_tai"));
            TypeGroups.Add(g1);

            // 2. TuongCanhPhai 1 (3 parameters)
            var g2 = new TypeGroup("TuongCanhPhai 1");
            g2.Parameters.Add(CreateRow("Heigth"));
            g2.Parameters.Add(CreateRow("Length"));
            g2.Parameters.Add(CreateRow("Radius"));
            TypeGroups.Add(g2);

            // 3. TuongCanhPhai 2 (3 parameters)
            var g3 = new TypeGroup("TuongCanhPhai 2");
            g3.Parameters.Add(CreateRow("Heigth"));
            g3.Parameters.Add(CreateRow("Length"));
            g3.Parameters.Add(CreateRow("Radius"));
            TypeGroups.Add(g3);

            // 6. BanQuaDoPhai 1 (4 parameters)
            var g6 = new TypeGroup("BanQuaDoPhai 1");
            g6.Parameters.Add(CreateRow("BeDay"));
            g6.Parameters.Add(CreateRow("H1"));
            g6.Parameters.Add(CreateRow("H3"));
            g6.Parameters.Add(CreateRow("W_Go"));
            g6.Parameters.Add(CreateRow("l_tai"));
            TypeGroups.Add(g6);

            // 7. BanQuaDoPhai 2 (4 parameters)
            var g7 = new TypeGroup("BanQuaDoPhai 2");
            g7.Parameters.Add(CreateRow("BeDay"));
            g7.Parameters.Add(CreateRow("H1"));
            g7.Parameters.Add(CreateRow("H3"));
            g7.Parameters.Add(CreateRow("W_Go"));
            g7.Parameters.Add(CreateRow("l_tai"));
            TypeGroups.Add(g7);

            // 8. BanQuaDoTrai 1 (4 parameters)
            var g8 = new TypeGroup("BanQuaDoTrai 1");
            g8.Parameters.Add(CreateRow("BeDay"));
            g8.Parameters.Add(CreateRow("H1"));
            g8.Parameters.Add(CreateRow("H3"));
            g8.Parameters.Add(CreateRow("W_Go"));
            g8.Parameters.Add(CreateRow("l_tai"));
            TypeGroups.Add(g8);

            // 9. BanQuaDoTrai 2 (4 parameters)
            var g9 = new TypeGroup("BanQuaDoTrai 2");
            g9.Parameters.Add(CreateRow("BeDay"));
            g9.Parameters.Add(CreateRow("H1"));
            g9.Parameters.Add(CreateRow("H3"));
            g9.Parameters.Add(CreateRow("W_Go"));
            g9.Parameters.Add(CreateRow("l_tai"));
            TypeGroups.Add(g9);

            // 10. TuongCanhTrai 1 - nhóm 2 (5 parameters)
            var g10 = new TypeGroup("TuongCanhTrai 1");
            g10.Parameters.Add(CreateRow("Hw"));
            g10.Parameters.Add(CreateRow("Hw2"));
            g10.Parameters.Add(CreateRow("Lw1"));
            g10.Parameters.Add(CreateRow("Lw"));
            g10.Parameters.Add(CreateRow("Radius"));
            TypeGroups.Add(g10);

            // 11. TuongCanhTrai 2 - nhóm 2 (5 parameters)
            var g11 = new TypeGroup("TuongCanhTrai 2");
            g11.Parameters.Add(CreateRow("Hw"));
            g11.Parameters.Add(CreateRow("Hw2"));
            g11.Parameters.Add(CreateRow("Lw1"));
            g11.Parameters.Add(CreateRow("Lw"));
            g11.Parameters.Add(CreateRow("Radius"));
            TypeGroups.Add(g11);
        }

        private ParameterRow CreateRow(string paramName)
        {
            var row = new ParameterRow(paramName);
            // Default 1 column
            row.Values.Add(new TEDI_Ham_chui_model.Models.ParameterValue { ValueText = "" });
            return row;
        }

        private void ExecuteSelectOutputDir(object obj)
        {
            var dialog = new Microsoft.Win32.OpenFolderDialog();
            if (dialog.ShowDialog() == true)
            {
                OutputDirectory = dialog.FolderName;
            }
        }

        private void ExecuteAddColumn(object obj)
        {
            int nextIndex = FileHeaders.Count + 1;
            FileHeaders.Add($"Bản sao {nextIndex}");

            foreach (var group in TypeGroups)
            {
                foreach (var param in group.Parameters)
                {
                    param.Values.Add(new TEDI_Ham_chui_model.Models.ParameterValue { ValueText = "" });
                }
            }
        }

        private bool CanExecuteRemoveColumn(object obj)
        {
            return FileHeaders.Count > 1;
        }

        private void ExecuteRemoveColumn(object obj)
        {
            if (FileHeaders.Count > 1)
            {
                int lastIndex = FileHeaders.Count - 1;
                FileHeaders.RemoveAt(lastIndex);

                foreach (var group in TypeGroups)
                {
                    foreach (var param in group.Parameters)
                    {
                        param.Values.RemoveAt(lastIndex);
                    }
                }
            }
        }

        private bool CanExecuteCreate(object obj)
        {
            return !string.IsNullOrEmpty(OutputDirectory);
        }

        private void ExecuteCreate(object parameter)
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

        public void BatchProcessRevitFiles(UIApplication uiApp)
        {
            string assemblyPath = System.Reflection.Assembly.GetExecutingAssembly().Location;
            string addinFolder = Path.GetDirectoryName(assemblyPath);
            string templateFilePath = Path.Combine(addinFolder, "Models", "HamChui_KM77+633.rvt");

            if (!File.Exists(templateFilePath))
            {
                TaskDialog.Show("Lỗi", $"Không tìm thấy file mẫu tại:\n{templateFilePath}");
                return;
            }

            int fileCount = FileHeaders.Count;
            double MmToFeet(double mm) => mm / 304.8;

            for (int i = 0; i < fileCount; i++)
            {
                string newFileName = Path.Combine(OutputDirectory, $"Output_File_{i + 1}.rvt");
                File.Copy(templateFilePath, newFileName, true);

                // Mở ngầm file (true = detach from central if it is a workshared model, false for normal)
                Document bgDoc = uiApp.Application.OpenDocumentFile(newFileName);
                
                using (Transaction t = new Transaction(bgDoc, "Update Parameters"))
                {
                    t.Start();
                    
                    foreach (var group in TypeGroups)
                    {
                        // Tìm Family Symbol theo TypeName
                        var familySymbol = new FilteredElementCollector(bgDoc)
                            .OfClass(typeof(FamilySymbol))
                            .Cast<FamilySymbol>()
                            .FirstOrDefault(x => x.Name == group.TypeName);
                            
                        if (familySymbol != null)
                        {
                            foreach (var paramRow in group.Parameters)
                            {
                                string valText = paramRow.Values[i].ValueText;
                                if (double.TryParse(valText, out double valMm))
                                {
                                    Parameter param = familySymbol.LookupParameter(paramRow.ParameterName);
                                    if (param != null && !param.IsReadOnly)
                                    {
                                        param.Set(MmToFeet(valMm));
                                    }
                                }
                            }
                        }
                    }
                    
                    t.Commit();
                }
                
                // Đóng file và lưu lại
                SaveAsOptions saveOptions = new SaveAsOptions();
                saveOptions.OverwriteExistingFile = true;
                bgDoc.SaveAs(newFileName, saveOptions);
                bgDoc.Close();
            }
            
            TaskDialog.Show("Thành công", $"Đã tạo {fileCount} file Revit trong:\n{OutputDirectory}");
        }
    }
}
