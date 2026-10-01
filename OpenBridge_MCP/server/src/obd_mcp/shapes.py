"""Hinh hoc tham so cho ket cau cau: dam I (BTCT/BTCT DUL), ban mat cau, tru nhieu cot.

Moi kich thuoc nhap bang mm; toa do diem chen bang met. Ham o day la thuan tinh toan (khong
goi OBD) de test duoc doc lap; server.py gui ket qua sang bridge qua geometry.extrusion.

He toa do tiet dien (u, v): u ngang (duong = ben TRAI chieu start->end), v dung.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from bentley_mcp_core.sections import section_properties

MM = 0.001


def _dedupe(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Bo diem trung va diem thang hang (vd dinh crown khi sieu cao 1 mai) -> khong co canh thua trong DGN."""
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-9:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cross) <= 1e-9 * max(1.0, math.dist(a, b) * math.dist(b, c)):
                del out[i]
                changed = True
                break
    return out


def _to_m(pts) -> list[list[float]]:
    return [[round(x * MM, 9), round(y * MM, 9)] for x, y in pts]


# ============================================================================ dam I
@dataclass(frozen=True)
class IGirderSection:
    """Tiet dien dam I doi xung (kieu AASHTO/PCI, dam I BTCT DUL dang dung o Viet Nam).

        |<---- top_flange_width ---->|
        +----------------------------+  -  v = H
        |                            |  top_flange_thickness
        +---\\                  /----+  -
             \\  top_haunch     /        top_haunch_height (vut tren)
              |               |
              |<-web_thick.-->|
              |               |
             /  bottom_haunch  \\       bottom_haunch_height (vut duoi)
        +---/                    \\---+  -
        |                            |  bottom_flange_thickness
        +----------------------------+  -  v = 0  (DIEM CHEN = tim day dam)
        |<-- bottom_flange_width --->|
    """

    height_mm: float
    top_flange_width_mm: float
    top_flange_thickness_mm: float
    top_haunch_height_mm: float
    web_thickness_mm: float
    bottom_flange_width_mm: float
    bottom_flange_thickness_mm: float
    bottom_haunch_height_mm: float

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if value is None or value < 0:
                raise ValueError(f"{name} khong duoc am (dang la {value}).")
        for name in ("height_mm", "top_flange_width_mm", "web_thickness_mm", "bottom_flange_width_mm"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} phai > 0.")
        if self.web_thickness_mm > min(self.top_flange_width_mm, self.bottom_flange_width_mm):
            raise ValueError("Bung dam day hon canh dam.")
        stack = (self.top_flange_thickness_mm + self.top_haunch_height_mm
                 + self.bottom_haunch_height_mm + self.bottom_flange_thickness_mm)
        if stack >= self.height_mm:
            raise ValueError(f"Tong chieu day canh + vut ({stack:g}) phai < chieu cao dam ({self.height_mm:g}).")

    def outline_mm(self) -> list[tuple[float, float]]:
        H, bt, tt, ht = self.height_mm, self.top_flange_width_mm, self.top_flange_thickness_mm, self.top_haunch_height_mm
        bw, bb, tb, hb = (self.web_thickness_mm, self.bottom_flange_width_mm,
                          self.bottom_flange_thickness_mm, self.bottom_haunch_height_mm)
        return _dedupe([
            (-bb / 2, 0), (bb / 2, 0), (bb / 2, tb), (bw / 2, tb + hb),
            (bw / 2, H - tt - ht), (bt / 2, H - tt), (bt / 2, H),
            (-bt / 2, H), (-bt / 2, H - tt), (-bw / 2, H - tt - ht),
            (-bw / 2, tb + hb), (-bb / 2, tb),
        ])

    def loops_m(self) -> list[dict]:
        return [{"role": "outer", "points": _to_m(self.outline_mm())}]

    def properties_mm(self) -> dict:
        return section_properties([{"role": "outer", "points": self.outline_mm()}], "mm")


def composite_properties(girder: IGirderSection, slab_effective_width_mm: float, slab_thickness_mm: float,
                         haunch_mm: float = 0.0, modular_ratio: float = 1.0) -> dict:
    """Dac trung tiet dien LIEN HOP dam + ban mat cau (tiet dien quy doi).

    Ban quy doi ve vat lieu dam: b_qd = b_eff * n, n = E_ban / E_dam (TCVN 11823-4 / AASHTO 4.6.2.6
    cho b_eff). Lop dem (haunch) giua dinh dam va day ban bo qua khi tinh do cung (thien ve an toan,
    thong le thiet ke) nhung van nang ban len cao.
    """
    if slab_effective_width_mm <= 0 or slab_thickness_mm <= 0 or modular_ratio <= 0 or haunch_mm < 0:
        raise ValueError("b_eff, chieu day ban, modular_ratio phai > 0; haunch >= 0.")
    H = girder.height_mm
    b = slab_effective_width_mm * modular_ratio
    y0 = H + haunch_mm
    slab = [(-b / 2, y0), (b / 2, y0), (b / 2, y0 + slab_thickness_mm), (-b / 2, y0 + slab_thickness_mm)]
    props = section_properties([
        {"role": "outer", "points": girder.outline_mm()},
        {"role": "outer", "points": slab},
    ], "mm")
    yc = props["centroid_mm"][1]
    props["yt_girder_mm"] = H - yc                         # trong tam -> dinh dam
    props["St_girder_mm3"] = props["Ix_mm4"] / (H - yc) if H != yc else None
    props["transformed_slab_width_mm"] = b
    return props


# ============================================================================ ban mat cau
@dataclass(frozen=True)
class DeckSlab:
    """Ban mat cau chieu day khong doi, doc ngang 2 mai (hoac 1 mai khi sieu cao).

    Diem chen = DINH mat ban tai vi tri dinh doc (crown). crown_offset_mm: vi tri dinh doc so voi
    tim (duong = ben trai). left/right_slope_pct: doc ngang tu dinh ra mep, DUONG = doc xuong.
    Sieu cao 1 mai 4% xuong ben phai: left_slope_pct=-4, right_slope_pct=4.
    """

    width_mm: float
    thickness_mm: float
    left_slope_pct: float = 2.0
    right_slope_pct: float = 2.0
    crown_offset_mm: float = 0.0

    def validate(self) -> None:
        if self.width_mm <= 0 or self.thickness_mm <= 0:
            raise ValueError("Be rong va chieu day ban phai > 0.")
        if abs(self.crown_offset_mm) >= self.width_mm / 2:
            raise ValueError("Dinh doc (crown) phai nam trong be rong ban.")
        if max(abs(self.left_slope_pct), abs(self.right_slope_pct)) > 12:
            raise ValueError("Doc ngang > 12% - kiem tra lai don vi (%).")

    def outline_mm(self) -> list[tuple[float, float]]:
        W, t, c = self.width_mm, self.thickness_mm, self.crown_offset_mm
        vl = -self.left_slope_pct / 100 * (W / 2 - c)      # mep trai (u = +W/2)
        vr = -self.right_slope_pct / 100 * (W / 2 + c)     # mep phai (u = -W/2)
        return _dedupe([
            (-W / 2, vr - t), (c, -t), (W / 2, vl - t),
            (W / 2, vl), (c, 0.0), (-W / 2, vr),
        ])

    def loops_m(self) -> list[dict]:
        return [{"role": "outer", "points": _to_m(self.outline_mm())}]

    def area_m2(self) -> float:
        return self.width_mm * self.thickness_mm * MM * MM


# ============================================================================ tru nhieu cot
@dataclass(frozen=True)
class MultiColumnPier:
    """Tru be + n cot + xa mu chu nhat. Truc ngang tru = phuong dai cua xa mu / be.

    Diem chen = TIM DAY BE. orientation_deg: goc phuong vi truc ngang tru tu +X, nguoc chieu kim
    dong ho (tru vuong goc tim cau co huong cau 0 deg -> orientation_deg = 90).
    """

    footing_length_mm: float      # doc truc ngang tru
    footing_width_mm: float       # doc huong cau
    footing_thickness_mm: float
    column_count: int
    column_height_mm: float       # tu dinh be den day xa mu
    column_spacing_mm: float      # tim - tim, doc truc ngang tru
    cap_length_mm: float
    cap_width_mm: float
    cap_depth_mm: float
    column_shape: str = "circle"  # "circle" | "rectangle"
    column_diameter_mm: float | None = None
    column_size_mm: tuple[float, float] | None = None   # (doc truc ngang, doc huong cau)
    circle_segments: int = 64

    def column_footprint_mm(self) -> tuple[float, float]:
        if self.column_shape == "circle":
            return (self.column_diameter_mm or 0.0, self.column_diameter_mm or 0.0)
        a, b = self.column_size_mm or (0.0, 0.0)
        return (a, b)

    def validate(self) -> None:
        dims = ("footing_length_mm", "footing_width_mm", "footing_thickness_mm", "column_height_mm",
                "cap_length_mm", "cap_width_mm", "cap_depth_mm")
        for name in dims:
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} phai > 0.")
        if self.column_count < 1:
            raise ValueError("column_count phai >= 1.")
        if self.column_shape not in ("circle", "rectangle"):
            raise ValueError("column_shape chi nhan 'circle' hoac 'rectangle'.")
        a, b = self.column_footprint_mm()
        if a <= 0 or b <= 0:
            raise ValueError("Cot tron can column_diameter_mm; cot chu nhat can column_size_mm [a, b].")
        if self.column_count > 1 and self.column_spacing_mm < a:
            raise ValueError("Khoang cach cot nho hon kich thuoc cot - cac cot chong len nhau.")
        span = (self.column_count - 1) * self.column_spacing_mm + a
        for what, length, width in (("be", self.footing_length_mm, self.footing_width_mm),
                                    ("xa mu", self.cap_length_mm, self.cap_width_mm)):
            if span > length + 1e-6 or b > width + 1e-6:
                raise ValueError(f"Cot vuot ra ngoai {what}: can {span:g} x {b:g} mm, {what} {length:g} x {width:g} mm.")

    def column_offsets_mm(self) -> list[float]:
        n = self.column_count
        return [(k - (n - 1) / 2) * self.column_spacing_mm for k in range(n)]

    def column_area_mm2(self) -> float:
        a, b = self.column_footprint_mm()
        return math.pi * a * a / 4 if self.column_shape == "circle" else a * b

    def components(self, base_point_m: list[float], orientation_deg: float) -> list[dict]:
        """Cac khoi dun THANG DUNG: {name, origin, end, loops} (toa do met, san sang gui bridge)."""
        x0, y0, z0 = [*base_point_m, 0.0, 0.0][:3]
        th = math.radians(orientation_deg)
        cs, sn = math.cos(th), math.sin(th)

        def rot(pts_mm, du=0.0):
            # (a doc truc ngang, b doc huong cau) mm -> (X, Y) met so voi diem chen
            return [[round(((a + du) * cs - b * sn) * MM, 9), round(((a + du) * sn + b * cs) * MM, 9)]
                    for a, b in pts_mm]

        def rect(lx, ly):
            return [(-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2)]

        z_top_footing = z0 + self.footing_thickness_mm * MM
        z_cap = z_top_footing + self.column_height_mm * MM
        z_top = z_cap + self.cap_depth_mm * MM

        comps = [{"name": "be_tru", "origin": [x0, y0, z0], "end": [x0, y0, z_top_footing],
                  "loops": [{"role": "outer", "points": rot(rect(self.footing_length_mm, self.footing_width_mm))}]}]

        a, b = self.column_footprint_mm()
        if self.column_shape == "circle":
            n = max(self.circle_segments, 12)
            col = [(a / 2 * math.cos(2 * math.pi * i / n), a / 2 * math.sin(2 * math.pi * i / n)) for i in range(n)]
        else:
            col = rect(a, b)
        for k, off in enumerate(self.column_offsets_mm(), start=1):
            comps.append({"name": f"cot_{k}", "origin": [x0, y0, z_top_footing], "end": [x0, y0, z_cap],
                          "loops": [{"role": "outer", "points": rot(col, du=off)}]})

        comps.append({"name": "xa_mu", "origin": [x0, y0, z_cap], "end": [x0, y0, z_top],
                      "loops": [{"role": "outer", "points": rot(rect(self.cap_length_mm, self.cap_width_mm))}]})
        return comps

    def quantities(self, base_point_m: list[float]) -> dict:
        v_footing = self.footing_length_mm * self.footing_width_mm * self.footing_thickness_mm * 1e-9
        v_cols = self.column_count * self.column_area_mm2() * self.column_height_mm * 1e-9
        v_cap = self.cap_length_mm * self.cap_width_mm * self.cap_depth_mm * 1e-9
        z0 = [*base_point_m, 0.0, 0.0][2]
        total_h = (self.footing_thickness_mm + self.column_height_mm + self.cap_depth_mm) * MM
        return {
            "footing_volume_m3": round(v_footing, 4),
            "columns_volume_m3": round(v_cols, 4),
            "cap_volume_m3": round(v_cap, 4),
            "total_volume_m3": round(v_footing + v_cols + v_cap, 4),
            "column_offsets_mm": self.column_offsets_mm(),
            "elevation_bottom_footing_m": round(z0, 4),
            "elevation_top_cap_m": round(z0 + total_h, 4),
            "note": ("The tich cot tron tinh theo pi*D^2/4 (thiet ke); khoi DGN la da giac "
                     f"{self.circle_segments} canh, nho hon ~{(1 - self.circle_segments / (2 * math.pi) * math.sin(2 * math.pi / self.circle_segments)) * 100:.2f}%.")
            if self.column_shape == "circle" else None,
        }


# ============================================================================ tien ich truc
def axis_info(start: list[float], end: list[float]) -> dict:
    s = [*start, 0.0, 0.0][:3]
    e = [*end, 0.0, 0.0][:3]
    d = [e[i] - s[i] for i in range(3)]
    plan = math.hypot(d[0], d[1])
    length = math.sqrt(sum(c * c for c in d))
    if plan < 1e-9:
        raise ValueError("Truc start->end thang dung hoac co chieu dai bang 0.")
    return {
        "start": s, "end": e,
        "length_3d_m": length, "length_plan_m": plan,
        "slope_pct": d[2] / plan * 100,
        "left_normal": [-d[1] / plan, d[0] / plan, 0.0],  # phap tuyen ngang ben trai
    }


def lateral_offsets_m(count: int, spacing_mm: float | None) -> list[float]:
    if count < 1:
        raise ValueError("count phai >= 1.")
    if count > 1 and (spacing_mm is None or spacing_mm <= 0):
        raise ValueError("Nhieu dam can spacing_mm > 0 (khoang cach tim - tim).")
    return [(k - (count - 1) / 2) * (spacing_mm or 0.0) * MM for k in range(count)]


def offset_axis(axis: dict, offset_m: float) -> tuple[list[float], list[float]]:
    n = axis["left_normal"]
    s = [axis["start"][i] + offset_m * n[i] for i in range(3)]
    e = [axis["end"][i] + offset_m * n[i] for i in range(3)]
    return s, e
