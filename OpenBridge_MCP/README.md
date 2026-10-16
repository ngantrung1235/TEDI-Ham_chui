# OpenBridge MCP: điều khiển Bentley OpenBridge Designer 2026 bằng Claude

MCP server cho phép Claude (Claude Desktop / Claude Code) đọc, tạo và điều khiển mô hình trong
**OpenBridge Designer 2026 (OpenBridgeDesignerx64 26.00.00.142)**, gồm OpenBridge Modeler (OBM),
OpenRoads Designer và mọi lệnh trên ribbon.

> Kiến trúc, danh sách tool dùng chung, bảo mật và lưu ý build nằm ở
> [`Bentley_MCP_Core/README.md`](../Bentley_MCP_Core/README.md). Phần lõi này dùng chung với
> [`OpenTunnel_MCP`](../OpenTunnel_MCP), và hai MCP chạy song song được.

```
OpenBridge_MCP/
├── bridge/OBDMcpBridge/   ProductInfo.cs (tên, cổng 8766, key-in OBDMCP), commands.xml, .csproj
├── server/                package obd_mcp: server.py, shapes.py (dầm/bản/trụ), guide.py
└── scripts/build_bridge.ps1
```

## 1. Hai cách làm việc với mô hình cầu

| | Đối tượng OBM native (cầu, unit, trụ/mố, dầm, bản, gối…) | Khối tham số của MCP này |
|---|---|---|
| Tạo bằng | lệnh OBM trên ribbon qua `obd_send_keyins` (+ `obd_send_data_point`), hoặc API qua `obd_run_csharp` | `obd_create_girders`, `obd_create_deck_slab`, `obd_create_pier` |
| Đọc bằng | `obd_ec_summary` → `obd_find_by_ec_class` → `obd_get_element` | `obd_query_elements` theo level |
| Ưu điểm | gắn tham số với tuyến; xuất sang LEAP Bridge / RM Bridge; báo cáo OBM | nhanh, chủ động hình học; trả về ngay đặc trưng tiết diện và khối lượng |
| Hạn chế | cần đúng key-in/API của OBM (dò trên máy thật, **không đoán**) | solid DGN thuần, không tự cập nhật khi đổi tuyến |
| Dùng cho | hồ sơ thiết kế chính thức, liên kết phân tích | nghiên cứu phương án, khối lượng sơ bộ, phối cảnh, kiểm tra nhanh |

## 2. Tool MCP

Gồm **toàn bộ tool dùng chung** với tiền tố `obd_` (`obd_status`, `obd_ec_summary`,
`obd_find_by_ec_class`, `obd_send_keyins`, `obd_section_properties`, `obd_run_csharp`…), xem bảng
ở README lõi, cộng thêm:

| Tool | Mô tả |
|---|---|
| `obd_create_girders` | dầm I tham số (kiểu AASHTO/PCI, dầm I BTCT DƯL), 1 hoặc nhiều dầm song song; trả về A, y_b, y_t, I_x, S_b, S_t; tuỳ chọn tiết diện **liên hợp** với bản mặt cầu; khối lượng bê tông |
| `obd_create_deck_slab` | bản mặt cầu dày đều, dốc ngang 2 mái hoặc 1 mái (siêu cao), crown lệch tâm |
| `obd_create_pier` | trụ bệ + n cột (tròn/chữ nhật) + xà mũ, xoay theo góc phương vị; khối lượng bệ/cột/xà mũ, cao độ |

Mọi tool dựng hình đều có `dry_run=True`: chỉ tính, không vẽ. Resource `obd://guide` là hướng dẫn
chiến lược cho LLM.

## 3. Cài đặt

### 3.1 Yêu cầu
- Windows và OpenBridge Designer 2026 (26.00.00.142).
- .NET SDK 8+ (dùng để build; với target net48 cần thêm .NET Framework 4.8 Developer Pack).
- Python ≥ 3.10 và [uv](https://docs.astral.sh/uv/) (khuyến nghị).
- Giữ nguyên cấu trúc repo: `OpenBridge_MCP/` phải nằm cạnh `Bentley_MCP_Core/` và `Mcp_Common/`.

### 3.2 Build và cài add-in bridge
```powershell
cd OpenBridge_MCP\scripts
.\build_bridge.ps1 -DetectOnly     # dò thư mục cài, runtime .NET (net48 hay net8), DLL Bentley, DLL "*Bridge*"
.\build_bridge.ps1                 # build + copy vào %LOCALAPPDATA%\OBDMcp\bin
# Nếu cài ở ổ khác:  .\build_bridge.ps1 -InstallDir "D:\Bentley\...\OpenBridgeDesigner"
```
Build tay:
```powershell
dotnet build bridge\OBDMcpBridge -c Release -p:BentleyInstallDir="C:\...\OpenBridgeDesigner\" -p:BentleyTargetFramework=net48
```
Thêm vào file cấu hình user của OBD (ví dụ `Personal.ucf` hoặc `.cfg` của WorkSpace):
```
MS_ADDINPATH > C:/Users/<user>/AppData/Local/OBDMcp/bin/
MS_DGNAPPS   > OBDMcpBridge
```
Mở OBD và một file DGN. Nếu không dùng `MS_DGNAPPS`, gõ key-in `mdl load OBDMcpBridge`. Các key-in
của add-in: `OBDMCP STATUS | START | STOP`.

### 3.3 Cài MCP server
```powershell
cd OpenBridge_MCP\server
uv sync            # tự cài cả bentley-mcp-core từ ..\..\Bentley_MCP_Core\python
uv run obd-mcp     # thử chạy (stdio): Ctrl+C để thoát
# Không có uv:  pip install -e ..\..\Mcp_Common\python -e ..\..\Bentley_MCP_Core\python -e .
```
**Claude Desktop**, file `%APPDATA%\Claude\claude_desktop_config.json` (khai báo cả hai MCP):
```json
{
  "mcpServers": {
    "openbridge": {
      "command": "uv",
      "args": ["--directory", "D:\\TEDI-Ham_chui\\OpenBridge_MCP\\server", "run", "obd-mcp"]
    },
    "opentunnel": {
      "command": "uv",
      "args": ["--directory", "D:\\TEDI-Ham_chui\\OpenTunnel_MCP\\server", "run", "otd-mcp"]
    }
  }
}
```
**Claude Code:**
```powershell
claude mcp add openbridge -- uv --directory D:\TEDI-Ham_chui\OpenBridge_MCP\server run obd-mcp
```
Biến môi trường: `OBD_MCP_PORT` (mặc định 8766), `OBD_MCP_ENABLE_SCRIPTS`, `OBD_MCP_DISCOVERY`,
`OBD_MCP_URL` + `OBD_MCP_TOKEN` (xem README lõi).

## 4. Ví dụ dùng với Claude

> "Thống kê các EC class trong model cầu đang mở, liệt kê các trụ và lý trình của chúng."

> "Tính đặc trưng tiết diện dầm I cao 1650 (cánh trên 800×180, vút trên 100, bụng 200, cánh dưới
> 650×230, vút dưới 225), liên hợp với bản 200 mm, b_eff = 2400, n = 0,85. Chưa vẽ."

> "Dựng 5 dầm I như trên, khoảng cách 2,4 m, nhịp từ (0, 0, 10.00) đến (33, 0, 10.00), rồi bản mặt
> cầu rộng 12 m dày 200, dốc ngang 2 % hai mái, đỉnh bản tại (0, 0, 11.85) → (33, 0, 11.85). Báo khối lượng."

> "Dựng trụ 3 cột tròn D1200 cách nhau 3,2 m, bệ 9×4×2 m, cột cao 6 m, xà mũ 10×1,8×1,5 m, tim đáy
> bệ tại (100, 200, 5.0), trục ngang trụ hướng 90°."

## 5. Ghi chú kỹ thuật

### 5.1 Dầm I (`obd_create_girders`)
- **Điểm chèn** là tim **đáy dầm** tại hai đầu dầm (không phải tim gối). Nhóm nhiều dầm được rải
  đối xứng sang hai bên trục start→end theo `spacing_mm`, với phương ngang vuông góc hình chiếu bằng của trục.
- Tiết diện gồm 12 đỉnh, mô tả được dầm I kiểu AASHTO Type I–VI, PCI BT, dầm I DƯL 33 m thông dụng.
  Dầm T là trường hợp đặc biệt: đặt `bottom_flange_width = web_thickness`, `bottom_flange_thickness = 0`.
  Tiết diện phức tạp hơn (Super-T, hộp, bản rỗng) thì nhập toạ độ đa giác vào `obd_section_properties`
  / `obd_create_extrusion`.
- **Kiểm chứng:** thuật toán (công thức Green cho đa giác) cho dầm AASHTO Type IV ra A = 789 in²,
  y_b = 24,73 in, I = 260.741 in⁴, trùng với bảng tra PCI Bridge Design Manual.
- **Tiết diện liên hợp:** bản được quy đổi về vật liệu dầm, b_qđ = b_eff · n với n = E_bản/E_dầm
  (bản C30 trên dầm C50 có n ≈ 0,85). Chọn b_eff theo TCVN 11823-4:2017 (tương đương AASHTO LRFD
  4.6.2.6: với dầm trong, lấy bằng khoảng cách dầm). Lớp đệm (haunch) chỉ nâng bản lên, **bỏ qua**
  khi tính độ cứng (thiên về an toàn, theo thông lệ). Kết quả có thêm `St_girder` (W tại đỉnh dầm),
  dùng cho kiểm toán ứng suất giai đoạn khai thác.

### 5.2 Bản mặt cầu (`obd_create_deck_slab`)
- Điểm chèn là **đỉnh mặt bản tại crown**. `left/right_slope_pct` là dốc từ crown ra mép, dương là
  dốc xuống. Siêu cao 1 mái 4 % xuống phía phải nhập là `-4 / 4`, khi đó các đỉnh thẳng hàng ở crown
  được loại bỏ tự động.
- Diện tích = B·t chính xác (bản dày đều theo phương đứng); thể tích = A × chiều dài bằng (`vertical`).

### 5.3 Trụ (`obd_create_pier`)
- Điểm chèn là **tim đáy bệ**. `orientation_deg` là góc phương vị của trục ngang trụ (phương dài
  xà mũ) đo từ +X ngược chiều kim đồng hồ. Trụ vuông góc với cầu có hướng tuyến θ thì nhập θ + 90°.
- Tool kiểm tra cột không chồng nhau và không vượt ra ngoài bệ hoặc xà mũ.
- Khối lượng cột tròn tính theo πD²/4. Khối DGN là đa giác 64 cạnh, diện tích nhỏ hơn khoảng 0,16 %.
- Xà mũ dạng hộp chữ nhật; xà mũ vát đầu hoặc chữ T ngược thì dựng thêm bằng `obd_create_extrusion`.

### 5.4 Phạm vi
Các tool này chỉ dựng hình học, tính khối lượng và đặc trưng tiết diện đầu vào. **Kiểm toán kết cấu**
(TCVN 11823:2017 / AASHTO LRFD: tổ hợp tải trọng, mất mát ứng suất trước, TTGH cường độ/sử dụng)
vẫn làm trong LEAP Bridge, RM Bridge, Midas Civil hoặc bảng tính.

## 6. Hướng phát triển
- Đặt dầm, trụ theo lý trình trên tuyến `Bentley.CifNET`, sau khi dò API trên máy thật bằng `obd_explore_api`.
- Bọc các lệnh OBM hay dùng (tạo cầu, unit, support, girder) thành tool có kiểu, sau khi có danh
  sách key-in hoặc API chính xác từ bản 26.00.00.142.
- Thêm các tiết diện thường dùng ở Việt Nam (Super-T, dầm bản rỗng, hộp) dưới dạng thư viện tham số.
