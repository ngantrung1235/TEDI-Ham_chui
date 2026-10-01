"""Phan chung cua huong dan (MCP resource) cho LLM dieu khien san pham Bentley qua MCP."""

from __future__ import annotations

from .product import ProductConfig

_COMMON = r"""
# Hướng dẫn điều khiển {name} qua MCP

## 1. Ba lớp công cụ — chọn lớp thấp nhất đủ dùng
| Lớp | Tool | Dùng khi |
|---|---|---|
| A. Tool có kiểu | {p}_query_elements, {p}_get_element, {p}_ec_summary, {p}_find_by_ec_class, {p}_create_extrusion, {p}_draw_polyline, {p}_list_levels ... | Đọc/tạo dữ liệu có cấu trúc, kết quả kiểm soát được |
| B. Key-in + input queue | {p}_send_keyins, {p}_send_data_point, {p}_send_reset | Chạy BẤT KỲ lệnh nào trên ribbon (kể cả lệnh không có API) đúng như người dùng gõ/click |
| C. C# script | {p}_explore_api → {p}_run_csharp | Cần API .NET sâu (OpenRoads/Civil, SDK riêng của sản phẩm, EC, Element...) |

## 2. Quy ước
- Toạ độ trao đổi qua MCP luôn là **mét** theo hệ toạ độ hiển thị (đã trừ Global Origin).
- Kích thước tiết diện nhập bằng **mm**.
- Key-in được xếp hàng và chỉ chạy SAU khi request trả về → sau khi gửi key-in hãy gọi
  {p}_capture_view hoặc truy vấn lại để kiểm tra kết quả.
- Mọi thao tác ghi đều có thể Undo (key-in `undo`).

## 3. Quy trình khuyến nghị
1. {p}_status → xác nhận bridge chạy, file/model active, đơn vị.
2. Khảo sát: {p}_list_models, {p}_list_levels, {p}_ec_summary (biết model có đối tượng thông minh nào),
   rồi {p}_find_by_ec_class / {p}_get_element để đọc thuộc tính.
3. Thao tác bằng lớp A; nếu không có tool phù hợp → lớp B (key-in) hoặc C (script).
4. Kiểm tra trực quan: {p}_capture_view(fit=True).
5. {p}_save_file khi người dùng đồng ý.

## 4. Key-in MicroStation nền tảng (chắc chắn có)
- `fit view extended` — fit toàn bộ view
- `view top`, `view iso` — đổi hướng nhìn view active
- `model active <tên model>` — chuyển model
- `active level <tên level>` — đổi level active
- `choose all` / `choose none` — chọn tất cả / bỏ chọn
- `mdl load <app>` / `mdl unload <app>` — nạp/gỡ ứng dụng
- `undo` / `redo`
- `filedesign` — lưu file

**Key-in riêng của {name}**: KHÔNG đoán tên. Cách lấy chính xác:
- Hộp thoại Customize (File ▸ Settings ▸ User ▸ Customize, tên menu có thể khác tuỳ bản) —
  chọn tool trên ribbon sẽ thấy thuộc tính *Key-in* của nó.
- Hoặc chạy tool bằng chuột rồi xem lịch sử trong cửa sổ Key-in.
- Người dùng có thể dán danh sách key-in vào hội thoại để gọi qua {p}_send_keyins.

## 5. Mẫu C# script ({p}_run_csharp)
Biến có sẵn: `Session`, `ActiveFile`, `ActiveModel`, `App` (COM Interop Application),
`UorPerMeter`, hàm `Print(x)`. Giá trị của biểu thức cuối cùng được trả về.

Đếm element theo loại:
```csharp
ActiveModel.GetGraphicElements()
    .GroupBy(e => e.ElementType.ToString())
    .ToDictionary(g => g.Key, g => g.Count())
```

Dò API trước khi viết script (KHÔNG đoán tên class):
- {p}_explore_api(assembly_filter="{asm_hint}") → các assembly riêng của sản phẩm đang nạp
- {p}_explore_api(assembly_filter="CifNET", type_filter="Alignment", include_members=True)
"""


def common_guide(product: ProductConfig, asm_hint: str) -> str:
    return _COMMON.format(name=product.name, p=product.tool_prefix, asm_hint=asm_hint)
