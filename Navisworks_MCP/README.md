# Navisworks MCP: điều khiển Autodesk Navisworks Manage 2025 bằng Claude

MCP server cho phép Claude (Claude Desktop / Claude Code) đọc cây mô hình, lọc theo thuộc tính BIM, chọn/ẩn/tô màu, quản
lý viewpoint và selection set, tạo và chạy **Clash Detective**, xuất báo cáo va chạm. Việc gì chưa có tool riêng thì làm
được bằng C# chạy trong Navisworks.

> Hạ tầng bridge (HTTP, hàng đợi UI thread, script C#, chụp màn hình) nằm ở [`Mcp_Common`](../Mcp_Common/README.md).

```
┌──────────────────┐ stdio ┌─────────────────────┐ HTTP 127.0.0.1:8767 ┌──────────────────────────────────┐
│ Claude Desktop/  │ ────► │ nw-mcp (Python)     │ ──────────────────► │ NwMcpBridge.dll — plugin .NET    │
│ Claude Code      │ ◄──── │ server/             │  X-MCP-Token        │ CHẠY TRONG Navisworks (net48)    │
└──────────────────┘       └─────────┬───────────┘                     │  ├ UI-thread dispatcher          │
                                     │ đọc port+token                  │  ├ Autodesk.Navisworks.Api       │
                                     ▼                                 │  └ Roslyn: biên dịch C# tại chỗ  │
                     %LOCALAPPDATA%\NwMcp\bridge.json ◄── ghi ─────────│  (Clash, viewpoint, màu, tệp…)   │
                                                                       └──────────────────────────────────┘
```

## 1. Hai cách cài đặt tính năng — và vì sao

| Cách | Dùng cho | Ưu | Nhược |
|---|---|---|---|
| **C# đã biên dịch sẵn** (`bridge/NwMcpBridge`) | doc info, duyệt cây (`tree`), tìm kiếm (`search`), thuộc tính (`get_item`), vùng chọn | nhanh, chỉ dùng API Navisworks mình **chắc chắn nhất** | cần build lại khi sửa |
| **Snippet C# chạy lúc runtime** (`server/src/nw_mcp/snippets.py`) | Clash Detective, TimeLiner, viewpoint, selection set, màu/độ trong suốt, ẩn/hiện, mở/lưu file, chụp viewport | tên lớp/hàm API khác giữa các bản chỉ làm **hỏng đúng tool đó** (lỗi biên dịch có diagnostic), sửa ngay trong file Python, **không cần build lại plugin** | mỗi lần gọi biên dịch Roslyn (~0,3–1,5 s) |

Lý do: API Navisworks khá lớn và tên lớp (đặc biệt Clash/TimeLiner) khác nhau giữa các bản; mình viết khi không có SDK 2025
để đối chiếu. Cách chia này đảm bảo **lỗi sai API không làm plugin ngừng nạp**, và có đường sửa nhanh: `nw_explore_api` để dò
tên đúng trong máy bạn, rồi `nw_run_csharp` để thử, rồi cập nhật snippet.

## 2. Tool MCP (27)

| Nhóm | Tool |
|---|---|
| Tài liệu / cây | `nw_status`, `nw_tree`, `nw_search`, `nw_get_item`, `nw_get_selection`, `nw_select` |
| Tệp | `nw_open_file`, `nw_save_file` |
| Hiển thị | `nw_set_visibility` (hide / show / isolate / reset_all), `nw_set_appearance` (màu, trong suốt, reset) |
| Khung nhìn | `nw_list_viewpoints`, `nw_save_viewpoint`, `nw_apply_viewpoint`, `nw_focus_selection`, `nw_capture_view` |
| Selection set | `nw_list_selection_sets`, `nw_create_selection_set`, `nw_select_selection_set` |
| Clash Detective | `nw_clash_list_tests`, `nw_clash_create_test`, `nw_clash_run_test`, `nw_clash_results`, `nw_clash_report` (CSV/HTML) |
| TimeLiner | `nw_timeliner_tasks` (chưa kiểm chứng) |
| Mở rộng | `nw_explore_api` (dò API .NET bằng reflection), `nw_run_csharp` (script C# trong Navisworks), `nw_bridge_methods` |

Resource `nw://guide` hướng dẫn mô hình dữ liệu, selector và quy trình.

### Selector và `ref`
- **`ref`** = đường dẫn chỉ số trong cây mô hình, ví dụ `0/3/12`. Navisworks .NET API không có ID số ổn định cho `ModelItem`
  nên dùng cách này; ổn định chừng nào chưa append/xoá model hay refresh file nguồn.
- **Selector** (dùng cho chọn, ẩn/hiện, tô màu, selection set, clash):
  ```json
  {"refs": ["0/3/12"]}   |   {"selection": true}   |
  {"where": [{"category": "Item", "property": "Name", "op": "contains", "value": "Dầm"}],
   "class_name": "Geometry", "geometry_only": true, "scope_ref": "0/3", "max_items": 5000}
  ```
  `op`: equals, not_equals, contains, starts_with, ends_with, regex, exists, not_exists, gt, gte, lt, lte (nhiều điều kiện = AND).
  Điều kiện `equals` đầu tiên có `category` chạy bằng Search native của Navisworks (nhanh); phần còn lại duyệt cây nên
  chậm hơn trên model lớn, hãy thu hẹp bằng `scope_ref`, `geometry_only`, `max_scan`.
- Toạ độ, bbox, khoảng cách trả về bằng **mét** (bridge nhân hệ số theo đơn vị tài liệu).

## 3. Cài đặt

### 3.1 Yêu cầu
- Windows; Navisworks Manage 2025 (Navisworks 2024 trở lên dùng .NET Framework 4.8).
- .NET SDK 8+ để build (hoặc Visual Studio có .NET Framework 4.8 targeting pack).
- Python ≥ 3.10 và [uv](https://docs.astral.sh/uv/) (khuyến nghị).
- Giữ nguyên cấu trúc repo: `Navisworks_MCP/` nằm cạnh `Mcp_Common/`.

### 3.2 Build và cài plugin
Script đọc shortcut `C:\Users\Public\Desktop\Navisworks Manage 2025.lnk` để tìm thư mục cài:
```powershell
cd Navisworks_MCP\scripts
.\build_bridge.ps1 -DetectOnly        # tìm thư mục cài, phiên bản, các DLL Autodesk.Navisworks.*
.\build_bridge.ps1                    # build + chép vào <thư mục cài>\Plugins\NwMcpBridge\   (cần PowerShell Admin)
.\build_bridge.ps1 -Mode Bundle       # hoặc cài dạng bundle vào %APPDATA%\Autodesk\ApplicationPlugins (không cần Admin)
```
Khởi động lại Navisworks. Plugin **tự bật** khi chương trình mở (`EventWatcherPlugin`). Kiểm tra: tab **Add-ins ▸ MCP Bridge**
(hiện trạng thái), hoặc file `%LOCALAPPDATA%\NwMcp\bridge.json` và `bridge.log`.

> Nếu mọi lệnh (trừ `ping`) báo "Main thread không phản hồi": bấm **Add-ins ▸ MCP Bridge** một lần. Lệnh này chạy trên UI
> thread thật và gắn lại hàng đợi.

### 3.3 Cài MCP server
```powershell
cd Navisworks_MCP\server
uv sync                  # tự cài mcp-bridge-common từ ..\..\Mcp_Common\python
uv run nw-mcp            # thử chạy (stdio)
# Không có uv:  pip install -e ..\..\Mcp_Common\python -e .
```
**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{ "mcpServers": { "navisworks": {
    "command": "uv",
    "args": ["--directory", "D:\\TEDI-Ham_chui\\Navisworks_MCP\\server", "run", "nw-mcp"] } } }
```
**Claude Code:** `claude mcp add navisworks -- uv --directory D:\TEDI-Ham_chui\Navisworks_MCP\server run nw-mcp`

Biến môi trường: `NW_MCP_PORT` (8767), `NW_MCP_ENABLE_SCRIPTS=0` (tắt `nw_run_csharp` và mọi tính năng dùng snippet),
`NW_MCP_DISCOVERY`, `NW_MCP_URL` + `NW_MCP_TOKEN`.

## 4. Ví dụ

> "Cho biết Navisworks đang mở file nào, có mấy model, đơn vị gì. Rồi liệt kê 3 phần tử hình học đầu tiên kèm toàn bộ
> thuộc tính để mình xem tên các trường."

> "Chọn tất cả phần tử có tab Item, thuộc tính Layer chứa 'MEP' và ẩn mọi thứ khác, rồi chụp viewport."

> "Tạo selection set 'KetCau' (Layer = 'STR') và 'MEP' (Layer chứa 'MEP'). Tạo clash test 'KC-MEP' loại hard, dung sai 5 mm
> giữa hai nhóm, chạy ngay. Xuất danh sách va chạm trạng thái New ra D:\bao_cao\kc_mep.csv."

> "Tô đỏ, trong suốt 0,6 toàn bộ phần tử trong kết quả clash đầu tiên rồi lưu viewpoint 'Clash 001'."

## 5. Trạng thái kiểm chứng — đọc trước khi build lần đầu

| Hạng mục | Đã làm | Chưa làm được |
|---|---|---|
| Python server (27 tool, selector, báo cáo CSV/HTML, thử nhiều biến thể `using`, chụp viewport rồi dự phòng) | 36 test, qua trên mcp 1.30 và 2.2 | — |
| Cú pháp mọi snippet C# | kiểm bằng parser tree-sitter (test tự động) | kiểu và tên API (cần Roslyn + DLL Navisworks) |
| Plugin C# | biên dịch bằng Mono trên **stub** API (`Mcp_Common/tools/csharp-check`) — mạch lạc nội bộ | **chưa build với `Autodesk.Navisworks.Api.dll` thật** |
| Tương tác với Navisworks thật | — | toàn bộ: không có Navisworks trong môi trường phát triển |

Những chỗ nhiều khả năng cần chỉnh khi chạy thật (đã cô lập để dễ sửa):
- `NwModel.cs`: `ModelItem.Parent/Children/DescendantsAndSelf/PropertyCategories`, `Document.Models.RootItems`. Các thuộc tính chỉ để
  hiển thị (tên file model, đơn vị, GUID, bbox) đọc bằng reflection nên sai tên chỉ mất trường đó, không vỡ build.
- `NwSearch.cs`: `Search`, `SearchCondition.HasPropertyByDisplayName(...).EqualValue(VariantData.FromDisplayString(...))` — nếu lỗi
  lúc chạy sẽ tự rơi về duyệt cây.
- `ModelItem.Equals`: `ref` dựa vào `Equals` để tìm chỉ số con; có dự phòng so khớp theo (tên, GUID).
- Clash Detective / TimeLiner / viewpoint / màu / tệp: toàn bộ ở `snippets.py` (lỗi hiện thành `errors[]` của đúng tool).
- Đường dẫn plugin: `Plugins\NwMcpBridge\NwMcpBridge.dll`. Dạng bundle (`-Mode Bundle`) phụ thuộc `SeriesMin/Max` trong
  `PackageContents.xml` (mặc định `Nw22`, thư mục `v22` theo tài liệu APS cho 2025; chưa kiểm chứng) nên mặc định dùng `Plugins\`.

**Khi gặp lỗi:** gửi log build (`dotnet build`) hoặc phần `errors[]` của tool. Dòng lỗi cho biết ngay tên API cần sửa.

## 6. Giới hạn
- Navisworks **không có key-in/lệnh ribbon gọi từ API**; chỉ làm được những gì API công khai cho phép (rất rộng, nhưng không phải tất cả).
- Lệnh chạy trên UI thread và **chặn giao diện** khi đang thực thi; tránh duyệt toàn cây model rất lớn nhiều lần.
- Không tự lưu file; `nw_save_file` chỉ chạy khi được gọi.
- `nw_run_csharp` có quyền như chính Navisworks; tắt bằng `NW_MCP_ENABLE_SCRIPTS=0`. Bridge chỉ nghe `127.0.0.1`, có token.
