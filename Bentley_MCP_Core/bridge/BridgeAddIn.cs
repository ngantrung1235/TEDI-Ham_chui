using System;
using System.Runtime.CompilerServices;
using Bentley.MstnPlatformNET;
using McpBridge;
using McpBridge.Infrastructure;

namespace BentleyMcp
{
    // Diem vao cua add-in (dung chung cho moi san pham; ten lay tu ProductInfo cua project).
    // Nap trong san pham bang key-in:
    //     mdl load OTDMcpBridge  /  mdl load OBDMcpBridge   (khi DLL nam trong MS_ADDINPATH)
    //     mdl load "D:\...\<AddInName>.dll"
    // Run() chay tren MAIN THREAD cua MicroStation -> day la noi duy nhat duoc phep tao
    // MainThread dispatcher (WinForms Timer gan voi vong lap thong diep cua main thread).
    [AddInAttribute(MdlTaskID = ProductInfo.AddInName, KeyinTree = ProductInfo.AddInName + ".commands.xml")]
    internal sealed class BridgeAddIn : AddIn
    {
        internal static BridgeAddIn Instance { get; private set; }

        private BridgeAddIn(IntPtr mdlDesc) : base(mdlDesc)
        {
            Instance = this;
        }

        protected override int Run(string[] commandLine)
        {
            // Phai cai AssemblyResolve TRUOC khi JIT bat ky method nao tham chieu
            // Newtonsoft.Json / Roslyn (MicroStation co the da nap ban khac cua cac DLL nay).
            AssemblyResolver.Install();
            StartBridge();
            return 0;
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void StartBridge()
        {
            MainThread.Initialize();
            BridgeHost.Start();
        }

        protected override void OnUnloading(UnloadingEventArgs eventArgs)
        {
            BridgeHost.Stop();
            base.OnUnloading(eventArgs);
        }
    }
}
