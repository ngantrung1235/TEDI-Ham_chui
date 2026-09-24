using System;
using System.Collections.Concurrent;
using System.Threading.Tasks;
using Autodesk.Revit.UI;
using Newtonsoft.Json.Linq;

namespace TEDI_ClaudeBridge
{
    // 1 yeu cau tu Claude (qua MCP server -> TCP) cho Revit xu ly.
    internal class BridgeRequest
    {
        public string Method = "";
        public JObject Params = new JObject();
        // Revit bat dau thuc thi (true) hoac server da huy vi cho qua lau (canceled) -
        // ai dat truoc thang, nen khong co chuyen vua bao timeout vua van chay lenh.
        public TaskCompletionSource<bool> Started =
            new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource<JToken?> Completion =
            new TaskCompletionSource<JToken?>(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    // Revit API CHI duoc goi tu thread chinh cua Revit (API context). Luong TCP chay
    // o thread nen nen KHONG duoc dung Document truc tiep: no chi dua request vao hang
    // doi roi Raise() ExternalEvent; Revit se goi Execute() ben duoi tren thread chinh
    // khi ranh (khong co lenh/hop thoai modal nao dang mo), luc do moi thuc thi lenh.
    internal class BridgeEventHandler : IExternalEventHandler
    {
        private readonly ConcurrentQueue<BridgeRequest> _queue = new ConcurrentQueue<BridgeRequest>();

        public void Enqueue(BridgeRequest request) => _queue.Enqueue(request);

        public void Execute(UIApplication app)
        {
            while (_queue.TryDequeue(out BridgeRequest? request))
            {
                // Request da bi huy do het thoi gian cho (Revit ban lau) -> bo qua, KHONG
                // thuc thi muon vi client da nhan loi timeout roi.
                if (!request.Started.TrySetResult(true))
                    continue;

                try
                {
                    request.Completion.TrySetResult(BridgeCommands.Dispatch(app, request.Method, request.Params));
                }
                catch (Exception ex)
                {
                    request.Completion.TrySetException(ex);
                }
            }
        }

        public string GetName() => "TEDI Claude Bridge";
    }
}
