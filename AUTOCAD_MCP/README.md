# AutoCAD MCP – liên kết Claude Code với AutoCAD (mọi phiên bản)

MCP server cho phép **Claude Code trên terminal** (hoặc Claude Desktop) vẽ, đọc, sửa và thống kê bản vẽ AutoCAD
bằng tiếng Việt.

Có 2 chế độ, tự chọn khi kết nối:

| Chế độ | Khi nào dùng | Phạm vi |
|---|---|---|
| **COM** (ActiveX, pywin32) | AutoCAD đang mở trên Windows | **AutoCAD 2000 → 2026**, Civil 3D, Map 3D, Plant 3D…; BricsCAD, ZWCAD, GstarCAD |
| **DXF** (ezdxf) | Không có hoặc không mở AutoCAD, kể cả máy Linux/Mac | Đọc/ghi DXF R12 → 2018; DWG khi có ODA File Converter (miễn phí) |

---

## 1. Vì sao chạy được "mọi phiên bản"

* **Không dùng plugin .NET/ObjectARX**, vì các plugin này phải biên dịch lại cho từng phiên bản (R24 cho 2021–2024, R25 cho 2025–2026…).
* **Dùng COM/ActiveX với *late binding***. Mô hình đối tượng `AcadApplication → Documents → ModelSpace → AddLine/AddLightWeightPolyline…`
  được Autodesk giữ tương thích ngược từ AutoCAD 2000. Late binding (`win32com.client.dynamic`) không phụ thuộc
  type library của một bản cụ thể, nên cùng một mã chạy cho mọi bản.
* **Tìm AutoCAD theo thứ tự ProgID:**
  1. `AutoCAD.Application`: bản mới nhất đã đăng ký;
  2. `AutoCAD.Application.25` → `.15`: từng thế hệ;
  3. các phần mềm tương thích: `BricscadApp.AcadApplication`, `ZWCAD.Application`, `GCAD.Application`.

  Muốn ép một bản, đặt biến môi trường `AUTOCAD_PROGID`, ví dụ `AutoCAD.Application.24` (2021–2024).
* **Các thuộc tính mới có phương án dự phòng**, ví dụ `EffectiveName` (từ 2008) quay về `Name`, và `PlotToFile` với PC3.
* **Lệnh gửi qua `cad_command`** nên dùng tên tiếng Anh có gạch dưới (`_.LINE`, `_.ZOOM _E`), để chạy được trên AutoCAD bản tiếng Việt, Pháp, Nhật…

| Version | Phiên bản | Version | Phiên bản |
|---|---|---|---|
| R15.x | 2000 / 2000i / 2002 | R21.0 | 2017 |
| R16.x | 2004 / 2005 / 2006 | R22.0 | 2018 |
| R17.x | 2007 / 2008 / 2009 | R23.x | 2019 / 2020 |
| R18.x | 2010 / 2011 / 2012 | R24.x | 2021 / 2022 / 2023 / 2024 |
| R19.x, R20.x | 2013–2014, 2015–2016 | R25.x | 2025 / 2026 |

**Hai lỗi COM kinh điển đã được xử lý:**
* Mọi lệnh COM chạy trên **một luồng STA riêng** (`CoInitialize`). Đối tượng COM không dùng được từ luồng khác.
* Khi AutoCAD bận (đang regen, đang mở hộp thoại), COM báo lỗi `RPC_E_CALL_REJECTED` (−2147418111). MCP **tự thử lại** với thời gian chờ tăng dần.

---

## 2. Cài đặt và chạy trên terminal

```powershell
cd D:\Tools\AUTOCAD_MCP
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
Script làm lần lượt: tạo `.venv`, cài thư viện (offline nếu có thư mục `wheels`), chạy test, **đăng ký với Claude Code**
(`claude mcp add autocad …`), rồi thử kết nối.

Sử dụng:
```powershell
# Mở AutoCAD (bản nào cũng được), rồi:
claude
> /mcp                                  # thấy "autocad" connected
> Vẽ mặt cắt cống hộp 4x3.2 m, bản nắp 450, bản đáy 500, tường 400, vát 200, tỉ lệ 1:50
```

Kiểm tra nhanh trên terminal: `.venv\Scripts\python -m autocad_mcp --check`.

| Biến môi trường | Ý nghĩa |
|---|---|
| `AUTOCAD_BACKEND` | `auto` (mặc định) \| `com` \| `dxf` |
| `AUTOCAD_PROGID` | Ép sản phẩm/phiên bản, ví dụ `AutoCAD.Application.24`, `BricscadApp.AcadApplication` |

---

## 3. Danh sách tool (39)

| Nhóm | Tool |
|---|---|
| Kết nối, bản vẽ | `cad_connect`, `cad_status`, `cad_versions`, `doc_new`, `doc_open`, `doc_save` (lưu về bản cũ: `2000_dwg` … `2018_dwg`, `R12_dxf`), `doc_close`, `doc_activate` |
| Layer | `layer_list`, `layer_create` (màu ACI, linetype CENTER/DASHED…, lineweight) |
| Vẽ | `draw_line`, `draw_polyline` (2D/3D), `draw_circle`, `draw_arc`, `draw_text`, `draw_mtext`, `draw_point`, `draw_dimension`, `draw_hatch`, `block_insert` (+ attribute), `draw_table` |
| Truy vấn, sửa | `entities_list` (lọc theo layer, loại, khung), `entity_get`, `entities_transform` (move/rotate/scale/mirror, có copy), `entity_offset`, `entities_set_properties`, `entities_delete`, `block_list` |
| Trích xuất | `block_attributes_extract` (khung tên, bảng cọc, mốc → CSV), `texts_extract`, `quantities_by_layer` (chiều dài, diện tích, số block theo layer) |
| AutoCAD | `cad_command`, `cad_lisp` (trả về kết quả AutoLISP), `sysvar_get`, `sysvar_set`, `zoom_extents`, `plot_pdf` |
| Kiểm tra trực quan | `preview_image`: ảnh PNG trả cho Claude xem (DXF: dựng bằng matplotlib; COM: plot qua `PublishToWeb PNG.pc3`) |
| Chuyên ngành | `draw_box_culvert_section`: mặt cắt cống hộp có vát nách, tô mặt cắt, trục, chuỗi kích thước, tiêu đề, tỉ lệ |

Quy ước: đơn vị là **đơn vị bản vẽ (mm)**, góc tính bằng **độ**, đối tượng xác định bằng **handle**.
Chiều cao chữ trong model = chiều cao trên giấy × tỉ lệ, ví dụ 2,5 mm × 50 = 125.

---

## 4. Bản vẽ chuyên ngành: mặt cắt cống hộp

`draw_box_culvert_section` dùng cùng bộ tham số với tool `build_box_culvert` bên PLAXIS MCP (bên đó tính bằng m), nên một mô hình
tính toán đi kèm được bản vẽ thống nhất:
* **Layer:** `KC_BETONG` (đường bao), `KC_HATCH` (tô ANSI31), `KC_KICHTHUOC`, `KC_TEXT`, `KC_TRUC` (nét CENTER).
* **Kích thước:** chuỗi tường – lòng – tường và tổng bề rộng; chuỗi bản đáy – lòng – bản nắp và tổng chiều cao; hai cạnh vát nách.
* **Trả về** diện tích bê tông trên 1 m dài, dùng để kiểm tra khối lượng.
  Ví dụ 4,0×3,2 m, t = 450/500/400, vát 200: (4,8 × 4,15) − (4,0 × 3,2 − 4 × ½ × 0,2²) = **7,200 m²/m**.

Quy cách nét, chữ tham khảo TCVN 8-20:2002 (nét vẽ) và TCVN 5570:2012 (ký hiệu đường nét, đường trục trong bản vẽ xây dựng).

---

## 5. Ví dụ câu lệnh

```
Mở D:/HoSo/HC_KM77+633.dwg, thống kê chiều dài theo từng layer thép, xuất bảng attribute của block KHUNG_TEN ra CSV.
```
```
Vẽ tim tuyến theo các điểm (0,0) (120000,15000) (250000,10000) trên layer TIM_TUYEN nét CENTER màu đỏ,
rồi offset hai bên 5500 làm mép đường.
```
```
Lưu bản vẽ về định dạng AutoCAD 2010 cho đơn vị bạn dùng bản cũ, rồi in PDF layout hiện hành.
```
```
Đọc toàn bộ text trong khung [0,0,50000,30000] để lấy bảng tọa độ cọc, lập bảng và vẽ lại thành draw_table.
```

---

## 6. Hạn chế và lưu ý

1. **Chưa chạy trên AutoCAD thật trong môi trường phát triển** (máy Linux, không có AutoCAD).
   * Backend **DXF** được kiểm thử thật bằng ezdxf, và bản vẽ mẫu đã được xuất ảnh để kiểm tra.
   * Backend **COM** được kiểm thử trên AutoCAD giả lập.
   * Lần đầu dùng, hãy chạy `draw_box_culvert_section` rồi `preview_image` trên máy có AutoCAD để đối chiếu.
2. **`cad_command` chạy bất đồng bộ.** AutoCAD xếp lệnh vào hàng đợi và thực hiện khi rảnh. `cad_lisp` đọc kết quả qua biến `USERS5`, nên cần có `vl-princ-to-string`, được hỗ trợ từ AutoCAD 2000.
3. **Duyệt đối tượng qua COM chậm** (mỗi thuộc tính là một lần gọi qua tiến trình). Bản vẽ lớn nên lọc theo layer, loại đối tượng, khung, và giới hạn bằng `limit`.
4. **`preview_image` ở chế độ COM** in theo thiết lập trang (page setup) của layout hiện hành. Nếu ảnh không đúng vùng, hãy đặt vùng in là *Extents* trong page setup.
5. **DWG khi không có AutoCAD** cần ODA File Converter (miễn phí). Nếu không có, hãy lưu DXF; mọi bản AutoCAD đều mở được DXF.
6. Tool AutoCAD-only (`cad_command`, `cad_lisp`, `sysvar_*`, `plot_pdf`, `entity_offset`, `doc_close`) sẽ báo lỗi rõ ràng khi đang ở chế độ DXF.

## 7. Kiểm thử
```powershell
.\.venv\Scripts\python -m pytest -q     # 16 test, chạy đạt với MCP SDK 1.x và 2.x
```
Nội dung test: bảng phiên bản; thử lại khi AutoCAD bận; luồng COM duy nhất; backend COM trên AutoCAD giả lập (layer, vẽ, truy vấn, sửa, block/attribute, hatch, LISP);
backend DXF thật (lưu R12/2000/2013, biến đổi hình học, block); mặt cắt cống hộp trên cả hai backend (giá trị kích thước đúng);
bảng; thống kê; MCP chuyển về DXF khi không có AutoCAD.
