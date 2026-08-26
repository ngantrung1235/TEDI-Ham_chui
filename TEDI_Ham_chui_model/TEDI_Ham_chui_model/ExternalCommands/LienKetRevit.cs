using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Microsoft.Win32;

namespace TEDI_Ham_chui_model.ExternalCommands
{
    // Liên kết (link) các file .rvt vào model đang mở theo kiểu Origin to Origin.
    // Dùng để đưa các file được sinh ra từ lệnh "Tạo thô" vào 1 model tổng.
    [Transaction(TransactionMode.Manual)]
    public class LienKetRevit : IExternalCommand
    {
        // Nhớ thư mục đã chọn lần trước trong cùng 1 phiên Revit
        private static string _lastFolder;

        // File backup của Revit có dạng: TenFile.0001.rvt -> không đưa vào danh sách liên kết
        private static readonly Regex _backupPattern = new Regex(@"\.\d{4}\.rvt$", RegexOptions.IgnoreCase);

        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            try
            {
                Document doc = commandData.Application.ActiveUIDocument?.Document;

                if (doc == null)
                {
                    message = "Không có model nào đang mở.";
                    return Result.Failed;
                }

                if (doc.IsFamilyDocument)
                {
                    TaskDialog.Show("Liên kết Revit", "Không thể liên kết file Revit vào môi trường Family. Hãy mở 1 Project (.rvt) rồi chạy lại lệnh.");
                    return Result.Cancelled;
                }

                List<string> filePaths = ChonFileCanLienKet();
                if (filePaths == null) return Result.Cancelled;

                if (filePaths.Count == 0)
                {
                    TaskDialog.Show("Liên kết Revit", "Không tìm thấy file .rvt nào để liên kết.");
                    return Result.Cancelled;
                }

                LienKet(doc, filePaths);
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.Message;
                return Result.Failed;
            }
        }

        // Cho người dùng chọn từng file, hoặc chọn cả 1 thư mục.
        // Trả về null nếu người dùng bấm huỷ.
        private List<string> ChonFileCanLienKet()
        {
            TaskDialog td = new TaskDialog("Liên kết Revit");
            td.MainInstruction = "Chọn nguồn file cần liên kết";
            td.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Chọn các file .rvt", "Có thể chọn nhiều file cùng lúc.");
            td.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Chọn cả thư mục", "Liên kết toàn bộ file .rvt trong thư mục (bỏ qua file backup dạng .0001.rvt).");
            td.CommonButtons = TaskDialogCommonButtons.Cancel;
            td.DefaultButton = TaskDialogResult.Cancel;

            TaskDialogResult result = td.Show();

            if (result == TaskDialogResult.CommandLink1)
            {
                var dialog = new OpenFileDialog
                {
                    Filter = "Revit Project (*.rvt)|*.rvt",
                    Title = "Chọn file Revit cần liên kết",
                    Multiselect = true
                };
                if (!string.IsNullOrEmpty(_lastFolder) && Directory.Exists(_lastFolder))
                    dialog.InitialDirectory = _lastFolder;

                if (dialog.ShowDialog() != true) return null;

                _lastFolder = Path.GetDirectoryName(dialog.FileName);
                return dialog.FileNames.ToList();
            }

            if (result == TaskDialogResult.CommandLink2)
            {
                var dialog = new OpenFolderDialog { Title = "Chọn thư mục chứa file Revit" };
                if (!string.IsNullOrEmpty(_lastFolder) && Directory.Exists(_lastFolder))
                    dialog.InitialDirectory = _lastFolder;

                if (dialog.ShowDialog() != true) return null;

                _lastFolder = dialog.FolderName;
                return Directory.GetFiles(dialog.FolderName, "*.rvt")
                                .Where(p => !_backupPattern.IsMatch(Path.GetFileName(p)))
                                .OrderBy(p => p, StringComparer.OrdinalIgnoreCase)
                                .ToList();
            }

            return null;
        }

        private void LienKet(Document doc, List<string> filePaths)
        {
            // Các link đã có sẵn trong model (bỏ qua link lồng trong link khác)
            var linkDaCo = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var linkType in new FilteredElementCollector(doc)
                .OfClass(typeof(RevitLinkType))
                .Cast<RevitLinkType>()
                .Where(x => !x.IsNestedLink))
            {
                string duongDan = LayDuongDan(linkType);
                if (!string.IsNullOrEmpty(duongDan)) linkDaCo.Add(duongDan);
            }

            int soLinkMoi = 0;
            var boQua = new List<string>();
            var loi = new List<string>();

            using (Transaction t = new Transaction(doc, "Liên kết file Revit"))
            {
                t.Start();

                foreach (string filePath in filePaths)
                {
                    string tenFile = Path.GetFileName(filePath);
                    try
                    {
                        if (LaChinhModelHienTai(doc, filePath))
                        {
                            boQua.Add($"{tenFile} (là model đang mở)");
                            continue;
                        }

                        if (linkDaCo.Contains(ChuanHoaDuongDan(filePath)))
                        {
                            boQua.Add($"{tenFile} (đã được liên kết)");
                            continue;
                        }

                        var options = new RevitLinkOptions(false); // lưu đường dẫn tuyệt đối
                        ModelPath modelPath = ModelPathUtils.ConvertUserVisiblePathToModelPath(filePath);
                        LinkLoadResult loadResult = RevitLinkType.Create(doc, modelPath, options);

                        if (loadResult == null || loadResult.ElementId == ElementId.InvalidElementId)
                        {
                            loi.Add($"{tenFile}: không tải được ({loadResult?.LoadResult})");
                            continue;
                        }

                        // Origin to Origin: gốc file link trùng gốc model chủ
                        RevitLinkInstance.Create(doc, loadResult.ElementId, ImportPlacement.Origin);

                        linkDaCo.Add(ChuanHoaDuongDan(filePath));
                        soLinkMoi++;
                    }
                    catch (Exception ex)
                    {
                        loi.Add($"{tenFile}: {ex.Message}");
                    }
                }

                t.Commit();
            }

            BaoCaoKetQua(soLinkMoi, filePaths.Count, boQua, loi);
        }

        private void BaoCaoKetQua(int soLinkMoi, int tongSo, List<string> boQua, List<string> loi)
        {
            var sb = new StringBuilder();
            sb.AppendLine($"Đã liên kết {soLinkMoi}/{tongSo} file (Origin to Origin).");

            if (boQua.Count > 0)
            {
                sb.AppendLine();
                sb.AppendLine($"Bỏ qua {boQua.Count} file:");
                foreach (string item in boQua) sb.AppendLine($"  - {item}");
            }

            if (loi.Count > 0)
            {
                sb.AppendLine();
                sb.AppendLine($"Lỗi {loi.Count} file:");
                foreach (string item in loi) sb.AppendLine($"  - {item}");
            }

            TaskDialog.Show(loi.Count > 0 ? "Liên kết Revit - có lỗi" : "Liên kết Revit", sb.ToString());
        }

        // Đường dẫn tuyệt đối của 1 link đang có trong model
        private static string LayDuongDan(RevitLinkType linkType)
        {
            try
            {
                if (!linkType.IsExternalFileReference()) return string.Empty;

                ExternalFileReference reference = linkType.GetExternalFileReference();
                if (reference == null) return string.Empty;

                return ChuanHoaDuongDan(ModelPathUtils.ConvertModelPathToUserVisiblePath(reference.GetAbsolutePath()));
            }
            catch
            {
                return string.Empty;
            }
        }

        private static bool LaChinhModelHienTai(Document doc, string filePath)
        {
            if (string.IsNullOrEmpty(doc.PathName)) return false;
            return string.Equals(ChuanHoaDuongDan(doc.PathName), ChuanHoaDuongDan(filePath), StringComparison.OrdinalIgnoreCase);
        }

        private static string ChuanHoaDuongDan(string path)
        {
            if (string.IsNullOrWhiteSpace(path)) return string.Empty;
            try
            {
                return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
            }
            catch
            {
                return path;
            }
        }
    }
}
