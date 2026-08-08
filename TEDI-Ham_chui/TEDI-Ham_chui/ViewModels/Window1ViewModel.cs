using System;
using System.IO;
using System.Linq;
using System.Windows.Input;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Selection;

namespace TEDI_Ham_chui.ViewModels
{
    public class Window1ViewModel : ViewModelBase
    {
        private double _cr = 200;
        private double _chamfer = 50;
        private double _wGo = 100;
        private double _height = 2000;
        private double _width = 2000;
        private double _h1 = 300;
        private double _h2 = 300;
        private double _length = 5000;
        private double _h3 = 200;
        private double _radiusCut = 150;

        public double CR { get => _cr; set => SetProperty(ref _cr, value); }
        public double Chamfer { get => _chamfer; set => SetProperty(ref _chamfer, value); }
        public double WGo { get => _wGo; set => SetProperty(ref _wGo, value); }
        public double Height { get => _height; set => SetProperty(ref _height, value); }
        public double Width { get => _width; set => SetProperty(ref _width, value); }
        public double H1 { get => _h1; set => SetProperty(ref _h1, value); }
        public double H2 { get => _h2; set => SetProperty(ref _h2, value); }
        public double Length { get => _length; set => SetProperty(ref _length, value); }
        public double H3 { get => _h3; set => SetProperty(ref _h3, value); }
        public double RadiusCut { get => _radiusCut; set => SetProperty(ref _radiusCut, value); }

        public ICommand OKCommand { get; }
        public ICommand CancelCommand { get; }

        public Window1ViewModel()
        {
            OKCommand = new RelayCommand(ExecuteOK);
            CancelCommand = new RelayCommand(ExecuteCancel);
        }

        private void ExecuteOK(object parameter)
        {
            if (parameter is System.Windows.Window window)
            {
                window.DialogResult = true;
                window.Close();
            }
        }

        private void ExecuteCancel(object parameter)
        {
            if (parameter is System.Windows.Window window)
            {
                window.DialogResult = false;
                window.Close();
            }
        }

        // Logic để thực thi Revit API được chuyển vào đây
        public void PlaceFamilyInRevit(UIDocument uidoc)
        {
            Document doc = uidoc.Document;
            XYZ placePoint = null;

            try
            {
                placePoint = uidoc.Selection.PickPoint("Vui lòng chọn 1 điểm để đặt Family Cống Hộp");
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                // Hủy lệnh
                return;
            }

            using (Transaction t = new Transaction(doc, "Đặt Family Cống Hộp"))
            {
                t.Start();

                string familyName = "cong hop 2.0x2.0m";
                FamilySymbol symbol = GetFamilySymbol(doc, familyName);

                if (symbol == null)
                {
                    string assemblyPath = System.Reflection.Assembly.GetExecutingAssembly().Location;
                    string addinFolder = Path.GetDirectoryName(assemblyPath);
                    string familyPath = Path.Combine(addinFolder, "Family", $"{familyName}.rfa");

                    if (File.Exists(familyPath))
                    {
                        Family family = null;
                        if (doc.LoadFamily(familyPath, out family))
                        {
                            var symbolIds = family.GetFamilySymbolIds();
                            if (symbolIds.Count > 0)
                            {
                                symbol = doc.GetElement(symbolIds.First()) as FamilySymbol;
                            }
                        }
                    }
                    else
                    {
                        TaskDialog.Show("Lỗi", $"Không tìm thấy file Family tại:\n{familyPath}\n\nVui lòng đảm bảo folder 'Family' có chứa file .rfa!");
                        return;
                    }
                }

                if (symbol != null)
                {
                    if (!symbol.IsActive)
                    {
                        symbol.Activate();
                        doc.Regenerate();
                    }

                    FamilyInstance instance = doc.Create.NewFamilyInstance(placePoint, symbol, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);

                    double MmToFeet(double mm) => mm / 304.8;

                    SetParameter(instance, "CR", MmToFeet(CR));
                    SetParameter(instance, "Chamfer", MmToFeet(Chamfer));
                    SetParameter(instance, "W Go", MmToFeet(WGo));
                    SetParameter(instance, "Height", MmToFeet(Height));
                    SetParameter(instance, "Width", MmToFeet(Width));
                    SetParameter(instance, "H1", MmToFeet(H1));
                    SetParameter(instance, "H2", MmToFeet(H2));
                    SetParameter(instance, "Length", MmToFeet(Length));
                    SetParameter(instance, "H3", MmToFeet(H3));
                    SetParameter(instance, "radius cut", MmToFeet(RadiusCut));
                }

                t.Commit();
            }
        }

        private FamilySymbol GetFamilySymbol(Document doc, string familyName)
        {
            return new FilteredElementCollector(doc)
                .OfClass(typeof(FamilySymbol))
                .Cast<FamilySymbol>()
                .FirstOrDefault(x => x.FamilyName.Equals(familyName, StringComparison.OrdinalIgnoreCase));
        }

        private void SetParameter(FamilyInstance instance, string paramName, double value)
        {
            Parameter param = instance.LookupParameter(paramName);
            if (param != null && !param.IsReadOnly)
            {
                param.Set(value);
            }
        }
    }
}
