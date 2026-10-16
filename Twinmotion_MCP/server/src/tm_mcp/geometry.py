"""Hinh hoc toa do: doi toa do tuong doi cua so <-> toa do man hinh, kiem tra ra ngoai cua so."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """Hinh chu nhat theo toa do man hinh (pixel vat ly): [left, right) x [top, bottom)."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains_screen(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        """Toa do tuong doi goc tren-trai cua Rect -> toa do man hinh (lam tron)."""
        return self.left + round(x), self.top + round(y)

    def to_relative(self, sx: int, sy: int) -> tuple[int, int]:
        return sx - self.left, sy - self.top

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    def as_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


class OutOfBounds(ValueError):
    """Toa do nam ngoai vung dieu khien cho phep (an toan: khong click ra ngoai cua so)."""


def checked_screen_point(area: Rect, x: float, y: float, *, what: str = "diem") -> tuple[int, int]:
    """Toa do tuong doi `area` -> toa do man hinh, bao loi neu nam ngoai `area`."""
    if area.width <= 0 or area.height <= 0:
        raise OutOfBounds("Vung dieu khien co kich thuoc 0 (cua so bi thu nho hoac bi an?).")
    sx, sy = area.to_screen(x, y)
    if not area.contains_screen(sx, sy):
        raise OutOfBounds(
            f"{what.capitalize()} ({x:g}, {y:g}) nam ngoai vung dieu khien {area.width}x{area.height}px "
            f"(toa do hop le: 0..{area.width - 1}, 0..{area.height - 1}, goc tren-trai)."
        )
    return sx, sy


def interpolate(x0: float, y0: float, x1: float, y1: float, steps: int) -> list[tuple[int, int]]:
    """Cac diem trung gian (steps diem, kem diem cuoi) tren duong thang tu (x0,y0) toi (x1,y1)."""
    steps = max(int(steps), 1)
    return [(round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps)) for i in range(1, steps + 1)]
