# Kết nối Claude ↔ Revit (MCP)

Cho phép Claude (Claude Desktop hoặc Claude Code **chạy trên cùng máy Windows với Revit**) đọc và chỉnh model Revit đang mở: tra cứu phần tử và parameter, thống kê thép, chọn/zoom phần tử, gán giá trị parameter, và **chạy lệnh "Vẽ tất cả thép" thân hầm**.

Hỗ trợ **Revit 2024** (.NET Framework 4.8) và **Revit 2027** (.NET 10).

## 1. Kiến trúc

```
Claude Desktop / Claude Code
        │  MCP (stdio)
        ▼
ClaudeRevitMCP/revit_mcp_server.py          (Python, chạy trên máy anh/chị)
        │  TCP 127.0.0.1:48884, 1 dòng JSON / lệnh, có token
        ▼
Add-in TEDI_ClaudeBridge (trong Revit)      (TEDI_Ham_chui_model/TEDI_ClaudeBridge/)
        │  ExternalEvent → thread chính của Revit
        ▼
Revit API (Document, Transaction ...)
```

Vì sao lại thiết kế như vậy:

| Quyết định | Lý do |
|---|---|
| **Add-in riêng**, tách khỏi `TEDI_Ham_chui_model` | Project chính build `net10.0-windows` cho Revit 2027 nên **không load được trong Revit 2024** (.NET Framework 4.8). Cầu nối build ra 2 bản: `net48` cho 2024 và `net10.0-windows` cho 2027. |
| **ExternalEvent** | Revit API chỉ được gọi trên thread chính của Revit. Luồng TCP chỉ đưa yêu cầu vào hàng đợi; Revit thực thi khi đang rảnh. Nếu đang mở hộp thoại hoặc lệnh khác, yêu cầu sẽ báo timeout sau 60 giây. |
| **Chỉ nghe trên 127.0.0.1 + token ngẫu nhiên** | Máy khác trong mạng LAN không kết nối được. Token đổi mỗi lần bật và được ghi vào `%APPDATA%\TEDI-Ham_chui\claude_bridge.json`, chỉ user Windows hiện tại đọc được. |
| **Mặc định TẮT** | Cổng chỉ được mở khi bấm nút **Kết nối Claude**. Bấm lần nữa để ngắt. |
| **Newtonsoft.Json 13** | Revit cũng tự nạp bản này, nên tránh xung đột DLL trên .NET Framework. |

## 2. Cài đặt (làm 1 lần, trên máy Windows có Revit)

### 2.1 Build và cài add-in

Yêu cầu: Visual Studio 2022 (17.14 trở lên, để mở được `.slnx`) hoặc .NET SDK.

```bat
cd <thư mục repo>\TEDI_Ham_chui_model\TEDI_ClaudeBridge

:: Chỉ Revit 2024 (không cần .NET 10 SDK):
dotnet build -c Release -f net48

:: Cả Revit 2024 và 2027 (cần .NET 10 SDK):
dotnet build -c Release
```

Sau khi build xong, add-in tự được copy tới:

- `%APPDATA%\Autodesk\Revit\Addins\2024\TEDI_ClaudeBridge.addin`
- `%APPDATA%\Autodesk\Revit\Addins\2024\TEDI_ClaudeBridge\TEDI_ClaudeBridge.dll` và `Newtonsoft.Json.dll`

> **Revit đang mở thì phải tắt và mở lại**, vì Revit chỉ nạp add-in lúc khởi động. Nếu xuất hiện hộp thoại bảo mật, chọn **Always Load**.

### 2.2 Cài MCP server (Python 3.10+)

```bat
cd <thư mục repo>\ClaudeRevitMCP
pip install -r requirements.txt
```

### 2.3 Khai báo cho Claude

**Claude Code** (terminal):

```bat
claude mcp add revit -- python "<thư mục repo>\ClaudeRevitMCP\revit_mcp_server.py"
```

**Claude Desktop**: sửa `%APPDATA%\Claude\claude_desktop_config.json` rồi khởi động lại Claude Desktop:

```json
{
  "mcpServers": {
    "revit": {
      "command": "python",
      "args": ["D:\\TEDI-Ham_chui\\ClaudeRevitMCP\\revit_mcp_server.py"]
    }
  }
}
```

(Thay đường dẫn bằng vị trí repo thật trên máy. Trong JSON phải dùng `\\`.)

## 3. Sử dụng

1. Mở model trong Revit 2024. Vào tab **TEDI Claude** → bấm **Kết nối Claude**. Hộp thoại sẽ báo cổng đang dùng.
2. Hỏi Claude, ví dụ:
   - "Kiểm tra kết nối Revit" → `revit_ping`
   - "Model đang mở có những category nào, bao nhiêu phần tử?"
   - "Thống kê thép theo đường kính cho đốt cống tôi đang chọn" → `revit_get_rebar_summary(selection_only=true)`
   - "Liệt kê các Generic Model có tên chứa 'Ham'" → `revit_list_elements`
   - "Đổi Comments của phần tử 123456 thành 'Đã kiểm tra'" → `revit_set_parameters` (Claude sẽ hỏi xác nhận trước)
3. Làm xong, bấm **Ngắt Claude**.

## 4. Danh sách lệnh (tool)

| Tool | Tác dụng | Thay đổi model? |
|---|---|---|
| `revit_ping` | Phiên bản Revit, tên model đang mở | Không |
| `revit_get_document_info` | Tên và đường dẫn file, đơn vị chiều dài, view hiện hành, danh sách Level | Không |
| `revit_list_categories` | Các category có phần tử, kèm số lượng | Không |
| `revit_get_selection` | Các phần tử đang chọn | Không |
| `revit_list_elements` | Lọc theo category (`OST_Rebar`, `OST_GenericModel`… hoặc tên hiển thị), tên, view hiện hành | Không |
| `revit_get_element` | Toàn bộ parameter (instance/type), vị trí và bounding box (mm) | Không |
| `revit_get_rebar_summary` | Số thanh, tổng chiều dài (m), khối lượng danh nghĩa (kg) theo loại thanh | Không |
| `revit_select_elements` | Chọn và zoom tới các phần tử | Chỉ đổi selection |
| `revit_set_parameters` | Gán parameter trong 1 Transaction; chỉ cần 1 giá trị lỗi là hủy cả lô; hoàn tác được bằng Ctrl+Z | **Có** |
| `revit_get_draw_all_rebar_settings` | Thông số mặc định (mm) của lệnh Vẽ tất cả thép; cho biết model đã có RebarShape `Rebar_21` chưa | Không |
| `revit_draw_all_rebar` | Vẽ thép thân hầm cho các đốt đang chọn (hoặc `host_ids`), có thể ghi đè thông số | **Có** |

Quy ước đơn vị:

- Tọa độ và chiều dài hình học trả về theo **mm**.
- Parameter có 2 giá trị: `value` là chuỗi hiển thị theo đơn vị dự án, `raw` là đơn vị nội bộ của Revit (feet, radian).
- Khi gán giá trị cho `revit_set_parameters`:
  - Số được hiểu theo **đơn vị hiển thị của dự án** (ví dụ mm).
  - Chuỗi như `"2500 mm"` được Revit tự phân tích.
- Khối lượng thép danh nghĩa tính theo `π·d²/4 × L × 7850 kg/m³`, với `d` = `BarNominalDiameter`. Chỉ tính đối tượng `Rebar`, không tính Area/Path Reinforcement. Chỉ dùng để kiểm tra nhanh; bảng thống kê thép chính thức vẫn lập theo schedule của dự án.

## 5. Vẽ tất cả thép qua Claude

Lệnh `revit_draw_all_rebar` chạy **đúng logic** của nút "Vẽ tất cả thép" trong add-in chính: bridge link trực tiếp các file `Models/*.cs`, không sao chép code. Thông số và hàm `Run()` nằm trong `Models/RebarAllInOneSettings.cs`, được dùng chung cho cả form WPF và Claude.

Trình tự:

1. Claude gọi `revit_get_draw_all_rebar_settings` và đưa bảng thông số cho anh/chị xác nhận hoặc sửa. Bảng gồm:
   - Lớp bảo vệ: `CoverMm`
   - Đường kính và khoảng cách: S1/F1/H1, S2/F2, S4/F4/H2, S6/F6/H3, S5
   - `VuonMm`
   - Hai hằng số hiệu chỉnh của Rebar_21
2. Claude gọi `revit_draw_all_rebar`. Trong Revit, anh/chị **pick 3 mặt cho từng đốt**:
   1. Mặt bằng (đáy hoặc nắp)
   2. Mặt đứng (tường trái hoặc phải)
   3. Mặt cạnh (đầu đốt)

   Bấm Esc để hủy; khi hủy ở bước pick thì chưa có thanh thép nào được tạo. Lệnh chờ tối đa 30 phút.
3. Kết quả trả về gồm:
   - Báo cáo của từng nhóm thép
   - Thống kê các thanh **vừa tạo** theo loại thanh (số thanh, chiều dài, khối lượng danh nghĩa)
   - Thông số đã dùng

> **Revit 2024 và `Rebar_21`:** file `Rebar_21.rfa` trong repo được lưu bằng **Revit 2027**, nên Revit 2024 không load được (Revit không cho mở family lưu bằng phiên bản mới hơn). Trên Revit 2024, model phải **có sẵn RebarShape `Rebar_21` tạo bằng Revit 2024**. Nếu chưa có, lệnh sẽ báo lỗi **trước khi** yêu cầu pick, để không vẽ dở dang. Model mẫu `SampleModels/HamChui_KM77+633.rvt` cũng là file 2027.

> Mỗi nhóm thép commit trong một Transaction riêng: S4/F4/H2 + đai C → Rebar_21 (S2/F2) → S1/F1/H1 → S5. Nếu một nhóm lỗi giữa chừng, các nhóm đã chạy xong vẫn được giữ lại, và thông báo lỗi sẽ cho biết đã tạo bao nhiêu đối tượng Rebar. Muốn hoàn tác thì bấm Ctrl+Z cho từng bước.

> Để lệnh chạy được trên Revit 2024, việc tạo thanh thép không móc dùng hàm `RebarCommon.CreateFromCurvesNoHooks`:
> - Revit 2025 trở lên dùng `BarTerminationsData`.
> - Revit 2024 dùng overload cũ, hook = `null`. Hằng biên dịch `REVIT2024` chỉ bật khi build bản `net48`.

## 6. Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| Không thấy tab **TEDI Claude** | Chưa khởi động lại Revit sau khi build; hoặc thiếu `TEDI_ClaudeBridge.addin` trong `Addins\2024`; hoặc bấm nhầm "Do not load" ở hộp thoại bảo mật. |
| Claude báo "Không thấy …claude_bridge.json" | Chưa bấm **Kết nối Claude**, hoặc đã tắt/đóng Revit. |
| Claude báo "Không kết nối được Revit" | Revit đã đóng nhưng file kết nối còn sót lại. Mở Revit rồi bấm lại nút. |
| "Revit không phản hồi trong 60 giây" | Revit chưa **bắt đầu** xử lý lệnh trong 60 giây vì đang mở hộp thoại hoặc chạy lệnh khác (ví dụ form **Vẽ tất cả thép**). Đóng hộp thoại đó rồi hỏi lại. Khi lệnh đã bắt đầu (ví dụ đang chờ pick mặt), thời gian chờ là 30 phút. |
| "Model chưa có RebarShape 'Rebar_21'…" | Xem mục 5: cần RebarShape `Rebar_21` tạo bằng đúng phiên bản Revit đang dùng. |
| "Sai token" | Đã tắt/bật lại cầu nối trong lúc Claude đang gọi lệnh. Gọi lại là được, vì MCP server đọc file kết nối mới ở mỗi lần gọi. |
| Cổng 48884 đã bị chiếm | Add-in tự thử các cổng 48884–48893. Có thể đặt cổng khác bằng biến môi trường `TEDI_REVIT_BRIDGE_PORT` trước khi mở Revit. |
