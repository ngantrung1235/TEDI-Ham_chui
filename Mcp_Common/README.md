# Mcp_Common: hạ tầng dùng chung cho các MCP điều khiển phần mềm kỹ thuật

Thư mục này chứa phần **không phụ thuộc hãng** của các MCP server trong repo. Nó chia thành hai lớp: C# chạy trong
phần mềm, và Python chạy ngoài. Mỗi sản phẩm cụ thể chỉ thêm phần riêng của mình.

## 1. Họ MCP trong repo

| Thư mục | Phần mềm (bản đã nhắm) | Cách điều khiển | Tiền tố tool | Cổng |
|---|---|---|---|---|
| [`OpenTunnel_MCP`](../OpenTunnel_MCP) | OpenTunnel Designer 2026 (26.00.00.83) | add-in C# trong phần mềm + Python | `otd_` | 8765 |
| [`OpenBridge_MCP`](../OpenBridge_MCP) | OpenBridge Designer 2026 (26.00.00.142) | add-in C# + Python | `obd_` | 8766 |
| [`Navisworks_MCP`](../Navisworks_MCP) | Navisworks Manage 2025 | plugin .NET (net48) + Python | `nw_` | 8767 |
| [`Twinmotion_MCP`](../Twinmotion_MCP) | Twinmotion 2026.1 (For Revit) | **điều khiển giao diện** (không có API) | `tm_` | không dùng |

```
Mcp_Common/
├── bridge/                          C# trung lập (namespace McpBridge), nhúng vào add-in của từng sản phẩm
│   ├── McpBridge.Common.props       MSBuild: gom mã nguồn + NuGet (Newtonsoft.Json, Roslyn Scripting)
│   ├── Infrastructure/              HTTP loopback + token, hàng đợi main thread, JSON helper P, AssemblyResolver, BridgeHost
│   └── Handlers/                    ScriptHandlers (Roslyn), ViewHandlers (chụp màn hình), ApiHandlers (dò API bằng reflection)
├── python/                          package mcp_bridge_common
│   └── src/mcp_bridge_common/       BridgeClient, ProductConfig, compat (mcp 1.x/2.x), registry (tool chung), testing (bridge giả)
└── tools/csharp-check/              biên dịch thử toàn bộ C# bằng Mono trên stub SDK (xem mục 4)
```

Tầng Bentley (`Bentley_MCP_Core`) và các sản phẩm khác **phụ thuộc vào** thư mục này, không phụ thuộc lẫn nhau.

## 2. Hợp đồng của một add-in sản phẩm

Mỗi sản phẩm có C# tối thiểu gồm:

1. **`McpBridge.ProductInfo`** (`internal static class`): tên, mã, tên add-in, tiền tố biến môi trường, thư mục discovery, cổng
   mặc định, `RegisterProductHandlers(RpcRegistry)` và `Notify(message, detail, isError)`.
2. **Điểm vào của phần mềm** gọi, theo thứ tự: `AssemblyResolver.Install()` → `MainThread.Initialize()` (tại UI thread) →
   `BridgeHost.Start()`. MicroStation dùng `AddIn.Run`; Navisworks dùng `EventWatcherPlugin.OnLoaded`.
3. **Handler riêng**, đăng ký bằng `RpcRegistry.Add(name, onMainThread, description, handler)` trong `RegisterProductHandlers`.
   Các handler gọi API của phần mềm **phải** đánh dấu `onMainThread = true`.
4. (tuỳ chọn) `ScriptHandlers.Register(registry, new ScriptConfig { … })` để mở công cụ chạy C# tuỳ ý với biến toàn cục riêng.

Python tương ứng: tạo `ProductConfig`, rồi `make_tool(mcp, product)` để đăng ký tool có tiền tố, và
`register_generic_tools(mcp, bridge, product)` để có `explore_api`, `run_csharp`, `bridge_methods`, `capture_view`.

## 3. Giao thức bridge (chỉ 127.0.0.1)

```
GET  /health                             → {"ok":true,"name":…,"version":…}        (không cần token)
POST /rpc  {"method":…,"params":{…}}     header X-MCP-Token: <token>
          → {"ok":true,"result":…,"elapsed_ms":…}  |  {"ok":false,"error":{"type","message","detail"}}
```
Token ngẫu nhiên 256-bit, sinh mỗi lần khởi động, ghi cùng cổng vào `%LOCALAPPDATA%\<DiscoveryFolder>\bridge.json`. Client
Python đọc lại file này mỗi lần gọi nên không cần khởi động lại MCP khi phần mềm khởi động lại.

**Nguyên tắc cốt lõi:** API của phần mềm CAD/BIM hầu như **không thread-safe**. Mọi request HTTP vào hàng đợi; một
`WinForms.Timer` (tick trên UI thread nhờ vòng lặp thông điệp Win32) lấy ra chạy. Chạy API từ thread khác có thể làm
phần mềm treo hoặc hỏng file.

## 4. Kiểm chứng (và giới hạn của nó)

- `python -m pytest` trong mỗi thư mục `python/` / `server/`.
- `tools/csharp-check/check.sh` biên dịch thử toàn bộ C# (lõi dùng chung, OTD, OBD, Navisworks) bằng **Mono `mcs`** trên **stub**
  của SDK. Việc này bắt lỗi gõ sai tên, thiếu `using`, sai namespace/kiểu **trong mã của mình**, nhưng **không** kiểm chứng
  chữ ký API thật của Bentley/Autodesk vì stub chỉ là giả định. Qua bước này không có nghĩa build được với DLL thật.
- `mcs` không hỗ trợ cú pháp C# mới (`case … when`, pattern switch…), nên mã tránh các cú pháp đó.
