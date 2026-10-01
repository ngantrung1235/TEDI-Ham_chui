"""Huong dan rieng cua OpenTunnel (ghep sau phan chung trong resource otd://guide)."""

TUNNEL_GUIDE = r"""
## 6. Riêng OpenTunnel
- Đối tượng tunnel/corridor/template được nhận diện qua EC: chạy otd_ec_summary trước, sau đó
  otd_find_by_ec_class với tên class tìm được (KHÔNG đoán tên schema).
- Dò API tunnel: otd_explore_api(assembly_filter="Tunnel").

## 7. Hầm chui / cống hộp
otd_create_box_culvert dựng khối bê tông tiết diện hộp (1 hoặc nhiều khoang, có vút) theo
trục thẳng start→end; điểm chèn = tim mặt dưới bản đáy. Dùng dry_run=True để xem trước
khối lượng bê tông và đặc trưng hình học tiết diện mà không vẽ.
"""
