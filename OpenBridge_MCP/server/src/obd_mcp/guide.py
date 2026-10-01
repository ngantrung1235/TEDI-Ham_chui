"""Huong dan rieng cua OpenBridge (ghep sau phan chung trong resource obd://guide)."""

BRIDGE_GUIDE = r"""
## 6. Riêng OpenBridge Designer
OpenBridge Designer = OpenBridge Modeler (OBM) + OpenRoads Designer + liên kết phân tích (LEAP Bridge,
RM Bridge). Có HAI loại đối tượng trong DGN:

| Loại | Tạo bằng | Đặc điểm |
|---|---|---|
| Đối tượng OBM "thông minh" (cầu, nhịp/unit, trụ/mố, dầm, bản, gối...) | lệnh OBM trên ribbon → obd_send_keyins (+ data point), hoặc API qua obd_run_csharp | Có quan hệ tham số với tuyến, xuất sang LEAP/RM Bridge, báo cáo OBM |
| Khối hình học tham số (dầm, bản, trụ) của MCP này | obd_create_girders / obd_create_deck_slab / obd_create_pier | Solid DGN thuần, nhanh cho phương án/khối lượng/phối cảnh, KHÔNG tự cập nhật theo tuyến |

Khảo sát mô hình OBM có sẵn:
1. obd_ec_summary → xem các EC class có trong model (tên schema/class do OBM đặt — KHÔNG đoán).
2. obd_find_by_ec_class(class_name=<tên tìm được>) → đọc thuộc tính (tên cầu, lý trình trụ, loại dầm...).
3. Dò API OBM: obd_explore_api(assembly_filter="Bridge").

## 7. Tool hình học cầu (đơn vị: mm cho kích thước, m cho toạ độ)
- obd_create_girders: dầm I tham số (kiểu AASHTO/PCI, dầm I DƯL), 1 hoặc nhiều dầm song song;
  điểm chèn = TIM ĐÁY DẦM tại 2 đầu dầm. Trả về A, yb, yt, Ix, Sb, St; có thể kèm tiết diện liên hợp
  (b_eff, chiều dày bản, n = E_bản/E_dầm). dry_run=True để chỉ tính.
- obd_create_deck_slab: bản mặt cầu dày đều, dốc ngang 2 mái/1 mái; điểm chèn = đỉnh mặt bản tại crown.
- obd_create_pier: trụ bệ + n cột (tròn/chữ nhật) + xà mũ; điểm chèn = tim đáy bệ; trả về khối lượng.
- obd_section_properties: đặc trưng hình học tiết diện bất kỳ (hộp, T, Super-T nhập theo toạ độ...).

Kiểm toán kết cấu (TCVN 11823:2017 / AASHTO LRFD) KHÔNG nằm trong các tool này — dùng LEAP/RM Bridge,
Midas Civil hoặc bảng tính; MCP hỗ trợ dựng hình, khối lượng và đặc trưng tiết diện đầu vào.
"""
