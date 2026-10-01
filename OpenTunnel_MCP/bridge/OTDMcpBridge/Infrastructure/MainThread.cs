using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

namespace OTDMcpBridge.Infrastructure
{
    // Moi API MicroStation/DgnPlatform/OpenRoads deu KHONG thread-safe va phai goi tren
    // main thread. HTTP server chay tren thread pool, nen moi request duoc day vao hang doi
    // nay; WinForms Timer (tick tren main thread nho vong lap thong diep Win32 cua
    // MicroStation) lay ra va thuc thi.
    internal static class MainThread
    {
        private sealed class WorkItem
        {
            public Func<object> Body;
            public readonly TaskCompletionSource<object> Tcs =
                new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
            public int State; // 0 = cho, 1 = dang chay/da chay, 2 = bi huy do timeout
        }

        private static readonly ConcurrentQueue<WorkItem> Queue = new ConcurrentQueue<WorkItem>();
        private static System.Windows.Forms.Timer _timer;
        private static int _mainThreadId = -1;
        private static bool _draining;

        public static bool IsInitialized => _timer != null;
        public static bool IsMainThread => Thread.CurrentThread.ManagedThreadId == _mainThreadId;

        // PHAI goi tu main thread (AddIn.Run hoac key-in handler).
        public static void Initialize()
        {
            if (_timer != null) return;
            _mainThreadId = Thread.CurrentThread.ManagedThreadId;
            _timer = new System.Windows.Forms.Timer { Interval = 25 };
            _timer.Tick += (s, e) => Drain();
            _timer.Start();
        }

        public static object Invoke(Func<object> body, TimeSpan timeout)
        {
            if (IsMainThread) return body();
            if (_timer == null) throw new InvalidOperationException("MainThread chua duoc khoi tao (AddIn.Run chua chay).");

            var item = new WorkItem { Body = body };
            Queue.Enqueue(item);

            if (!item.Tcs.Task.Wait(timeout))
            {
                // Neu chua bat dau thi huy de khong chay "ma" sau khi client da bo cuoc.
                if (Interlocked.CompareExchange(ref item.State, 2, 0) == 0)
                    throw new TimeoutException($"Main thread cua OTD khong phan hoi sau {timeout.TotalSeconds:0}s (dang ban dialog/lenh khac?).");
                // Da chay roi -> doi them cho xong de tra dung ket qua.
                item.Tcs.Task.Wait();
            }
            return item.Tcs.Task.GetAwaiter().GetResult();
        }

        private static void Drain()
        {
            // Chong re-entrancy: handler co the mo dialog/pump message lam Tick goi lai.
            if (_draining) return;
            _draining = true;
            try
            {
                while (Queue.TryDequeue(out WorkItem item))
                {
                    if (Interlocked.CompareExchange(ref item.State, 1, 0) != 0) continue;
                    try { item.Tcs.SetResult(item.Body()); }
                    catch (Exception ex) { item.Tcs.SetException(ex); }
                }
            }
            finally
            {
                _draining = false;
            }
        }
    }
}
