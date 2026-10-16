# OpenTunnel MCP: điều khiển Bentley OpenTunnel Designer 2026 bằng Claude

MCP server cho phép Claude (Claude Desktop / Claude Code) đọc, tạo và điều khiển mô hình trong
**OpenTunnel Designer 2026 (26.00.00.83)**, bao gồm mọi lệnh trên ribbon, không riêng các API đã
được bọc sẵn.

> Kiến trúc, danh sách tool dùng chung, bảo mật và lưu ý build nằm ở
> [`Bentley_MCP_Core/README.md`](../Bentley_MCP_Core/README.md). Phần lõi này dùng chung với
> [`OpenBridge_MCP`](../OpenBridge_MCP).

```
OpenTunnel_MCP/
├── bridge/OTDMcpBridge/   ProductInfo.cs (tên, cổng 8765, key-in OTDMCP), commands.xml, .csproj
├── server/                package otd_mcp: server.py, culvert.py (hầm hộp), guide.py
└── scripts/build_bridge.ps1
```

## 1. Tool MCP

Gồm **toàn bộ tool dùng chung** với tiền tố `otd_` (`otd_status`, `otd_query_elements`,
`otd_ec_summary`, `otd_send_keyins`, `otd_run_csharp`…), xem bảng ở README lõi, cộng thêm:

| Tool | Mô tả |
|---|---|
| `otd_create_box_culvert` | hầm chui / cống hộp 1 hoặc nhiều khoang, có vút; trả về khối lượng bê tông; `dry_run` trả thêm đặc trưng hình học tiết diện |

Resource `otd://guide` là hướng dẫn chiến lược cho LLM.

## 2. Cài đặt

### 2.1 Yêu cầu
- Windows và OpenTunnel Designer 2026 (26.00.00.83).
- .NET SDK 8+ (dùng để build; với target net48 cần thêm .NET Framework 4.8 Developer Pack).
- Python ≥ 3.10 và [uv](https://docs.astral.sh/uv/) (khuyến nghị).
- Giữ nguyên cấu trúc repo: `OpenTunnel_MCP/` phải nằm cạnh `Bentley_MCP_Core/` và `Mcp_Common/`.

### 2.2 Build và cài add-in bridge
```powershell
cd OpenTunnel_MCP\scripts
.\build_bridge.ps1 -DetectOnly     # dò thư mục cài, runtime .NET (net48 hay net8), DLL Bentley
.\build_bridge.ps1                 # build + copy vào %LOCALAPPDATA%\OTDMcp\bin
```
Build tay:
```powershell
dotnet build bridge\OTDMcpBridge -c Release -p:BentleyInstallDir="C:\...\OpenTunnelDesigner\" -p:BentleyTargetFramework=net48
```
Thêm vào file cấu hình user của OTD (ví dụ `Personal.ucf` hoặc `.cfg` của WorkSpace):
```
MS_ADDINPATH > C:/Users/<user>/AppData/Local/OTDMcp/bin/
MS_DGNAPPS   > OTDMcpBridge
```
Mở OTD và một file DGN. Nếu không dùng `MS_DGNAPPS`, gõ key-in `mdl load OTDMcpBridge`. Các key-in
của add-in: `OTDMCP STATUS | START | STOP`.

### 2.3 Cài MCP server
```powershell
cd OpenTunnel_MCP\server
uv sync            # tự cài cả bentley-mcp-core từ ..\..\Bentley_MCP_Core\python
uv run otd-mcp     # thử chạy (stdio): Ctrl+C để thoát
# Không có uv:  pip install -e ..\..\Mcp_Common\python -e ..\..\Bentley_MCP_Core\python -e .
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
Biến môi trường: `OTD_MCP_PORT`, `OTD_MCP_ENABLE_SCRIPTS`, `OTD_MCP_DISCOVERY`,
`OTD_MCP_URL` + `OTD_MCP_TOKEN` (xem README lõi).

## 3. Ví dụ dùng với Claude

> "Kiểm tra OTD đang mở file nào, liệt kê các level và đếm số solid trên mỗi level."

> "Dựng hầm chui 2 khoang, khẩu độ 2×(4,0×3,5) m, bản nắp 450, bản đáy 500, tường biên 400,
> tường giữa 350, vút 200×200, từ (512340.0, 1234560.0, 12.50) đến (512340.0, 1234602.0, 12.08),
> level HamChui_BeTong. Báo khối lượng bê tông rồi chụp màn hình."

> "Thống kê các EC class trong model, tìm các đối tượng tunnel và đọc thuộc tính của chúng."

## 4. Ghi chú kỹ thuật cho `otd_create_box_culvert`

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

## 5. Hướng phát triển
- Tool alignment/lý trình qua `Bentley.CifNET` (lấy toạ độ theo lý trình và đùn hầm theo tuyến
  cong) sau khi dò API trên máy thật bằng `otd_explore_api`.
- Đọc `Form_Input.xlsx` (dùng chung với add-in Revit `TEDI_Ham_chui_model`) để dựng hầm hàng loạt.
- Bọc các lệnh OpenTunnel hay dùng thành tool có kiểu, sau khi có danh sách key-in chính xác từ OTD.
