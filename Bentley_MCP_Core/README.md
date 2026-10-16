# Bentley MCP Core: phần dùng chung cho MCP của các sản phẩm nền MicroStation

Thư mục này chứa phần dùng chung cho các MCP server điều khiển phần mềm Bentley nền
MicroStation/OpenRoads bằng Claude:

| Sản phẩm | Thư mục | Bản đã nhắm | Tiền tố tool | Add-in / key-in | Cổng mặc định |
|---|---|---|---|---|---|
| OpenTunnel Designer 2026 | [`OpenTunnel_MCP/`](../OpenTunnel_MCP) | 26.00.00.83 | `otd_` | `OTDMcpBridge` / `OTDMCP` | 8765 |
| OpenBridge Designer 2026 | [`OpenBridge_MCP/`](../OpenBridge_MCP) | 26.00.00.142 | `obd_` | `OBDMcpBridge` / `OBDMCP` | 8766 |

Mỗi sản phẩm dùng cổng, file discovery và biến môi trường riêng, nên **chạy song song được trên
cùng một máy**. Sửa một lỗi ở thư mục này là áp dụng cho mọi sản phẩm Bentley.

> **Phân tầng:** phần *không phụ thuộc hãng* (HTTP loopback + token, hàng đợi UI thread, script Roslyn, chụp màn hình, dò API,
> client Python, đăng ký tool) nằm ở [`Mcp_Common`](../Mcp_Common/README.md) và cũng được dùng bởi Navisworks. Thư mục này chỉ
> còn phần **riêng của MicroStation/OpenRoads**: session/level/element/EC/key-in/hình học và đặc trưng tiết diện.

## 1. Kiến trúc

```
┌──────────────────────┐  stdio (MCP)  ┌───────────────────────┐  HTTP 127.0.0.1:<port>  ┌──────────────────────────────────────┐
│ Claude Desktop/Code  │ ────────────► │ otd-mcp / obd-mcp     │ ──────────────────────► │ <AddInName>.dll (add-in .NET)        │
│ (LLM)                │ ◄──────────── │ (Python, dùng         │   header X-MCP-Token    │ chạy BÊN TRONG OTD / OBD             │
└──────────────────────┘               │  bentley_mcp_core)    │                         │  ├─ MainThread dispatcher            │
                                       └───────────┬───────────┘                         │  ├─ DgnPlatformNET / MstnPlatformNET │
                                                   │ đọc port + token                    │  ├─ EC (DgnECManager)                │
                                                   ▼                                     │  ├─ COM Interop: CadInputQueue       │
                                %LOCALAPPDATA%\<OTDMcp|OBDMcp>\bridge.json ◄──── ghi ────│  └─ Roslyn C# scripting              │
                                                                                         └──────────────────────────────────────┘
```

### Cấu trúc mã nguồn
```
Bentley_MCP_Core/
├── bridge/                      C# riêng của MicroStation (namespace BentleyMcp)
│   ├── BentleyMcp.Core.props    MSBuild: import Mcp_Common + tham chiếu DLL Bentley
│   ├── BridgeAddIn.cs           điểm vào add-in (AddIn.Run; tên lấy từ ProductInfo của từng sản phẩm)
│   ├── KeyinCommands.cs         <KEYIN> START | STOP | STATUS
│   ├── BentleyHandlers.cs       RegisterAll(): đăng ký handler Bentley + script (biến Session, ActiveModel, App…) + Notify
│   ├── Infrastructure/Mstn.cs   truy cập session/model/COM, đổi đơn vị UOR ↔ mét
│   └── Handlers/                session, level, element, EC, key-in, hình học
├── python/                      package bentley_mcp_core
│   └── src/bentley_mcp_core/    common_tools (tool riêng MicroStation), sections, guide
└── scripts/build_bridge.ps1     dò runtime .NET, build và cài add-in (được script của sản phẩm gọi)
```
Project của mỗi sản phẩm chỉ có `ProductInfo.cs` (namespace `McpBridge`), `commands.xml` và `.csproj` (import `BentleyMcp.Core.props`).
Hạ tầng trung lập (`MainThread`, `BridgeHost`, `ScriptHandlers`, `ViewHandlers`, `ApiHandlers`…) lấy từ `Mcp_Common/bridge`.

### Vì sao chọn "add-in C# trong sản phẩm + MCP Python"?

| Tiêu chí | Add-in C# + MCP Python (**đã chọn**) | MicroStation Python API | MCP .NET nhúng in-process |
|---|---|---|---|
| Gọi API .NET của OpenRoads/OpenTunnel/OpenBridge, EC | ✅ đầy đủ | ⚠️ hạn chế | ✅ |
| Chạy mọi lệnh ribbon (key-in, data point, reset) | ✅ | ✅ | ✅ |
| Chạy code tuỳ ý không cần build lại | ✅ Roslyn | ✅ | ✅ |
| Cách ly lỗi: MCP lỗi không làm sập sản phẩm | ✅ 2 tiến trình | ✅ | ❌ |
| Phụ thuộc phiên bản SDK MCP / runtime .NET của sản phẩm | Thấp | Thấp | Cao |

**Nguyên tắc kỹ thuật cốt lõi:** API MicroStation **không thread-safe**. Mọi request HTTP được đưa
vào hàng đợi, và một `WinForms.Timer` (tick trên main thread nhờ vòng lặp thông điệp Win32 của
MicroStation) lấy ra thực thi. Nếu gọi API từ thread khác thì chương trình có thể crash hoặc làm
hỏng file DGN.

### Ba lớp công cụ ("dùng hết toàn bộ công cụ")

| Lớp | Cơ chế | Phạm vi |
|---|---|---|
| **A. Tool có kiểu** | handler C# viết sẵn và tính toán Python | file/model/level/element, **thuộc tính EC** (nơi OBM/OTD lưu đối tượng cầu, tunnel), thống kê EC class, đùn khối, polyline, chụp màn hình, đặc trưng tiết diện |
| **B. Key-in + input queue** | `CadInputQueue.SendKeyin / SendDataPoint / SendReset` | **mọi lệnh trên ribbon**, kể cả lệnh không có API công khai: tương đương người dùng gõ/click |
| **C. C# script** | Roslyn biên dịch và chạy trong sản phẩm, tham chiếu mọi assembly đang nạp | mọi API .NET (CifNET, SDK OpenBridge/OpenTunnel, ECObjects…). Dò API trước bằng `<p>_explore_api` |

## 2. Tool dùng chung (tiền tố `otd_` hoặc `obd_`)

| Tool | Mô tả |
|---|---|
| `status` | trạng thái bridge, file/model/level active, đơn vị, runtime |
| `open_file`, `save_file` | mở/lưu DGN |
| `list_models`, `list_levels`, `ensure_level` | model và level |
| `query_elements`, `get_element` | lọc element; chi tiết và toàn bộ thuộc tính EC |
| `ec_summary`, `find_by_ec_class` | thống kê EC class có trong model; tìm element theo class (đối tượng OBM/OTD native) |
| `get_selection`, `select_elements`, `delete_elements` | selection set / xoá |
| `send_keyins`, `send_data_point`, `send_reset`, `get_cexpression` | điều khiển mọi lệnh |
| `draw_polyline`, `create_extrusion` | vẽ line string/shape; đùn tiết diện 2D bất kỳ (outer + holes) |
| `section_properties` | A, trọng tâm, Ix/Iy/Ixy, mômen chính, W, r của tiết diện đa giác có lỗ |
| `capture_view` | chụp cửa sổ (PNG) để Claude "nhìn" kết quả |
| `explore_api`, `run_csharp` | dò API .NET bằng reflection; chạy C# script |
| `bridge_methods` | chẩn đoán |

**Quy ước:** toạ độ tính bằng **mét** theo hệ toạ độ hiển thị (đã trừ Global Origin); kích thước
tiết diện/cấu kiện tính bằng **mm**.

## 3. Biến môi trường (`<P>` = `OTD_MCP_` hoặc `OBD_MCP_`)

| Biến | Nơi đặt | Ý nghĩa |
|---|---|---|
| `<P>PORT` | máy chạy sản phẩm | cổng bridge |
| `<P>ENABLE_SCRIPTS=0` | máy chạy sản phẩm | tắt `run_csharp` |
| `<P>DISCOVERY` | cả hai phía | đường dẫn file discovery khác mặc định |
| `<P>URL` + `<P>TOKEN` | MCP server | bỏ qua file discovery |

## 4. Bảo mật

- Bridge chỉ bind `127.0.0.1`, nên máy khác trong mạng không truy cập được.
- Token ngẫu nhiên 256-bit được sinh mỗi lần khởi động và lưu trong `%LOCALAPPDATA%` (chỉ user
  hiện tại đọc được). So sánh token theo thời gian hằng.
- `run_csharp` có quyền như chính sản phẩm. Nếu không cần, tắt bằng `<P>ENABLE_SCRIPTS=0`.
- Tool ghi/xoá được gắn annotation `destructiveHint`, nên client MCP sẽ hỏi xác nhận.

## 5. Trạng thái kiểm thử và lưu ý khi build lần đầu

- **Python:** `Mcp_Common` 6 test, `Bentley_MCP_Core` 5, OTD 17, OBD 22. Đã chạy qua trên `mcp` 2.2. Trên `mcp`
  1.30, các test gọi tool in-process bị bỏ qua (`mcp.Client` chỉ có từ bản 2.x), còn lại đều qua;
  việc đăng ký tool trên 1.30 được kiểm thử khói riêng. Chạy test: `uv run --extra dev pytest`
  trong từng thư mục `python/` hoặc `server/`.
- **Add-in C#:** viết theo API MicroStation CONNECT/2024+ nhưng **chưa được build** với DLL Bentley,
  vì môi trường phát triển không có OTD/OBD. Nếu lần build đầu báo lỗi, khả năng cao nằm ở các chữ
  ký API dưới đây (đã gom vào ít chỗ; sửa một lần là áp dụng cho cả hai sản phẩm):
  - `ModelInfo.UorPerMeter / UorPerMaster / GlobalOrigin`, `new ElementId(ref long)` → `bridge/Infrastructure/Mstn.cs`
  - `CurveVector.CreateLinear`, `CurvePrimitive.CreateChildCurveVector`, `DgnExtrusionDetail`,
    `DraftingElementSchema.ToElement` → `bridge/Handlers/GeometryHandlers.cs`
  - `DgnECManager.Manager.GetElementProperties`, `IECArrayValue`, `SelectionSetManager.AddElement/EmptyAll`
    → `bridge/Handlers/ElementHandlers.cs`, `EcHandlers.cs`
  - `AddIn.OnUnloading` → `bridge/BridgeAddIn.cs`
  - `Bentley.MstnPlatformNET.InteropServices.Utilities.ComApp` → `bridge/BentleyHandlers.cs`
- **Biên dịch thử trên stub (mới):** `Mcp_Common/tools/csharp-check/check.sh` biên dịch cả lõi Bentley, OTD, OBD bằng Mono
  trên stub SDK. Nó xác nhận mạch lạc nội bộ sau lần tách `Mcp_Common`, **không** kiểm chứng chữ ký API Bentley thật.
- Script C# đã biên dịch sẽ nằm lại trong bộ nhớ đến khi tắt chương trình (giới hạn của .NET khi
  không dùng AssemblyLoadContext riêng). Với vài trăm lần chạy thì không đáng kể.
