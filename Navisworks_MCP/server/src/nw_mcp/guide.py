"""Huong dan (MCP resource nw://guide) cho LLM dieu khien Navisworks Manage 2025."""

from __future__ import annotations

from mcp_bridge_common import ProductConfig


def nw_guide(product: ProductConfig) -> str:
    return _GUIDE.format(name=product.name, p=product.tool_prefix)


_GUIDE = r"""
# Hướng dẫn điều khiển {name} qua MCP

## 1. Mô hình dữ liệu
- **Cây mô hình**: Document → Model (mỗi file nạp vào/append) → ModelItem lồng nhau (nhóm, layer, instance, geometry).
  Dữ liệu BIM (Revit, IFC...) nằm ở **thuộc tính** của item: các tab như `Item`, `Element`, ... — tên tab/thuộc tính
  phụ thuộc file nguồn nên **luôn đọc mẫu bằng {p}_get_item trước khi lọc**, không đoán tên.
- **ref**: định danh item trong MCP = đường dẫn chỉ số trong cây, ví dụ `0/3/12` (model 0 → con thứ 3 → con thứ 12).
  Ổn định chừng nào cây chưa đổi (không append/xoá model, không refresh file nguồn). Lấy ref từ {p}_tree / {p}_search.
- **Đơn vị**: toạ độ, khoảng cách, bbox trả về bằng **mét**; dung sai nhập bằng mét (bridge tự đổi theo đơn vị tài liệu).

## 2. Selector (dùng cho select, ẩn/hiện, tô màu, selection set, clash...)
Một trong ba dạng:
```json
{{"refs": ["0/3/12", "0/3/13"]}}
{{"selection": true}}
{{"where": [{{"category": "Item", "property": "Name", "op": "contains", "value": "Dầm"}}],
  "class_name": "Geometry", "geometry_only": true, "scope_ref": "0/3", "max_items": 5000}}
```
- `op`: equals | not_equals | contains | starts_with | ends_with | regex | exists | not_exists | gt | gte | lt | lte.
  `gt/lt...` lấy số đầu tiên trong chuỗi hiển thị (vd `"3.50 m"` → 3.5).
- Điều kiện `equals` có `category` đầu tiên dùng Search native của Navisworks (nhanh, có index); các điều kiện còn
  lại và mọi op khác duyệt cây (chậm hơn trên model lớn — hạn chế bằng `scope_ref`, `geometry_only`, `max_scan`).
- Nhiều điều kiện trong `where` là **AND**. Cần OR: gọi {p}_search nhiều lần rồi ghép `refs`.

## 3. Quy trình khuyến nghị
1. {p}_status → file, đơn vị, danh sách model. {p}_tree → xem cấu trúc cấp trên cùng.
2. Lấy mẫu thuộc tính: {p}_search(limit=3, include_properties=True, geometry_only=True) hoặc {p}_get_item.
3. Lọc bằng {p}_search (`where`) → kiểm tra số lượng (`total_matched`).
4. Hành động: {p}_select, {p}_set_visibility, {p}_set_appearance, {p}_create_selection_set, {p}_save_viewpoint.
5. Kiểm tra trực quan: {p}_focus_selection rồi {p}_capture_view.
6. Phối hợp/va chạm: {p}_create_selection_set (hai nhóm A, B) → {p}_clash_create_test → {p}_clash_results →
   {p}_clash_report (CSV/HTML).

## 4. Clash Detective, TimeLiner và các tính năng làm bằng snippet
Clash, viewpoint, tô màu, mở/lưu file, selection set, TimeLiner chạy bằng **snippet C# biên dịch lúc chạy** (không đóng gói
sẵn). Nếu ban Navisworks đặt tên lớp/hàm khác, tool trả lỗi biên dịch **kèm diagnostic** thay vì làm hỏng plugin:
- Dò tên đúng: {p}_explore_api(assembly_filter="Clash") rồi {p}_explore_api(assembly_filter="Autodesk.Navisworks.Clash",
  type_filter="ClashTest", include_members=True).
- Viết lại bằng {p}_run_csharp (biến: Doc, Selected, MetersPerUnit, Resolve(selector), RefOf(item), FromRef(ref),
  Describe(item), Arg<T>(tên), Print(x)).

Mẫu {p}_run_csharp — đếm item theo lớp:
```csharp
Doc.Models.RootItems.SelectMany(r => r.DescendantsAndSelf)
   .GroupBy(i => i.ClassDisplayName).ToDictionary(g => g.Key ?? "?", g => g.Count())
```

## 5. Lưu ý quan trọng
- Mọi lệnh chạy trên UI thread của Navisworks và **chặn giao diện** khi đang chạy: tránh duyệt toàn cây model rất lớn
  nhiều lần; đặt `limit` hợp lý. Timeout mặc định 120 s.
- Nếu mọi lệnh (trừ ping) báo "Main thread không phản hồi": tab Add-ins ▸ **MCP Bridge** một lần để gắn lại UI thread.
- Navisworks không có key-in như MicroStation: lệnh ribbon không gọi được trực tiếp; dùng API (snippet). Với thao tác
  chỉ có trên giao diện, nhờ người dùng làm hoặc dùng công cụ computer-use.
- Mọi thao tác ghi (tô màu, ẩn/hiện, tạo test...) nằm trong phiên làm việc; **không tự lưu** — gọi {p}_save_file khi
  người dùng đồng ý. Có thể Ctrl+Z trong Navisworks.
"""
