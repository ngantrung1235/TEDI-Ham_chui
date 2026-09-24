using System;
using System.Reflection;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.UI;

namespace TEDI_ClaudeBridge
{
    // Add-in doc lap, KHONG phu thuoc TEDI_Ham_chui_model: tao tab "TEDI Claude" voi 1
    // nut bat/tat cau noi. Tach rieng de chay duoc tren Revit 2024 (.NET Framework 4.8)
    // lan Revit 2027 (.NET 10) - xem TargetFrameworks trong TEDI_ClaudeBridge.csproj.
    public class App : IExternalApplication
    {
        private const string TabName = "TEDI Claude";

        public Result OnStartup(UIControlledApplication application)
        {
            application.CreateRibbonTab(TabName);
            RibbonPanel panel = application.CreateRibbonPanel(TabName, "Claude");

            var buttonData = new PushButtonData("cmdClaudeBridge", "Kết nối\nClaude",
                Assembly.GetExecutingAssembly().Location, typeof(ToggleBridgeCommand).FullName)
            {
                ToolTip = "Bật/tắt kết nối để Claude (Desktop/Code) trên máy này đọc và chỉnh model Revit đang mở qua MCP.",
            };
            ToggleBridgeCommand.Button = panel.AddItem(buttonData) as PushButton;

            // ExternalEvent phai tao trong API context -> tao san o day, chi mo cong khi bam nut.
            BridgeServer.Initialize();
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            BridgeServer.Stop();
            return Result.Succeeded;
        }
    }

    // Nut "Ket noi Claude": bat/tat cau noi TCP (BridgeServer). Mac dinh TAT - chi mo
    // cong khi nguoi dung chu dong bam nut.
    [Transaction(TransactionMode.Manual)]
    public class ToggleBridgeCommand : IExternalCommand
    {
        internal static PushButton? Button;

        public Result Execute(ExternalCommandData commandData, ref string message, Autodesk.Revit.DB.ElementSet elements)
        {
            try
            {
                if (BridgeServer.IsRunning)
                {
                    BridgeServer.Stop();
                    UpdateButton();
                    TaskDialog.Show("Kết nối Claude", "Đã TẮT kết nối Claude.");
                    return Result.Succeeded;
                }

                BridgeServer.Start(commandData.Application.Application.VersionNumber);
                UpdateButton();
                TaskDialog.Show("Kết nối Claude",
                    $"Đã BẬT kết nối Claude tại 127.0.0.1:{BridgeServer.Port}.\n\n" +
                    $"File kết nối: {BridgeServer.ConnectionFilePath}\n\n" +
                    "Mở Claude Desktop / Claude Code trên máy này (đã cấu hình MCP server 'revit') " +
                    "rồi hỏi, ví dụ: \"Thống kê thép trong model Revit đang mở\".");
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.Message;
                return Result.Failed;
            }
        }

        private static void UpdateButton()
        {
            if (Button != null)
                Button.ItemText = BridgeServer.IsRunning ? "Ngắt\nClaude" : "Kết nối\nClaude";
        }
    }
}
