"""Huong dan su dung (MCP resource otd://guide) cho LLM dieu khien OpenTunnel Designer."""

GUIDE = r"""
# Hướng dẫn điều khiển OpenTunnel Designer 2026 qua MCP

## 1. Ba lớp công cụ — chọn lớp thấp nhất đủ dùng
| Lớp | Tool | Dùng khi |
|---|---|---|
| A. Tool có kiểu | otd_query_elements, otd_get_element, otd_create_box_culvert, otd_create_extrusion, otd_draw_polyline, otd_list_levels ... | Đọc/tạo dữ liệu có cấu trúc, kết quả kiểm soát được |
| B. Key-in + input queue | otd_send_keyins, otd_send_data_point, otd_send_reset | Chạy BẤT KỲ lệnh nào trên ribbon OTD (kể cả lệnh tunnel không có API) đúng như người dùng gõ/click |
| C. C# script | otd_explore_api → otd_run_csharp | Cần API .NET sâu (OpenRoads/Civil, OpenTunnel SDK, EC, Element...) |

## 2. Quy ước
- Toạ độ trao đổi qua MCP luôn là **mét** theo hệ toạ độ hiển thị (đã trừ Global Origin).
- Kích thước tiết diện hầm nhập bằng **mm**.
- Key-in được xếp hàng và chỉ chạy SAU khi request trả về → sau khi gửi key-in hãy gọi
  otd_capture_view hoặc otd_get_selection/otd_query_elements để kiểm tra kết quả.
- Mọi thao tác ghi đều có thể Undo trong OTD (key-in `undo`).

## 3. Quy trình khuyến nghị
1. otd_status → xác nhận bridge chạy, file/model active, đơn vị.
2. Khảo sát: otd_list_models, otd_list_levels, otd_query_elements(include_properties=False) rồi
   otd_get_element(id) để đọc thuộc tính EC (tên tunnel, template, lý trình, vật liệu...).
3. Thao tác bằng lớp A; nếu không có tool phù hợp → lớp B (key-in) hoặc C (script).
4. Kiểm tra trực quan: otd_capture_view(fit=True).
5. otd_save_file khi người dùng đồng ý.

## 4. Key-in MicroStation nền tảng (chắc chắn có)
- `fit view extended` — fit toàn bộ view
- `view top`, `view iso` — đổi hướng nhìn view active
- `model active <tên model>` — chuyển model
- `active level <tên level>` — đổi level active
- `choose all` / `choose none` — chọn tất cả / bỏ chọn
- `mdl load <app>` / `mdl unload <app>` — nạp/gỡ ứng dụng
- `undo` / `redo`
- `filedesign` — lưu file

**Key-in riêng của OpenTunnel/OpenRoads**: KHÔNG đoán tên. Cách lấy chính xác:
- Trong OTD: hộp thoại Customize (File ▸ Settings ▸ User ▸ Customize, tên menu có thể khác
  tuỳ bản) — chọn tool trên ribbon sẽ thấy thuộc tính *Key-in* của nó.
- Hoặc chạy tool bằng chuột rồi xem lịch sử trong cửa sổ Key-in.
- Người dùng có thể dán danh sách key-in vào hội thoại để LLM gọi qua otd_send_keyins.

## 5. Mẫu C# script (otd_run_csharp)
Biến có sẵn: `Session`, `ActiveFile`, `ActiveModel`, `App` (COM Interop Application),
`UorPerMeter`, hàm `Print(x)`. Giá trị của biểu thức cuối cùng được trả về.

Đếm element theo loại:
```csharp
ActiveModel.GetGraphicElements()
    .GroupBy(e => e.ElementType.ToString())
    .ToDictionary(g => g.Key, g => g.Count())
```

Dò API OpenTunnel trước khi viết script (KHÔNG đoán tên class):
- otd_explore_api(assembly_filter="Tunnel") → các assembly tunnel đang nạp
- otd_explore_api(assembly_filter="CifNET", type_filter="Alignment", include_members=True)

Dùng reflection trong script khi chưa chắc API:
```csharp
AppDomain.CurrentDomain.GetAssemblies()
    .Select(a => a.GetName().Name)
    .Where(n => n.Contains("Tunnel") || n.Contains("Cif"))
    .OrderBy(n => n)
```

## 6. Hầm chui / cống hộp
otd_create_box_culvert dựng khối bê tông tiết diện hộp (1 hoặc nhiều khoang, có vút) theo
trục thẳng start→end; điểm chèn = tim mặt dưới bản đáy. Dùng dry_run=True để xem trước
khối lượng bê tông mà không vẽ.
"""
