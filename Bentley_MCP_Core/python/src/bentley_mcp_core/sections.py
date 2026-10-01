"""Dac trung hinh hoc tiet dien da giac (co lo rong) - dung cho dam, ham, tru...

Cong thuc Green cho da giac dinh (x_i, y_i), c_i = x_i*y_(i+1) - x_(i+1)*y_i:
    A   = 1/2  * sum c_i
    Sx  = 1/6  * sum (y_i + y_(i+1)) c_i            -> y_c = Sx / A
    Sy  = 1/6  * sum (x_i + x_(i+1)) c_i            -> x_c = Sy / A
    Ixx = 1/12 * sum (y_i^2 + y_i y_(i+1) + y_(i+1)^2) c_i     (quanh truc x qua goc)
    Iyy = 1/12 * sum (x_i^2 + x_i x_(i+1) + x_(i+1)^2) c_i
    Ixy = 1/24 * sum (x_i y_(i+1) + 2 x_i y_i + 2 x_(i+1) y_(i+1) + x_(i+1) y_i) c_i
Loop 'outer' cong, loop 'hole' tru (khong phu thuoc chieu ve). Doi truc song song
(Steiner) ve trong tam: I_c = I_0 - A d^2.
Don vi dau ra = don vi toa do dau vao (mm -> mm2, mm4).
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = Sequence[float]


def _raw(points: Sequence[Point]) -> tuple[float, float, float, float, float, float]:
    a = sx = sy = ixx = iyy = ixy = 0.0
    n = len(points)
    for i in range(n):
        x0, y0 = points[i][0], points[i][1]
        x1, y1 = points[(i + 1) % n][0], points[(i + 1) % n][1]
        c = x0 * y1 - x1 * y0
        a += c
        sx += (y0 + y1) * c
        sy += (x0 + x1) * c
        ixx += (y0 * y0 + y0 * y1 + y1 * y1) * c
        iyy += (x0 * x0 + x0 * x1 + x1 * x1) * c
        ixy += (x0 * y1 + 2 * x0 * y0 + 2 * x1 * y1 + x1 * y0) * c
    return a / 2, sx / 6, sy / 6, ixx / 12, iyy / 12, ixy / 24


def section_properties(loops: Iterable[dict], unit: str = "mm") -> dict:
    """loops: [{"role": "outer"|"hole", "points": [[x, y], ...]}] -> A, trong tam, I, W, r."""
    A = Sx = Sy = Ixx = Iyy = Ixy = 0.0
    xs: list[float] = []
    ys: list[float] = []
    n_outer = 0
    for loop in loops:
        pts = [tuple(p[:2]) for p in loop["points"]]
        if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-12:
            pts = pts[:-1]
        if len(pts) < 3:
            raise ValueError("Moi loop can it nhat 3 diem.")
        a, sx, sy, ixx, iyy, ixy = _raw(pts)
        orient = 1.0 if a >= 0 else -1.0          # chuan hoa ve chieu duong (CCW)
        sign = -1.0 if loop.get("role", "outer") == "hole" else 1.0
        if sign > 0:
            n_outer += 1
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
        k = sign * orient
        A += k * a
        Sx += k * sx
        Sy += k * sy
        Ixx += k * ixx
        Iyy += k * iyy
        Ixy += k * ixy

    if n_outer == 0 or A <= 0:
        raise ValueError("Tiet dien khong hop le: can it nhat 1 loop 'outer' va dien tich > 0.")

    xc, yc = Sy / A, Sx / A
    ix = Ixx - A * yc * yc
    iy = Iyy - A * xc * xc
    ixy_c = Ixy - A * xc * yc
    # Momen quan tinh chinh
    mid, rad = (ix + iy) / 2, math.hypot((ix - iy) / 2, ixy_c)
    yb, yt = yc - min(ys), max(ys) - yc
    xl, xr = xc - min(xs), max(xs) - xc
    u = unit
    return {
        "unit": u,
        f"area_{u}2": A,
        f"centroid_{u}": [xc, yc],
        f"yb_{u}": yb,                       # trong tam -> mep duoi
        f"yt_{u}": yt,                       # trong tam -> mep tren
        f"Ix_{u}4": ix,                      # quanh truc ngang qua trong tam
        f"Iy_{u}4": iy,                      # quanh truc dung qua trong tam
        f"Ixy_{u}4": ixy_c,
        f"I1_{u}4": mid + rad,
        f"I2_{u}4": mid - rad,
        f"Sb_{u}3": ix / yb if yb > 0 else None,     # W thoi duoi
        f"St_{u}3": ix / yt if yt > 0 else None,     # W thoi tren
        f"Sy_left_{u}3": iy / xl if xl > 0 else None,
        f"Sy_right_{u}3": iy / xr if xr > 0 else None,
        f"rx_{u}": math.sqrt(ix / A),
        f"ry_{u}": math.sqrt(iy / A),
        f"bbox_{u}": [min(xs), min(ys), max(xs), max(ys)],
    }
