"""Backend interface shared by the live AutoCAD (COM) and headless DXF backends.

Coordinates are drawing units (usually mm). Angles in the public API are in
degrees; backends convert to radians where the CAD API needs it. Entities are
identified by their handle (hex string), which is stable across sessions.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Sequence

Point = Sequence[float]

# normalised entity kinds
KINDS = ("line", "polyline", "polyline3d", "circle", "arc", "ellipse", "spline", "text", "mtext",
         "insert", "dimension", "hatch", "point", "3dface", "solid", "leader", "other")


def p3(p: Point) -> tuple[float, float, float]:
    if len(p) not in (2, 3):
        raise RuntimeError(f"Point must be [x, y] or [x, y, z], got {p!r}")
    return (float(p[0]), float(p[1]), float(p[2]) if len(p) == 3 else 0.0)


def rad(deg: float) -> float:
    return math.radians(deg)


def bbox_contains(bbox: Sequence[float] | None, pmin: Point, pmax: Point) -> bool:
    """bbox = [xmin, ymin, xmax, ymax]; True when the entity extents overlap it."""
    if not bbox:
        return True
    return not (pmax[0] < bbox[0] or pmin[0] > bbox[2] or pmax[1] < bbox[1] or pmin[1] > bbox[3])


def polyline_length(pts: Sequence[Point], closed: bool) -> float:
    seg = list(zip(pts, pts[1:] + (pts[:1] if closed else [])))
    return sum(math.dist(a, b) for a, b in seg)


def polygon_area(pts: Sequence[Point]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2.0


class Backend(ABC):
    name = "base"

    # -- session / documents ---------------------------------------------------------
    @abstractmethod
    def info(self) -> dict: ...
    @abstractmethod
    def new_document(self, template: str | None = None, version: str | None = None) -> dict: ...
    @abstractmethod
    def open_document(self, path: str, read_only: bool = False) -> dict: ...
    @abstractmethod
    def save_document(self, path: str | None = None, fmt: str | None = None) -> dict: ...

    # -- layers ------------------------------------------------------------------------------
    @abstractmethod
    def list_layers(self) -> list[dict]: ...
    @abstractmethod
    def create_layer(self, name: str, color: int | None = None, linetype: str | None = None,
                     lineweight: int | None = None, current: bool = False) -> dict: ...

    # -- drawing -----------------------------------------------------------------------------
    @abstractmethod
    def add_line(self, p1: Point, p2: Point, props: dict) -> str: ...
    @abstractmethod
    def add_polyline(self, points: list[Point], closed: bool, props: dict) -> str: ...
    @abstractmethod
    def add_circle(self, center: Point, radius: float, props: dict) -> str: ...
    @abstractmethod
    def add_arc(self, center: Point, radius: float, start_deg: float, end_deg: float, props: dict) -> str: ...
    @abstractmethod
    def add_text(self, text: str, point: Point, height: float, rotation: float, props: dict) -> str: ...
    @abstractmethod
    def add_mtext(self, text: str, point: Point, width: float, height: float, props: dict) -> str: ...
    @abstractmethod
    def add_point(self, point: Point, props: dict) -> str: ...
    @abstractmethod
    def add_dimension(self, p1: Point, p2: Point, location: Point, angle: float | None, props: dict) -> str: ...
    @abstractmethod
    def add_hatch(self, outer: list[Point], holes: list[list[Point]], pattern: str, scale: float,
                  props: dict) -> str: ...
    @abstractmethod
    def insert_block(self, name: str, point: Point, scale: float, rotation: float,
                     attributes: dict[str, str] | None, props: dict) -> str: ...

    # -- query / modify -------------------------------------------------------------------------
    @abstractmethod
    def list_entities(self, layers: list[str] | None, kinds: list[str] | None,
                      bbox: list[float] | None, limit: int) -> list[dict]: ...
    @abstractmethod
    def get_entity(self, handle: str) -> dict: ...
    @abstractmethod
    def transform(self, handles: list[str], op: str, **kw: Any) -> list[str]: ...
    @abstractmethod
    def set_properties(self, handles: list[str], props: dict) -> list[str]: ...
    @abstractmethod
    def delete(self, handles: list[str]) -> int: ...
    @abstractmethod
    def list_blocks(self) -> list[dict]: ...
