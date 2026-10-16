"""Huong dan (MCP resource tm://guide) cho LLM dieu khien Twinmotion."""

GUIDE = r"""
# Hướng dẫn điều khiển Twinmotion 2026.1 (For Revit) qua MCP

## 1. Cách hoạt động — và giới hạn
Twinmotion 2026.1 **không có API script hay điều khiển từ xa được công bố**. MCP này điều khiển **giao diện**:
1. `tm_screenshot` → bạn **nhìn** màn hình;  2. `tm_click / tm_drag / tm_type_text / tm_hotkey` → thao tác;
3. `tm_screenshot` lại để **xác nhận**. Không có đường tắt: mọi việc phải qua vòng lặp nhìn → làm → kiểm tra.

Hệ quả cần chấp nhận: chậm hơn API; phụ thuộc bố cục giao diện (độ phân giải, tỉ lệ DPI, ngôn ngữ); không đọc được
dữ liệu cấu trúc (ví dụ danh sách vật liệu) trừ khi nó hiện trên màn hình.

## 2. Hệ toạ độ
- `tm_screenshot(target="main", area="client")` chụp **vùng nội dung** của cửa sổ chính. Toạ độ (0,0) = góc trên-trái của
  ảnh gốc. Meta kèm theo cho biết `width`, `height`, `scale`: nếu ảnh bị thu nhỏ (`max_width`), **toạ độ trên ảnh thu nhỏ
  = toạ độ thật × scale** — hãy chia cho `scale` trước khi click, hoặc đặt `max_width=0` để lấy ảnh gốc.
- Dùng `grid=100` để vẽ lưới có nhãn toạ độ thật lên ảnh → đọc toạ độ chính xác hơn. `mark_x/mark_y` vẽ vòng tròn đỏ
  tại điểm định click để xác nhận trước khi click.
- `target="active"` dùng cho **hộp thoại / menu** của Twinmotion đang ở foreground (toạ độ tính theo cửa sổ đó).

## 3. An toàn (đã cài sẵn)
- Chỉ gửi chuột/phím khi cửa sổ **foreground là của Twinmotion**; tự đưa Twinmotion lên trước, không được thì huỷ.
- Từ chối toạ độ ngoài vùng cửa sổ. **Chốt an toàn**: đưa chuột vào góc trên-trái màn hình (0,0) → mọi lệnh dừng.
- Chế độ chỉ-đọc: đặt `TM_MCP_ALLOW_INPUT=0` → chỉ chụp màn hình/đọc trạng thái.
- `tm_close(force=true)` giết tiến trình, **mất thay đổi chưa lưu** → chỉ làm khi người dùng đồng ý.
- Không nhập mật khẩu/khoá bản quyền; nếu gặp đăng nhập/EULA, dừng lại hỏi người dùng.

## 4. Quy trình thường gặp
**Khởi động**: `tm_status` → `tm_launch` (hoặc `tm_open_project(path)` nếu chưa chạy) → `tm_wait_stable` → `tm_screenshot`.

**Đưa mô hình từ Revit sang (Datasmith Direct Link)** — làm trong Revit, MCP này chỉ lo phía Twinmotion:
1. Mở Twinmotion (`tm_launch`), để cửa sổ chạy nền.
2. Trong Revit: mở **3D view** cần đẩy, dùng nút **Synchronize** (Direct Link) của plugin Twinmotion/Datasmith
   (tab *Twinmotion* hoặc *Datasmith*). Direct Link đồng bộ theo view đang chọn cho kết nối — khác view là nguyên nhân
   phổ biến khiến đối tượng bị ẩn/hiện sai.
3. Quay lại đây: `tm_wait_stable` (đợi nhập xong) → `tm_screenshot` kiểm tra.
- Phương án dự phòng: xuất file `.udatasmith` từ Revit rồi `tm_find_files(folder)` để tìm file mới nhất.
- Bộ plugin Revit↔Twinmotion phụ thuộc phiên bản Revit và bộ xuất Datasmith (xem bảng tương thích của Epic/Autodesk).

**Lưu & xuất hình/phim**: dùng thanh Media của Twinmotion (chụp ảnh, panorama, video, trình chiếu). Với mỗi bước:
chụp màn hình để thấy hộp thoại, chỉnh thông số, bấm Export, `tm_wait_stable(timeout_s=…)` đến khi xong, rồi
`tm_find_files` để xác nhận file đầu ra.

**Điều hướng camera**: kéo chuột trong viewport (`tm_drag`, `button="right"` thường là xoay/nhìn quanh trong chế độ
điều hướng tự do), cuộn (`tm_scroll`) để zoom, giữ phím W/A/S/D/Q/E (`tm_press(key, hold_ms=…)`) để di chuyển.
Phím/nút chính xác phụ thuộc cài đặt điều hướng của người dùng — **thử một lần và chụp ảnh kiểm tra**, đừng giả định.

## 5. Mẹo khi bấm
- Bấm vào giữa nút/mục, không bấm sát mép. Menu đổ xuống: click mở → `tm_screenshot` → click mục.
- Ô nhập: click vào ô → `tm_hotkey("ctrl+a")` → `tm_type_text(giá_trị)` → `tm_press("enter")` hoặc `tab`.
- Hộp thoại mở/lưu file của Windows: `tm_type_text` đường dẫn đầy đủ vào ô tên file rồi `enter`.
- Chữ có dấu tiếng Việt gõ được bằng `tm_type_text` (gửi Unicode, không phụ thuộc bàn phím).
- Hành động mất nhiều giây (nhập, render): luôn `tm_wait_stable` thay vì đoán thời gian.
- `tm_uia_tree` có thể liệt kê nút bấm nếu Twinmotion lộ UI Automation; thường là rất ít — đừng dựa vào nó.
"""
