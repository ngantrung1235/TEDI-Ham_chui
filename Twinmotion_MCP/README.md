# Twinmotion MCP: điều khiển Twinmotion 2026.1 (For Revit) bằng Claude

MCP server cho Claude (Claude Desktop / Claude Code) khởi động, quan sát và thao tác **giao diện** Twinmotion trên chính
máy Windows của bạn.

## 1. Điều cần biết trước: Twinmotion không có API để điều khiển

Mình đã tra cứu (10/2026): **không thấy Twinmotion 2026.1 công bố API script hay giao thức điều khiển từ xa nào**
(ghi chú phát hành 2026.1 chỉ nói về tính năng hình ảnh/nhập mô hình; trên diễn đàn Epic, scripting/API vẫn là *đề nghị* của
người dùng, chưa phải tính năng). Vì vậy khác với Navisworks hay OpenBridge, **không có cầu nối trong tiến trình**. MCP này
điều khiển như một người dùng:

```
Claude ──MCP/stdio──► tm-mcp (Python, chạy trên máy có Twinmotion)
                        ├─ psutil ......... tìm / chạy (qua shortcut .lnk) / đóng tiến trình
                        ├─ Win32 ctypes ... liệt kê & đưa cửa sổ lên trước, SendInput (chuột, phím, Unicode)
                        ├─ Pillow ......... chụp màn hình, vẽ lưới toạ độ, phát hiện màn hình ngừng thay đổi
                        └─ pywinauto ...... (tuỳ chọn) UI Automation
         ◄─ ảnh chụp ─┘      vòng lặp:  tm_screenshot (nhìn) → tm_click/… (làm) → tm_screenshot (kiểm tra)
```

**Hệ quả nên chấp nhận:** chậm hơn API; phụ thuộc bố cục giao diện, độ phân giải, tỉ lệ DPI, ngôn ngữ; không đọc được dữ liệu
cấu trúc (ví dụ danh sách vật liệu) trừ khi nó hiện trên màn hình. Nếu sau này Epic công bố API, nên thay lớp điều khiển
bằng cầu nối thật thay vì mở rộng lớp giao diện này.

## 2. Mối liên hệ với Revit (plugin "For Revit")

Plugin Twinmotion cho Revit đẩy mô hình sang Twinmotion qua **Datasmith Direct Link**; nút *Synchronize* nằm trong Revit.
MCP này **không thao tác Revit**, chỉ lo phía Twinmotion: mở Twinmotion → bạn (hoặc công cụ khác) bấm Synchronize trong
Revit → MCP chờ nhập xong (`tm_wait_stable`) và chụp ảnh kiểm tra. Lưu ý từ tài liệu tương thích của ImagineIT:
- Phiên bản Revit ↔ Twinmotion phụ thuộc **bộ xuất Datasmith** (Revit 2026.4 và 2027 dùng bộ xuất UE 5.6, Twinmotion 2023.1–2026.1
  được liệt kê hỗ trợ; Revit 2026 gốc dùng bộ xuất UE 5.4 với Twinmotion 2025.1). Bảng này do bên thứ ba tổng hợp, hãy đối chiếu
  trang chính thức của Epic/Autodesk.
- Direct Link đồng bộ theo **view đã chọn cho kết nối**, không nhất thiết là view 3D đang mở; lệch view là nguyên nhân phổ biến
  khiến đối tượng bị ẩn/hiện sai.
- Phương án dự phòng: xuất `.udatasmith` từ Revit rồi dùng `tm_find_files` để tìm file mới nhất.

## 3. Tool MCP (20)

| Nhóm | Tool |
|---|---|
| Trạng thái / tiến trình | `tm_status`, `tm_resolve_shortcut`, `tm_launch`, `tm_open_project`, `tm_close`, `tm_list_windows` |
| Cửa sổ | `tm_focus`, `tm_set_window` |
| Nhìn | `tm_screenshot` (lưới toạ độ, đánh dấu điểm, thu nhỏ), `tm_wait_stable` |
| Chuột | `tm_click`, `tm_move`, `tm_drag`, `tm_scroll` |
| Bàn phím | `tm_type_text` (Unicode, gõ được tiếng Việt), `tm_hotkey`, `tm_press` (giữ phím, vd W/A/S/D) |
| UI Automation (tuỳ chọn) | `tm_uia_tree`, `tm_uia_invoke` |
| Tệp | `tm_find_files` (`.tm`, `.udatasmith`, `.fbx`, `.rvt`… mới nhất trước; thêm `png/jpg/mp4` để tìm đầu ra) |

Resource `tm://guide`: hệ toạ độ, an toàn, quy trình Revit→Twinmotion, mẹo bấm.

### Hệ toạ độ
Toạ độ tính từ **góc trên-trái vùng nội dung cửa sổ** (ảnh chụp mặc định), theo pixel vật lý (tiến trình đặt DPI-aware nên
khớp `GetWindowRect`/`SendInput`/ảnh chụp). Ảnh gửi cho Claude có thể bị thu nhỏ (`max_width`): meta kèm `scale`, toạ độ trên
ảnh thu nhỏ chia `scale` ra toạ độ thật; hoặc `max_width=0` lấy ảnh gốc. `grid=100` vẽ lưới có nhãn toạ độ thật.

## 4. An toàn — vì công cụ này chạm vào chuột và bàn phím thật

| Cơ chế | Hành vi |
|---|---|
| Kiểm tra foreground | Chỉ gửi chuột/phím khi cửa sổ foreground là của Twinmotion; tự đưa lên trước, không được thì **huỷ**, không bao giờ gõ vào ứng dụng khác |
| Kiểm tra vùng | Từ chối toạ độ ngoài vùng cửa sổ |
| Chốt an toàn | Con trỏ ở góc trên-trái màn hình (0,0) → mọi lệnh dừng (như pyautogui failsafe) |
| Nhả phím/nút | `drag`, `hotkey`, `press` luôn nhả nút/modifier kể cả khi lỗi giữa chừng |
| Chế độ chỉ-đọc | `TM_MCP_ALLOW_INPUT=0`: chỉ chụp màn hình và đọc trạng thái |
| Đóng cưỡng bức | `tm_close(force=true)` giết tiến trình (mất thay đổi chưa lưu); tắt hẳn bằng `TM_MCP_ALLOW_KILL=0` |
| Annotation MCP | Tool chuột/phím/đóng gắn `destructiveHint` → client hỏi xác nhận |

Giới hạn thật cần biết: **UIPI** của Windows chặn chuột/phím vào cửa sổ chạy quyền cao hơn (Admin) nếu MCP chạy quyền thường;
nên chạy cả hai cùng quyền. Không dùng công cụ này cho màn hình đăng nhập, mật khẩu, khoá bản quyền.

## 5. Cài đặt

Chỉ Python (không build C#), chỉ chạy trên Windows, **cùng máy** với Twinmotion.

```powershell
cd Twinmotion_MCP\scripts
.\setup.ps1             # đọc shortcut, kiểm tra môi trường, uv sync, in cấu hình Claude
.\setup.ps1 -Uia        # cài thêm pywinauto (UI Automation, tuỳ chọn)
```
Shortcut mặc định: `C:\Users\Public\Desktop\Twinmotion 2026.1 For Revit.lnk`. Đổi bằng `TM_SHORTCUT`, hoặc trỏ thẳng
`TM_EXE=...\Twinmotion.exe`. Đọc `.lnk` bằng WScript.Shell (PowerShell); nếu bị chặn thì tự rơi về bộ đọc nhị phân MS-SHLLINK.

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{ "mcpServers": { "twinmotion": {
    "command": "uv",
    "args": ["--directory", "D:\\TEDI-Ham_chui\\Twinmotion_MCP\\server", "run", "tm-mcp"],
    "env": { "TM_SHORTCUT": "C:\\Users\\Public\\Desktop\\Twinmotion 2026.1 For Revit.lnk" } } } }
```
**Claude Code:** `claude mcp add twinmotion -- uv --directory D:\TEDI-Ham_chui\Twinmotion_MCP\server run tm-mcp`

| Biến môi trường | Ý nghĩa |
|---|---|
| `TM_SHORTCUT` | đường dẫn shortcut `.lnk` (mặc định như trên) |
| `TM_EXE` | đường dẫn thẳng tới exe (bỏ qua shortcut) |
| `TM_PROCESS_HINT` | chuỗi con trong tên tiến trình để nhận diện (mặc định `twinmotion`) |
| `TM_MCP_ALLOW_INPUT=0` | chế độ chỉ-đọc |
| `TM_MCP_ALLOW_KILL=0` | cấm `tm_close(force=true)` |

## 6. Ví dụ

> "Kiểm tra Twinmotion đã chạy chưa; nếu chưa thì mở, đợi nhập xong rồi chụp màn hình."

> "Mình vừa bấm Synchronize trong Revit. Đợi Twinmotion nhập xong (tối đa 3 phút) rồi chụp ảnh cho mình kiểm tra mô hình."

> "Xoay camera sang trái khoảng 30° bằng cách kéo chuột phải trong viewport, chụp ảnh, rồi lưu dự án bằng Ctrl+S."

> "Tìm file ảnh/phim mới nhất trong D:\Render sau khi xuất."

## 7. Trạng thái kiểm chứng

| Hạng mục | Đã làm | Chưa làm được |
|---|---|---|
| Logic điều khiển + an toàn (96 test, qua trên mcp 1.30 và 2.2) | bảng phím, hình học toạ độ, đọc `.lnk` (file nhị phân tự dựng theo đặc tả), chụp/lưới/so sánh ảnh, kiểm tra foreground/vùng/failsafe/nhả phím — bằng **backend giả** | — |
| Kiểm tra độ nhạy của test an toàn | cố ý phá 7 cơ chế an toàn, mỗi lần đều có test thất bại | — |
| Lớp Win32 (`winapi.py`) | khai báo đủ `argtypes/restype`, kích thước struct `INPUT/MOUSEINPUT/KEYBDINPUT` = 40/32/24 byte (đúng x64), tách cặp thay thế UTF-16 | **chưa chạy trên Windows thật**; không có Windows trong môi trường phát triển |
| Tương tác với Twinmotion thật | — | toàn bộ: nhận diện tiến trình/cửa sổ, `SendInput` vào viewport Unreal, mở file bằng đối số dòng lệnh, UI Automation |

Điểm nhiều khả năng cần chỉnh khi chạy thật:
- **Chụp màn hình**: dùng `ImageGrab` (chụp màn hình thật) vì viewport DirectX thường cho ảnh đen với `PrintWindow`. Cửa sổ phải
  hiện và không bị che.
- **Kéo chuột trong viewport**: dùng sự kiện chuột *tương đối* (raw input) vì engine Unreal đọc theo raw input; nếu viewport không phản ứng
  hãy báo lại để thử cách khác.
- **`tm_open_project`**: truyền đường dẫn file qua dòng lệnh chưa được xác nhận với bản 2026.1.
- **Nhiều màn hình / DPI khác nhau**: đã đặt PER_MONITOR_AWARE_V2 nhưng chưa thử trên cấu hình hỗn hợp.
