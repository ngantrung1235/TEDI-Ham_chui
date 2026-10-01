"""Hinh hoc tiet dien ham chui / cong hop BTCT (1 hoac nhieu khoang) + khoi luong.

Quy uoc he toa do tiet dien (don vi met khi gui sang bridge):
  u : phuong ngang, goc tai TIM tiet dien
  v : phuong dung, goc tai MAT DUOI ban day (day ngoai)
=> diem chen (start/end cua truc) = tim mat duoi ban day tai 2 dau doan ham.

        |<------------------- B_out ------------------->|
        +-----------------------------------------------+  -
        |                 ban nap  t_top                |  |
        |   /-------------\\  t_mid  /-------------\\    |  |
        |  |   khoang 1    |  |   |    khoang 2    |   |  H_out
        |  |  B x H        |  |   |                |   |  |
        |   \\-------------/        \\-------------/    |  |
        |                 ban day  t_bot                |  |
        +-----------------------------------------------+  -  v=0
  t_wall                                                t_wall

Vat (vut) goc trong 45 deg: chamfer_top o 2 goc tren, chamfer_bottom o 2 goc duoi moi khoang.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

MM = 0.001


@dataclass(frozen=True)
class BoxCulvertSection:
    clear_width_mm: float
    clear_height_mm: float
    top_slab_mm: float
    bottom_slab_mm: float
    wall_mm: float
    cells: int = 1
    mid_wall_mm: float | None = None
    chamfer_top_mm: float = 0.0
    chamfer_bottom_mm: float = 0.0

    def validate(self) -> None:
        dims = {
            "clear_width_mm": self.clear_width_mm,
            "clear_height_mm": self.clear_height_mm,
            "top_slab_mm": self.top_slab_mm,
            "bottom_slab_mm": self.bottom_slab_mm,
            "wall_mm": self.wall_mm,
        }
        for name, value in dims.items():
            if not value or value <= 0:
                raise ValueError(f"{name} phai > 0 (dang la {value}).")
        if self.cells < 1:
            raise ValueError("cells phai >= 1.")
        if self.cells > 1 and (self.mid_wall_mm is None or self.mid_wall_mm <= 0):
            raise ValueError("Ham nhieu khoang can mid_wall_mm > 0 (chieu day tuong giua).")
        ct, cb = self.chamfer_top_mm, self.chamfer_bottom_mm
        if ct < 0 or cb < 0:
            raise ValueError("Kich thuoc vut khong duoc am.")
        if 2 * max(ct, cb) > self.clear_width_mm:
            raise ValueError("Vut qua lon: 2 x vut > be rong thong thuy B.")
        if ct + cb > self.clear_height_mm:
            raise ValueError("Vut qua lon: vut_tren + vut_duoi > chieu cao thong thuy H.")

    @property
    def mid_wall(self) -> float:
        return (self.mid_wall_mm or 0.0) if self.cells > 1 else 0.0

    @property
    def outer_width_mm(self) -> float:
        n = self.cells
        return n * self.clear_width_mm + 2 * self.wall_mm + (n - 1) * self.mid_wall

    @property
    def outer_height_mm(self) -> float:
        return self.bottom_slab_mm + self.clear_height_mm + self.top_slab_mm

    def outer_loop_mm(self) -> list[tuple[float, float]]:
        hb, ho = self.outer_width_mm / 2, self.outer_height_mm
        return [(-hb, 0.0), (hb, 0.0), (hb, ho), (-hb, ho)]

    def cell_loops_mm(self) -> list[list[tuple[float, float]]]:
        b, h = self.clear_width_mm, self.clear_height_mm
        ct, cb = self.chamfer_top_mm, self.chamfer_bottom_mm
        y0, y1 = self.bottom_slab_mm, self.bottom_slab_mm + h
        loops = []
        for i in range(self.cells):
            x0 = -self.outer_width_mm / 2 + self.wall_mm + i * (b + self.mid_wall)
            x1 = x0 + b
            pts = [
                (x0 + cb, y0), (x1 - cb, y0),
                (x1, y0 + cb), (x1, y1 - ct),
                (x1 - ct, y1), (x0 + ct, y1),
                (x0, y1 - ct), (x0, y0 + cb),
            ]
            loops.append(_dedupe(pts))
        return loops

    def concrete_area_m2(self) -> float:
        outer = self.outer_width_mm * self.outer_height_mm
        cell = (self.clear_width_mm * self.clear_height_mm
                - self.chamfer_top_mm ** 2 - self.chamfer_bottom_mm ** 2)  # 2 tam giac c^2/2 moi canh
        return (outer - self.cells * cell) * MM * MM

    def loops_m(self) -> list[dict]:
        def conv(pts):
            return [[round(x * MM, 9), round(y * MM, 9)] for x, y in pts]

        loops = [{"role": "outer", "points": conv(self.outer_loop_mm())}]
        loops += [{"role": "hole", "points": conv(p)} for p in self.cell_loops_mm()]
        return loops


def _dedupe(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Bo diem trung lien tiep (khi vut = 0) de tranh canh dai 0 trong DGN."""
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-9:
        out.pop()
    return out


def axis_lengths(start: list[float], end: list[float]) -> tuple[float, float, float]:
    """(chieu dai 3D, chieu dai bang, do doc %) cua truc ham."""
    s = [*start, 0.0, 0.0][:3]
    e = [*end, 0.0, 0.0][:3]
    dx, dy, dz = e[0] - s[0], e[1] - s[1], e[2] - s[2]
    horiz = math.hypot(dx, dy)
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    slope = (dz / horiz * 100.0) if horiz > 1e-12 else float("inf")
    return length, horiz, slope


def quantities(section: BoxCulvertSection, start: list[float], end: list[float], section_plane: str) -> dict:
    """Khoi luong be tong cua doan ham.

    - section_plane='vertical' : tiet dien thang dung, dun theo truc co doc -> lang tru xien,
      the tich = dien tich x chieu dai BANG (khoang cach giua 2 mat dau thang dung).
    - section_plane='perpendicular': the tich = dien tich x chieu dai 3D.
    """
    length, horiz, slope = axis_lengths(start, end)
    area = section.concrete_area_m2()
    effective = horiz if section_plane == "vertical" else length
    return {
        "section": asdict(section),
        "outer_width_mm": section.outer_width_mm,
        "outer_height_mm": section.outer_height_mm,
        "concrete_area_m2": round(area, 6),
        "axis_length_3d_m": round(length, 4),
        "axis_length_plan_m": round(horiz, 4),
        "longitudinal_slope_pct": round(slope, 4) if math.isfinite(slope) else None,
        "concrete_volume_m3": round(area * effective, 4),
    }
