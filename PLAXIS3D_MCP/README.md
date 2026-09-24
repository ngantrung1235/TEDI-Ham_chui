# PLAXIS 3D MCP – liên kết Claude Code với PLAXIS 3D

MCP server (Model Context Protocol) cho phép **Claude Code** hoặc **Claude Desktop** điều khiển
**PLAXIS 3D** (Bentley, đã nhắm tới bản 2025.1 – V25.01) qua *Remote Scripting server*
(thư viện `plxscripting`). Bạn ra lệnh bằng ngôn ngữ tự nhiên; Claude gọi các tool để tạo vật liệu,
địa tầng, kết cấu, tải trọng, lưới, giai đoạn thi công, chạy tính toán và đọc kết quả.

Gói có kèm bộ dựng **mô hình hầm chui / cống hộp dưới nền đắp** theo tham số: khung BTCT theo
TCVN 5574:2018 và hoạt tải HL-93 theo TCVN 11823-3:2017.

---

## 1. Kiến trúc

```
┌──────────────┐  MCP (stdio)  ┌────────────────────┐ HTTP + password ┌──────────────────────┐
│ Claude Code  │ ────────────► │ plaxis3d_mcp       │ ──────────────► │ PLAXIS 3D Input      │
│ Claude Desk. │ ◄──────────── │ (Python, 42 tools) │  port 10000     │ Remote scripting     │
└──────────────┘               │  ops/  engineering/│ ──────────────► │ PLAXIS 3D Output     │
                               └────────────────────┘  port 10001/view└──────────────────────┘
```

| Tầng | File | Vai trò |
|---|---|---|
| MCP | `server.py` | Khai báo tool; chạy lệnh PLAXIS trong luồng phụ (`anyio.to_thread`) có khóa (`RLock`), vì `plxscripting` là thư viện đồng bộ và không an toàn đa luồng |
| Phiên | `session.py` | Giữ `(s_i, g_i)` (Input) và `(s_o, g_o)` (Output); đọc cấu hình từ biến môi trường |
| Tiện ích | `plx.py` | Chuyển proxy PLAXIS sang JSON; lấy đối tượng theo tên; `setproperties` có kiểm soát lỗi |
| Thao tác | `ops/*.py` | Project, địa tầng, vật liệu, kết cấu, tải trọng, lưới, giai đoạn, kết quả |
| Kỹ thuật | `engineering/*.py` | Vật liệu mẫu (TCVN 5574), HL-93 qua lớp đắp (TCVN 11823-3), mô hình hầm chui |

**Nguyên tắc thiết kế:**
* **Không “nuốt” lỗi.** Thuộc tính bị PLAXIS từ chối (sai tên do khác phiên bản…) được trả về trong
  `warnings`. Tool **không** dùng `setattr`, vì `plxscripting` sẽ âm thầm tạo thuộc tính Python mới
  khi thuộc tính PLAXIS không tồn tại; thay vào đó dùng lệnh `setproperties` của chính PLAXIS.
* **Có lối thoát khi thiếu tool:** `plaxis_command` chạy bất kỳ lệnh command-line nào của PLAXIS.
  `plaxis_python` chạy script Python với `g_i/g_o`, nhưng mặc định bị tắt.
* **Lỗi hiển thị nguyên văn** cho Claude (`ToolError`), để Claude tự sửa lệnh.

---

## 2. Yêu cầu

* Windows có cài PLAXIS 3D 2025.1 (bản 2023.x/2024.x cũng dùng được, xem mục 9) và license còn hiệu lực.
* Python ≥ 3.10 (dùng Python cài riêng từ python.org; không bắt buộc dùng Python đi kèm PLAXIS).
* Claude Code (CLI/VS Code) hoặc Claude Desktop.

## 3. Cài đặt

```powershell
# Giải nén thư mục PLAXIS3D_MCP, ví dụ vào D:\Tools\PLAXIS3D_MCP
cd D:\Tools\PLAXIS3D_MCP
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Script sẽ tạo `.venv`, cài `mcp` và `plxscripting` (có trên PyPI), rồi in sẵn lệnh đăng ký với Claude Code.
Cài thủ công:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -e .
```

## 4. Bật Remote Scripting trong PLAXIS 3D

1. Mở **PLAXIS 3D Input** → menu **Expert → Configure remote scripting server**.
2. Chọn port **10000**, đặt **password** (ví dụ `tedi2025`), bấm **Start server**.
3. Output: không cần bật thủ công. Tool `output_connect` sẽ yêu cầu Input mở Output qua lệnh
   `view` và tự lấy port. Nếu muốn tự bật, dùng port 10001 rồi gọi `output_connect(port=10001)`.

> Mật khẩu chỉ đặt trong biến môi trường `PLAXIS_PASSWORD`, không ghi vào mã nguồn hay repo.

## 5. Kết nối Claude Code

```powershell
claude mcp add plaxis3d --scope user `
  -e PLAXIS_PASSWORD=tedi2025 `
  -- D:\Tools\PLAXIS3D_MCP\.venv\Scripts\python.exe -m plaxis3d_mcp
```

Hoặc chép `examples/.mcp.json` vào thư mục dự án (cấu hình theo từng project). Kiểm tra bằng `/mcp` trong Claude Code.

**Thời gian tính toán dài:** `calculate` chờ đến khi PLAXIS tính xong. Hãy tăng thời gian chờ tool của Claude Code
trước khi mở Claude Code, ví dụ 2 giờ:

```powershell
$env:MCP_TOOL_TIMEOUT = "7200000"   # ms
claude
```

**Claude Desktop:** chép nội dung `examples/claude_desktop_config.json` vào
`%APPDATA%\Claude\claude_desktop_config.json`.

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `PLAXIS_HOST` | `localhost` | Máy chạy PLAXIS (có thể là máy khác trong LAN) |
| `PLAXIS_INPUT_PORT` | `10000` | Port Input |
| `PLAXIS_OUTPUT_PORT` | `10001` | Port Output (khi tự bật) |
| `PLAXIS_PASSWORD` | – | Mật khẩu remote scripting |
| `PLAXIS_MCP_ALLOW_PYTHON` | `0` | `1` = cho phép tool `plaxis_python` chạy mã tùy ý |

---

## 6. Danh sách tool (42)

| Nhóm | Tool |
|---|---|
| Kết nối/Project | `plaxis_connect`, `plaxis_status`, `project_new`, `project_open`, `project_save`, `goto_mode` |
| Đối tượng chung | `list_objects`, `get_object`, `set_object_properties` (có tham số `phase` cho thuộc tính theo giai đoạn), `delete_objects`, `plaxis_command`, `plaxis_python` |
| Vật liệu | `material_create`, `material_concrete_plate` (TCVN 5574), `material_soil_preset`, `material_list`, `material_set` |
| Địa tầng | `soil_contour`, `borehole_create`, `soil_layer_material`, `soil_volume_create` |
| Kết cấu | `surface_create`, `plate_create` (+interface), `beam_create`, `embedded_beam_create`, `anchor_create` |
| Tải trọng | `surface_load_create`, `line_load_create`, `point_load_create` |
| Tính toán | `mesh_generate`, `phase_create`, `phase_configure`, `phase_list`, `calculate` |
| Kết quả | `output_connect`, `results_get` (min/max/|max| kèm tọa độ), `results_at_point`, `results_plate_forces` |
| Kỹ thuật | `hl93_live_load_through_fill`, `concrete_properties`, `box_culvert_layout`, `build_box_culvert` |

Quy ước: đơn vị kN, m, kPa. Trục Z hướng lên, tải hướng xuống mang dấu âm (`sigz < 0`).
Trong giá trị thuộc tính, chuỗi bắt đầu bằng `@` là tham chiếu đối tượng, ví dụ `{"Material": "@PlateMat_2"}`.

---

## 7. Mô hình hầm chui tham số (`build_box_culvert`)

### 7.1 Hệ tọa độ và hình học

```
      Mặt cắt dọc tuyến đường (mặt YZ)             Mặt cắt ngang cống (mặt XZ)
            Bc (bề rộng đỉnh)                         ┌───────────────┐ ← bản nắp (plate, z = z_ts)
        ┌──────────────┐  ▲ He                        │               │
       /  cover ▲       \  │                    tường │   B × H       │ tường (x = ±xw)
      /   ┌─────┴─────┐  \ │                          │               │
     /    │   CỐNG    │   \│                          └───────────────┘ ← bản đáy (plate, z = 0)
 ───/─────┴───────────┴────\──── z = 0 (mặt đất tự nhiên)
    1:m     L (dài cống)
```

* **X**: trục đường (hướng xe chạy), tim cống tại x = 0. **Y**: trục cống, tim đường tại y = 0.
* Tường và bản là **plate đặt tại mặt trung bình**: `xw = B/2 + tw/2`, bản đáy tại z = 0,
  bản nắp tại `z_ts = tb/2 + H + tt/2`. Chiều cao đắp `He = z_ts + tt/2 + cover`.
* Chiều dài cống mặc định `L = Bc + 2·m·cover`, tức bằng bề rộng nền đắp tại cao độ mặt bản nắp.
* **Nền đắp gồm 3 khối đất không chồng lấn:** 2 khối hai bên cống (|x| ≥ xw) và 1 khối trên bản nắp
  (|x| ≤ xw, cắt tại y = ±L/2). Ưu điểm: khi chuyển sang Staged construction, mỗi cluster thuộc đúng
  một đối tượng Soil nên kích hoạt/vô hiệu hóa không bị mơ hồ.
* **Tường cánh** (mặt x = ±xw, ngoài hai đầu cống) và **tường đầu** (mặt y = ±L/2, phía trên bản nắp) đỡ taluy tại cửa cống.
* **Interface** chỉ đặt ở phía có đất. Thứ tự điểm được tính (pháp tuyến Newell) để phía *positive* hướng ra đất.

**Giả thiết đơn giản hóa:** mặt trung bình bản đáy đặt tại mặt đất tự nhiên, nên lòng cống nằm hoàn toàn
trên mặt đất và không phải đào đất trong hộp. Nếu móng cống chôn sâu, cần tạo thêm khối đất đào và
vô hiệu hóa cluster tương ứng bằng `phase_configure`.

### 7.2 Vật liệu

| Cấu kiện | Mô hình | Tham số |
|---|---|---|
| Bê tông (TCVN 5574:2018, bảng 10) | Plate đàn hồi đẳng hướng | Eb: B25 = 30 000; **B30 = 32 500**; B35 = 34 500 MPa; ν = 0,2; γ = 25 kN/m³ |
| Đất đắp K95 | Mohr–Coulomb | γ = 19/20, E = 25 MPa, c = 5 kPa, φ = 30°, R_inter = 0,67 |
| Địa tầng tự nhiên | Mohr–Coulomb | **preset mang tính minh họa**: bắt buộc thay bằng số liệu khảo sát (TCVN 9363:2012) |

Lưu ý: dùng mô đun đàn hồi ban đầu Eb (tiết diện không nứt) sẽ cho độ cứng khung lớn hơn thực tế.
Khi kiểm tra trạng thái giới hạn sử dụng có nứt, nên giảm độ cứng uốn, ví dụ nhân EI hữu hiệu khoảng 0,5–0,7 cho bản bị nứt.
Việc này làm mô men phân phối lại giữa bản và tường; hãy làm phân tích độ nhạy.

### 7.3 Hoạt tải HL-93 (TCVN 11823-3:2017 ≡ AASHTO LRFD 2012/2014)

| Nội dung | Điều khoản | Giá trị |
|---|---|---|
| Xe tải thiết kế | §3.6.1.2.2 | 35 + 145 + 145 kN, trục cách 4,3 m, khoảng cách bánh ngang 1,8 m |
| Xe hai trục | §3.6.1.2.3 | 2 × 110 kN, trục cách 1,2 m |
| Diện tích tiếp xúc bánh xe | §3.6.1.2.5 | 510 mm (ngang) × 250 mm (dọc) |
| Phân bố qua đất đắp (H ≥ 0,6 m) | §3.6.1.2.6 | Mỗi cạnh tăng thêm LLDF·H; LLDF = 1,15 (đất hạt chọn lọc), 1,0 (đất khác); vùng chồng lấn gộp lại thành một hình chữ nhật bao |
| Tải trọng làn | §3.6.1.3.3 | Không áp dụng cho bản nắp cống hộp |
| Hệ số làn xe m | §3.6.1.1.2 | 1,20 / 1,00 / 0,85 / 0,65 |
| Lực xung kích cho kết cấu vùi | §3.6.2.2 | IM = 33·(1 − 4,1·10⁻⁴·D_E) ≥ 0 %, D_E tính bằng mm |

**Ví dụ kiểm tra** (cover H = 1,5 m, đất hạt, 1 làn):
* Kích thước vệt tải: ngang 0,51 + 1,15·1,5 = 2,235 m > 1,8 m, nên hai bánh của cùng trục gộp lại,
  bề rộng 1,8 + 2,235 = 4,035 m. Dọc: 0,25 + 1,725 = 1,975 m < 4,3 m, nên các trục không gộp.
* p = 145 / (4,035 × 1,975) = **18,20 kPa**. IM = 33·(1 − 0,615) = 12,7 %.
* p·m·(1+IM) = 18,20 × 1,2 × 1,127 = **24,6 kPa**. Đây là giá trị trả về trong `governing`.

**Điểm quan trọng khi mô hình 3D:** trong mô hình phần tử hữu hạn liên tục, bản thân đất đã
phân bố tải. Vì vậy `build_box_culvert` đặt **tải bánh xe lên đúng diện tích tiếp xúc tại mặt đường**:
72,5 kN / (0,51 × 0,25) × m × (1+IM) ≈ 769 kPa với cover 1,5 m. Không đặt thêm áp lực đã phân bố,
vì như vậy sẽ tính phân bố tải **hai lần**.
Giá trị `governing` chỉ dùng để **đối chiếu** với áp lực đứng trên bản nắp đọc từ Output.
Các giá trị này là tải tiêu chuẩn (chưa nhân hệ số). Hệ số tải trọng như γ_LL = 1,75 cho tổ hợp Cường độ I
(bảng 3.4.1-1) được áp dụng ở bước kiểm toán tiết diện.

*So sánh tiêu chuẩn:* AASHTO LRFD bản 8/9 thay cách phân bố LLDF bằng phương pháp *wheel interaction depth*;
với lớp đắp mỏng, kết quả chênh lệch vài phần trăm. Hãy kiểm tra Khung tiêu chuẩn (Design Criteria) của dự án
áp dụng phiên bản nào. 22TCN 272-05 (tiêu chuẩn cũ) dùng quy tắc phân bố tương tự bản AASHTO 1998.

### 7.4 Giai đoạn thi công tự động

| Phase | Loại | Kích hoạt | Ghi chú |
|---|---|---|---|
| Initial | K0 procedure | Nền tự nhiên (vô hiệu hóa 3 khối đắp) | Mặt đất nằm ngang nên dùng K0 là hợp lệ |
| 01 Culvert construction | Plastic | Plate cống, tường cánh, tường đầu, interface | |
| 02 Embankment fill | Plastic | 3 khối đắp | Nền đất yếu: chia lớp đắp và thêm các phase Consolidation |
| 03 HL-93 traffic | Plastic, reset chuyển vị | Tải bánh xe | Chuyển vị trong phase này chỉ do hoạt tải |

Để tìm vị trí xe bất lợi, chạy lại với các giá trị `truck_x` khác nhau (vị trí trục 145 kN dọc tuyến),
ví dụ 0; ±B/2; ±(B/2 + 2 m). Có thể thêm `lanes = 2`.

### 7.5 Tham số (`params`, đều tùy chọn)

`clear_width` 4,0 · `clear_height` 3,2 · `t_top` 0,45 · `t_bottom` 0,50 · `t_wall` 0,40 · `concrete_grade` "B30" ·
`cover` 1,5 · `crest_width` 12 · `side_slope` 1,5 · `culvert_length` (tự tính) · `wing_walls` true ·
`layer_levels` [0, −20] · `layer_presets` ["stiff_clay"] · `layer_materials` (tên SoilMat có sẵn) · `water_head` ·
`embankment_preset` "embankment_K95" · `margin_x` · `margin_y` 10 · `traffic` "wheel_patches"|"none" ·
`vehicle` "truck"|"tandem" · `lanes` 1 · `truck_x` 0 · `granular_fill` true · `generate_mesh` true ·
`mesh_coarseness` 0,06 · `auto_stage` true.

Dùng `box_culvert_layout` để xem trước hình học mà không cần gọi PLAXIS.

---

## 8. Ví dụ câu lệnh cho Claude

```
Kết nối PLAXIS 3D, tạo project mới "HC KM77+633", dựng hầm chui 6x4.5 m, bản nắp 0.6, bản đáy 0.65,
tường 0.55, bê tông B30, đắp 2.5 m, taluy 1:1.5, mặt đường 12 m. Địa tầng: 0 đến -2.5 sét dẻo mềm,
-2.5 đến -9 cát pha chặt vừa, -9 đến -25 sét cứng; mực nước -1.5. Chạy tính toán rồi lập bảng
M11, Q13, N1 lớn nhất của bản nắp, bản đáy, tường cho phase hoạt tải.
```

```
Tính áp lực HL-93 trên bản nắp cống hộp với lớp đắp 0.9, 1.5, 2.4 m (đất hạt), 2 làn.
Lập bảng so sánh và chỉ ra khi nào tải xe hai trục khống chế.
```

```
Đọc độ lún Uz tại tim đường (0,0,He) sau phase đắp nền và sau phase hoạt tải.
```

---

## 9. Hạn chế, rủi ro và cách kiểm chứng

1. **Phiên bản API.** Tên thuộc tính lấy theo PLAXIS 3D CONNECT/2023+ (`Identification`, `Gamma`, `E1`, `nu12`,
   `sigz`, `DeformCalcType`). Phiên bản cũ dùng tên khác (`MaterialName`, `w`…); tool sẽ báo trong `warnings`.
   Khi đó dùng `material_set` hoặc `set_object_properties` với tên đúng. Có thể tra tên bằng `get_object`.
2. **Chưa chạy trên PLAXIS thật trong môi trường phát triển.** File cài bạn gửi là bộ cài online
   (WiX bootstrapper, khoảng 7,7 MB), chỉ tải PLAXIS khi cài trên Windows và cần license. Vì vậy mã được kiểm thử bằng
   bộ giả lập `tests/fake_plaxis.py` và chạy thử giao thức MCP qua stdio. Lần chạy đầu trên máy có PLAXIS,
   hãy dựng mô hình mặc định (`build_box_culvert` không tham số) và kiểm tra trong GUI:
   hướng interface, trạng thái kích hoạt từng phase, tải bánh xe nằm trên mặt đường.
3. **Tên đối tượng ở Staged construction.** Sau khi giao cắt, PLAXIS tách đối tượng thành các con
   (`Plate_1_1`…). Tool thử kích hoạt theo tên cha trước; nếu không được thì kích hoạt từng con có tiền tố `Plate_1_`.
4. **`calculate` chặn** cho đến khi tính xong. Cần tăng `MCP_TOOL_TIMEOUT`, hoặc chạy từng phase bằng tham số `phases`.
5. **`plaxis_python`** thực thi mã tùy ý trên máy của bạn, chỉ bật khi thực sự cần.
6. Kết quả PTHH phải được kiểm tra bằng tính toán độc lập, ví dụ khung phẳng với áp lực HL-93 đã phân bố
   và áp lực ngang K0/Ka, trước khi đưa vào hồ sơ thiết kế.

## 10. Kiểm thử

```powershell
.\.venv\Scripts\pip install -e .[test]
.\.venv\Scripts\python -m pytest -q
```

Có 16 test: phân bố HL-93 (có ví dụ tính tay), IM, hình học cống, hướng pháp tuyến, cắt đa giác,
thao tác vật liệu và giai đoạn trên PLAXIS giả lập, dựng toàn bộ mô hình qua tool MCP. Đã chạy đạt với MCP SDK 1.x và 2.x.
