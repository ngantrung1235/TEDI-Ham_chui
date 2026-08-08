using System.Collections.ObjectModel;
using TEDI_Ham_chui_model.ViewModels;

namespace TEDI_Ham_chui_model.Models
{
    // Đại diện cho 1 giá trị nhập vào của 1 file nhân bản
    public class ParameterValue : ViewModelBase
    {
        private string _valueText;
        public string ValueText
        {
            get => _valueText;
            set => SetProperty(ref _valueText, value);
        }
    }

    // Đại diện cho 1 thông số (Ví dụ: Chamfer, Height_N)
    public class ParameterRow : ViewModelBase
    {
        public string ParameterName { get; set; }
        
        // Danh sách các giá trị tương ứng với từng cột (từng file nhân bản)
        public ObservableCollection<ParameterValue> Values { get; set; }

        public ParameterRow(string name)
        {
            ParameterName = name;
            Values = new ObservableCollection<ParameterValue>();
        }
    }

    // Đại diện cho 1 nhóm Type (Ví dụ: FamilyCongHamChui-HT)
    public class TypeGroup : ViewModelBase
    {
        public string TypeName { get; set; }
        
        // Danh sách các thông số thuộc về Type này
        public ObservableCollection<ParameterRow> Parameters { get; set; }

        public TypeGroup(string name)
        {
            TypeName = name;
            Parameters = new ObservableCollection<ParameterRow>();
        }
    }
}
