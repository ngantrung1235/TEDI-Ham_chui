using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Input;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using TEDI_Ham_chui_model.Models;

namespace TEDI_Ham_chui_model.ViewModels
{
    // ViewModel cho nut "Ve tat ca thep": PICK 3 mat (mat bang/mat dung/mat canh) CHI
    // 1 LAN DUY NHAT cho moi host da chon (RebarCommon.PickHostGeometry), roi tai su
    // dung ket qua hinh hoc do (HostGeometry - Lv/Wv/Zv, solid, offset W/Z...) de goi
    // lan luot RunOnPrepared() cua 4 lenh ve thep da co san (RebarStirrupCLogic,
    // RebarOuterShapeLogic, RebarInnerSingleLogic, RebarChamferLogic) - khong con bat
    // nguoi dung pick lai 3 mat cho tung lenh nhu truoc.
    //
    // Moi lenh van tu dung coverFt RIENG cua no (RebarOuterShapeLogic dung CoverMm
    // truc tiep, 3 lenh con lai dung CoverMm + duong kinh S2/F2 - xem cong thuc trong
    // Run() ben duoi) de xay lai FaceDef rieng tu CUNG 1 HostGeometry da pick
    // (RebarCommon.PrepareHosts), KHONG dung chung 1 PreparedHost giua cac lenh vi
    // FaceDef.OuterPos/InnerPos/CrossMin/CrossMax phu thuoc coverFt.
    //
    // KHONG goi RebarLongitudinalCommand: RebarStirrupCLogic da tu ve lai toan bo thep
    // doc (4 mat x 2 lop Ngoai/Trong, xem RebarStirrupCLogic.cs) roi tao THEM dai C -
    // goi ca 2 se ve trung thep doc 2 lan.
    //
    // Moi lenh con tu mo/commit Transaction RIENG cua no trong RunOnPrepared, nen neu
    // 1 lenh sau do that bai (throw), cac lenh DA CHAY XONG TRUOC DO van giu nguyen ket
    // qua da tao (khong bi rollback theo).
    public class RebarAllInOneViewModel : ViewModelBase
    {
        // Lop bao ve be tong (cover) - NHAP 1 LAN DUNG CHUNG cho toan bo cau kien, thay vi
        // rieng cho tung loai thep. S2/F2 dung TRUC TIEP gia tri nay; cac loai con lai
        // (S1/F1/H1/S4/F4/H2/S5/S6/F6/H3) tu dong lui vao THEM duong kinh cua S2/F2 tuong
        // ung (xem cong thuc trong Run() ben duoi) - KHONG can nhap rieng.
        public double CoverMm { get; set; } = RebarCommon.DefaultCoverMm;

        // Cac property duoi day la NOI UI (RebarAllInOneInput.xaml) bind toi de nguoi dung
        // nhap D (mm) va khoang cach/spacing (mm) rieng cho tung loai thep theo ten trong
        // ban ve. Gia tri mac dinh lay THEO DUNG so lieu tren ban ve "SO DO KHUNG COT THEP
        // THAN HAM" (khong dung bang tra ten thanh/duong kinh vi bang do MAU THUAN voi ban
        // ve o vai dong - uu tien ban ve).

        // S1 (Nap) / F1 (Day) / H1 (Trai+Phai) - thep ngang lop Trong.
        public double DiamS1Mm { get; set; } = 25.0;
        public double SpaceS1Mm { get; set; } = 125.0;
        public double DiamF1Mm { get; set; } = 25.0;
        public double SpaceF1Mm { get; set; } = 125.0;
        public double DiamH1Mm { get; set; } = 16.0;
        public double SpaceH1Mm { get; set; } = 250.0;

        // S2 (Nap) / F2 (Day) - thep hinh Z (RebarShape "Rebar_21").
        public double DiamS2Mm { get; set; } = 20.0;
        public double SpaceS2Mm { get; set; } = 250.0;
        public double DiamF2Mm { get; set; } = 20.0;
        public double SpaceF2Mm { get; set; } = 250.0;

        // S4 (Nap) / F4 (Day) / H2 (Trai+Phai) - thep doc.
        public double DiamS4Mm { get; set; } = 14.0;
        public double SpaceS4Mm { get; set; } = 150.0;
        public double DiamF4Mm { get; set; } = 14.0;
        public double SpaceF4Mm { get; set; } = 150.0;
        public double DiamH2Mm { get; set; } = 14.0;
        public double SpaceH2Mm { get; set; } = 150.0;

        // S6 (Nap) / F6 (Day) / H3 (Trai+Phai) - dai C.
        public double DiamS6Mm { get; set; } = 12.0;
        public double SpaceS6Mm { get; set; } = 600.0;
        public double DiamF6Mm { get; set; } = 12.0;
        public double SpaceF6Mm { get; set; } = 600.0;
        public double DiamH3Mm { get; set; } = 12.0;
        public double SpaceH3Mm { get; set; } = 600.0;

        // S5 - thep cheo goc vat.
        public double DiamS5Mm { get; set; } = 15.0;
        public double SpaceS5Mm { get; set; } = 250.0;

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

        public string Run(UIDocument uidoc)
        {
            Document doc = uidoc.Document;

            var selectedIds = uidoc.Selection.GetElementIds();
            if (selectedIds.Count == 0)
                throw new InvalidOperationException("Vui lòng chọn ít nhất 1 cấu kiện trước khi chạy tool.");

            var pickReport = new List<string>();
            var geometries = RebarCommon.PickHostGeometry(uidoc, doc, selectedIds, pickReport);
            if (geometries.Count == 0)
                throw new InvalidOperationException(
                    "Không có cấu kiện hợp lệ nào để tạo thép sau bước pick.\n" + string.Join("\n", pickReport));

            // Cac loai thep khac (khong phai S2/F2) phai lui vao THEM duong kinh cua lop
            // Rebar_21 (S2/F2) tuong ung - vi Rebar_21 la lop ngoai cung tai Nap/Day. Dung
            // gia tri D nguoi dung nhap CHO CHINH S2/F2 (khong con la hang so co dinh nhu
            // truoc) de cong thuc nay luon dung du nguoi dung doi duong kinh S2/F2.
            double longitudinalCoverMm = CoverMm + Math.Max(DiamS2Mm, DiamF2Mm);
            double longitudinalCoverFt = RebarCommon.MmToFt(longitudinalCoverMm);
            double outerCoverFt = RebarCommon.MmToFt(CoverMm);

            var summaries = new List<string>();
            if (pickReport.Count > 0) summaries.Add(string.Join("\n", pickReport));

            var stirrupReport = new List<string>();
            summaries.Add(RebarStirrupCLogic.RunOnPrepared(
                doc, RebarCommon.PrepareHosts(geometries, longitudinalCoverFt), stirrupReport,
                DiamS4Mm, SpaceS4Mm, DiamF4Mm, SpaceF4Mm, DiamH2Mm, SpaceH2Mm,
                DiamS6Mm, SpaceS6Mm, DiamF6Mm, SpaceF6Mm, DiamH3Mm, SpaceH3Mm));

            var outerReport = new List<string>();
            summaries.Add(RebarOuterShapeLogic.RunOnPrepared(
                doc, RebarCommon.PrepareHosts(geometries, outerCoverFt), outerReport,
                DiamS2Mm, SpaceS2Mm, DiamF2Mm, SpaceF2Mm));

            var innerReport = new List<string>();
            summaries.Add(RebarInnerSingleLogic.RunOnPrepared(
                doc, RebarCommon.PrepareHosts(geometries, longitudinalCoverFt), innerReport,
                DiamS1Mm, SpaceS1Mm, DiamF1Mm, SpaceF1Mm, DiamH1Mm, SpaceH1Mm));

            var chamferReport = new List<string>();
            summaries.Add(RebarChamferLogic.RunOnPrepared(
                doc, RebarCommon.PrepareHosts(geometries, longitudinalCoverFt), chamferReport,
                DiamS5Mm, SpaceS5Mm, longitudinalCoverMm));

            return string.Join("\n\n", summaries);
        }
    }
}
