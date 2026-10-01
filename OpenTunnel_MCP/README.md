# OpenTunnel MCP — điều khiển Bentley OpenTunnel Designer 2026 bằng Claude

MCP server cho phép Claude (Claude Desktop / Claude Code) đọc, tạo và điều khiển mô hình trong
**OpenTunnel Designer 2026 (26.00.00.83)**, bao gồm mọi lệnh trên ribbon, không riêng các API đã
được bọc sẵn.

## 1. Kiến trúc

```
┌──────────────────────┐  stdio (MCP)  ┌──────────────────┐ HTTP 127.0.0.1:8765 ┌─────────────────────────────────────┐
│ Claude Desktop/Code  │ ────────────► │ otd-mcp (Python) │ ──────────────────► │ OTDMcpBridge.dll (add-in .NET)      │
│ (LLM)                │ ◄──────────── │ server/          │  token X-OTD-Token  │ chạy BÊN TRONG OpenTunnel Designer  │
└──────────────────────┘               └──────────────────┘                     │  ├─ MainThread dispatcher           │
                                                │ đọc port + token               │  ├─ DgnPlatformNET / MstnPlatformNET│
                                                ▼                                │  ├─ COM Interop: CadInputQueue      │
                                 %LOCALAPPDATA%\OTDMcp\bridge.json ◄──── ghi ────│  └─ Roslyn C# scripting             │
                                                                                 └─────────────────────────────────────┘
```

### Vì sao chọn "add-in C# trong OTD + MCP Python"?

| Tiêu chí | Add-in C# + MCP Python (**đã chọn**) | MicroStation Python API | MCP .NET nhúng in-process |
|---|---|---|---|
| Gọi API .NET của OpenRoads/OpenTunnel (`Bentley.CifNET.*`, EC) | ✅ đầy đủ | ⚠️ hạn chế, phụ thuộc binding Python | ✅ |
| Chạy mọi lệnh ribbon (key-in, data point, reset) | ✅ | ✅ | ✅ |
| Chạy code tuỳ ý không cần build lại | ✅ Roslyn | ✅ | ✅ |
| Cách ly lỗi: MCP lỗi không làm sập OTD | ✅ 2 tiến trình | ✅ | ❌ chung tiến trình |
| Phụ thuộc phiên bản SDK MCP / .NET của OTD | Thấp | Thấp | Cao (SDK MCP C# phải khớp runtime OTD) |
| Trùng ngôn ngữ C# với add-in Revit hiện có của repo | ✅ | ❌ | ✅ |

**Nguyên tắc kỹ thuật cốt lõi:** API MicroStation/DgnPlatform **không thread-safe**. Mọi
request HTTP vì vậy được đưa vào hàng đợi, và một `WinForms.Timer` (tick trên main thread nhờ
vòng lặp thông điệp Win32 của MicroStation) lấy ra thực thi. Nếu gọi API từ thread khác thì OTD
có thể crash hoặc làm hỏng file DGN.

### Ba lớp công cụ ("dùng hết toàn bộ công cụ")

| Lớp | Cơ chế | Phạm vi |
|---|---|---|
| **A. Tool có kiểu** | handler C# viết sẵn | đọc file/model/level/element, **toàn bộ thuộc tính EC** (nơi OTD lưu dữ liệu tunnel), tạo polyline, khối đùn, hầm hộp, chụp màn hình |
| **B. Key-in + input queue** | `CadInputQueue.SendKeyin / SendDataPoint / SendReset` | **mọi lệnh trên ribbon OTD** (tunnel, civil, MicroStation), kể cả lệnh không có API công khai: tương đương người dùng gõ/click |
| **C. C# script** | Roslyn biên dịch và chạy trong OTD, tham chiếu mọi assembly đang nạp | mọi API .NET: `Bentley.CifNET` (alignment, corridor), OpenTunnel SDK, ECObjects… Dò API trước bằng `otd_explore_api` |

## 2. Danh sách tool MCP

| Tool | Mô tả |
|---|---|
| `otd_status` | trạng thái bridge, file/model/level active, đơn vị, runtime |
| `otd_open_file`, `otd_save_file` | mở/lưu DGN |
| `otd_list_models`, `otd_list_levels`, `otd_ensure_level` | model và level |
| `otd_query_elements` | lọc element (level, loại, mô tả), phân trang, bao khung (m) |
| `otd_get_element` | chi tiết và toàn bộ thuộc tính EC của 1 element |
| `otd_get_selection`, `otd_select_elements`, `otd_delete_elements` | selection set / xoá |
| `otd_send_keyins`, `otd_send_data_point`, `otd_send_reset` | điều khiển mọi lệnh OTD |
| `otd_get_cexpression` | đọc biến hệ thống MicroStation |
| `otd_draw_polyline` | line string / shape (m) |
| `otd_create_extrusion` | đùn tiết diện 2D bất kỳ (outer + holes) theo trục |
| `otd_create_box_culvert` | hầm chui / cống hộp 1 hoặc nhiều khoang, có vút; trả về khối lượng bê tông; `dry_run` |
| `otd_capture_view` | chụp cửa sổ OTD (PNG) để Claude "nhìn" kết quả |
| `otd_explore_api` | dò assembly/type/member .NET đang nạp (ví dụ lọc theo "Tunnel") |
| `otd_run_csharp` | chạy C# script trong OTD |
| `otd_bridge_methods` | chẩn đoán |

Resource `otd://guide` là hướng dẫn chiến lược cho LLM (quy ước đơn vị, key-in nền tảng, mẫu script).

**Quy ước:** toạ độ luôn tính bằng **mét** theo hệ toạ độ hiển thị (đã trừ Global Origin). Bridge
quy đổi sang UOR qua `ModelInfo.UorPerMeter`, nên kết quả không phụ thuộc master unit của file
seed. Kích thước tiết diện tính bằng **mm**.

## 3. Cài đặt

### 3.1 Yêu cầu
- Windows và OpenTunnel Designer 2026 (26.00.00.83).
- .NET SDK 8+ (dùng để build; với target net48 cần thêm .NET Framework 4.8 Developer Pack).
- Python ≥ 3.10 và [uv](https://docs.astral.sh/uv/) (khuyến nghị).

### 3.2 Build và cài add-in bridge
```powershell
cd OpenTunnel_MCP\scripts
.\build_bridge.ps1 -DetectOnly     # dò thư mục cài, runtime .NET (net48 hay net8), DLL Bentley
.\build_bridge.ps1                 # build + copy vào %LOCALAPPDATA%\OTDMcp\bin
```
Script tự xác định target framework: có `*.runtimeconfig.json` cạnh exe thì là .NET 8+, có
`*.exe.config` thì là .NET Framework 4.8. Build tay:
```powershell
dotnet build bridge\OTDMcpBridge -c Release -p:OtdInstallDir="C:\...\OpenTunnelDesigner\" -p:OtdTargetFramework=net48
```

Thêm vào file cấu hình user của OTD (ví dụ `Personal.ucf` hoặc `.cfg` của WorkSpace):
```
MS_ADDINPATH > C:/Users/<user>/AppData/Local/OTDMcp/bin/
MS_DGNAPPS   > OTDMcpBridge
```
Mở OTD và một file DGN. Nếu không dùng `MS_DGNAPPS`, gõ key-in `mdl load OTDMcpBridge`. Các
key-in của add-in: `OTDMCP STATUS | START | STOP`.

### 3.3 Cài MCP server
```powershell
cd OpenTunnel_MCP\server
uv sync            # hoặc: pip install -e .
uv run otd-mcp     # thử chạy (stdio): Ctrl+C để thoát
```

**Claude Desktop**, file `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "opentunnel": {
      "command": "uv",
      "args": ["--directory", "D:\\TEDI-Ham_chui\\OpenTunnel_MCP\\server", "run", "otd-mcp"]
    }
  }
}
```
**Claude Code:**
```powershell
claude mcp add opentunnel -- uv --directory D:\TEDI-Ham_chui\OpenTunnel_MCP\server run otd-mcp
```

### 3.4 Biến môi trường
| Biến | Nơi đặt | Ý nghĩa |
|---|---|---|
| `OTD_MCP_PORT` | máy chạy OTD | cổng bridge (mặc định 8765) |
| `OTD_MCP_ENABLE_SCRIPTS=0` | máy chạy OTD | tắt `otd_run_csharp` |
| `OTD_MCP_DISCOVERY` | cả hai phía | đường dẫn file discovery khác mặc định |
| `OTD_MCP_URL` + `OTD_MCP_TOKEN` | MCP server | bỏ qua file discovery |

## 4. Ví dụ dùng với Claude

> "Kiểm tra OTD đang mở file nào, liệt kê các level và đếm số solid trên mỗi level."

> "Dựng hầm chui 2 khoang, khẩu độ 2×(4,0×3,5) m, bản nắp 450, bản đáy 500, tường biên 400,
> tường giữa 350, vút 200×200, từ (512340.0, 1234560.0, 12.50) đến (512340.0, 1234602.0, 12.08),
> level HamChui_BeTong. Báo khối lượng bê tông rồi chụp màn hình."

> "Tìm API OpenTunnel đang nạp liên quan tới 'Tunnel', rồi viết script liệt kê các tunnel trong file."

## 5. Ghi chú kỹ thuật cho `otd_create_box_culvert`

- **Điểm chèn** là tim mặt dưới bản đáy tại hai đầu đoạn hầm. Toạ độ z của start/end lấy theo cao
  độ đáy móng (cao độ đáy trong trừ đi chiều dày bản đáy).
- **`section_plane="vertical"` (mặc định):** tiết diện nằm trong mặt phẳng thẳng đứng, đùn theo
  trục có dốc, cho ra lăng trụ xiên. Tường đứng thẳng đúng như ván khuôn thi công. Thể tích bằng
  diện tích × **chiều dài bằng**.
- **`"perpendicular"`:** tiết diện vuông góc trục 3D, thể tích bằng diện tích × chiều dài 3D. Dùng
  cho hầm dốc lớn hoặc kết cấu đúc sẵn đặt theo dốc. Với độ dốc dọc i ≤ 5 %, chênh lệch thể tích
  giữa hai cách chỉ vào khoảng ≤ 0,13 % (tỉ số độ dài 1/cos α).
- Diện tích bê tông = B_out·H_out − n·(B·H − c_tren² − c_duoi²), trong đó mỗi vút 45° có diện tích c²/2.
- Tool chỉ dựng hình học và tính khối lượng. Kiểm toán kết cấu (TCVN 11823-12:2017 "Kết cấu vùi
  và áo hầm", tương đương AASHTO LRFD Section 12) vẫn thực hiện trong Midas Civil hoặc bảng tính riêng.

## 6. Bảo mật

- Bridge chỉ bind `127.0.0.1`, nên máy khác trong mạng không truy cập được.
- Token ngẫu nhiên 256-bit được sinh mỗi lần khởi động và lưu trong `%LOCALAPPDATA%` (chỉ user
  hiện tại đọc được). So sánh token theo thời gian hằng.
- `otd_run_csharp` có quyền như chính OTD. Nếu không cần, tắt bằng `OTD_MCP_ENABLE_SCRIPTS=0`.
- Tool ghi/xoá được gắn annotation `destructiveHint`, nên client MCP sẽ hỏi xác nhận.

## 7. Trạng thái kiểm thử và lưu ý khi build lần đầu

- **Python server:** có 22 test (hình học tiết diện, khối lượng, client HTTP, token refresh, gọi
  tool MCP in-process qua một bridge giả lập). Đã chạy qua trên `mcp` 1.30 và 2.2:
  `uv run --extra dev pytest`.
- **Add-in C#:** viết theo API MicroStation CONNECT/2024+ nhưng **chưa được build** với DLL Bentley,
  vì môi trường phát triển không có OTD. Lần build đầu trên máy có OTD 2026, nếu báo lỗi thì khả
  năng cao nằm ở các chữ ký API dưới đây (đã gom vào ít chỗ để dễ sửa):
  - `ModelInfo.UorPerMeter / UorPerMaster / GlobalOrigin`, `new ElementId(ref long)` → `Infrastructure/Mstn.cs`
  - `CurveVector.CreateLinear`, `CurvePrimitive.CreateChildCurveVector`, `DgnExtrusionDetail`,
    `DraftingElementSchema.ToElement` → `Handlers/GeometryHandlers.cs`
  - `DgnECManager.Manager.GetElementProperties`, `SelectionSetManager.AddElement/EmptyAll` → `Handlers/ElementHandlers.cs`
  - `AddIn.OnUnloading` → `BridgeAddIn.cs`
  Gửi log build để sửa đúng theo SDK của bản 26.00.00.83.
- Script C# đã biên dịch sẽ nằm lại trong bộ nhớ OTD đến khi tắt chương trình (giới hạn của .NET khi
  không dùng AssemblyLoadContext riêng). Với vài trăm lần chạy thì không đáng kể.

## 8. Hướng phát triển
- Tool alignment/lý trình qua `Bentley.CifNET` (lấy toạ độ theo lý trình và đùn hầm theo tuyến
  cong) sau khi dò API trên máy thật bằng `otd_explore_api`.
- Đọc `Form_Input.xlsx` (dùng chung với add-in Revit `TEDI_Ham_chui_model`) để dựng hầm hàng loạt.
- Bọc các lệnh OpenTunnel hay dùng thành tool có kiểu, sau khi có danh sách key-in chính xác từ OTD.
