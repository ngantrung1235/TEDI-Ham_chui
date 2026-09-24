"""HL-93 live load on buried structures (box culverts, underpasses).

References (TCVN 11823-3:2017, harmonised with AASHTO LRFD Bridge Design
Specifications, 2012-2014 editions):

* §3.6.1.2.2  Design truck: 35 / 145 / 145 kN, axle spacing 4.3 m (4.3-9.0 m),
  wheel gauge 1.8 m.
* §3.6.1.2.3  Design tandem: 2 x 110 kN, axle spacing 1.2 m.
* §3.6.1.2.5  Tire contact area 510 mm (transverse) x 250 mm (longitudinal).
* §3.6.1.2.6  Fill depth >= 600 mm: wheel load spread over the contact area
  enlarged by LLDF x H (LLDF = 1.15 select granular fill, 1.0 otherwise);
  overlapping areas are combined and the total load is spread uniformly over
  the enclosing rectangle. Live load may be neglected for single-span culverts
  when H > 2.4 m and H > clear span.
* §3.6.1.3.3  Top slabs of box culverts: only the axle loads of the design
  truck / tandem are applied (no lane load).
* §3.6.1.1.2  Multiple presence factor m: 1.20 (1 lane), 1.00 (2), 0.85 (3), 0.65 (>3).
* §3.6.2.2    Dynamic load allowance for buried components:
  IM = 33 (1 - 4.1e-4 D_E) >= 0 %, D_E = cover depth in mm.

Note: AASHTO LRFD 8th/9th editions replaced the LLDF spreading for fills
with a wheel-interaction-depth method; results differ slightly for shallow
fills. Check which edition the project Design Criteria adopts.

In a 3D continuum FE model (PLAXIS 3D) the soil itself spreads the load, so
the wheel loads must be applied at the road surface on the tire contact
areas (``surface_patches``). The spread pressure at the top slab level
(``pressure_at_depth``) is the value used in a conventional frame analysis and
is returned to cross-check the FE result - applying it in the FE model as
well would count the spreading twice.
"""

from __future__ import annotations

from dataclasses import dataclass

TIRE_TRANSVERSE = 0.51  # m
TIRE_LONGITUDINAL = 0.25  # m
WHEEL_GAUGE = 1.8  # m
ADJACENT_WHEEL_GAP = 1.2  # m, between wheels of trucks in adjacent lanes (0.6 m from lane edge)

VEHICLES = {
    # axle positions along travel direction (m) and axle loads (kN)
    "truck": [(0.0, 35.0), (4.3, 145.0), (8.6, 145.0)],
    "tandem": [(0.0, 110.0), (1.2, 110.0)],
}


def multiple_presence(n_lanes: int) -> float:
    return {1: 1.20, 2: 1.00, 3: 0.85}.get(n_lanes, 0.65)


def dynamic_allowance_buried(cover_m: float) -> float:
    """IM in percent (§3.6.2.2)."""
    return max(0.0, 33.0 * (1.0 - 4.1e-4 * cover_m * 1000.0))


@dataclass
class Wheel:
    x: float  # along traffic
    y: float  # transverse
    load: float  # kN


def wheels(vehicle: str, n_lanes: int = 1) -> list[Wheel]:
    """Wheel layout, vehicles side by side in adjacent lanes, centred on y = 0."""
    out = []
    pitch = WHEEL_GAUGE + ADJACENT_WHEEL_GAP
    y0 = -(n_lanes - 1) * pitch / 2.0
    for lane in range(n_lanes):
        yc = y0 + lane * pitch
        for x, axle in VEHICLES[vehicle]:
            for side in (-0.5, 0.5):
                out.append(Wheel(x, yc + side * WHEEL_GAUGE, axle / 2.0))
    return out


def _clusters(rects: list[tuple[float, float, float, float, float]]) -> list[tuple[float, float, float, float, float]]:
    """Merge overlapping rectangles (x1, x2, y1, y2, load) into enclosing rectangles."""
    rects = list(rects)
    merged = True
    while merged:
        merged = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]:
                    rects[i] = (min(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]), a[4] + b[4])
                    rects.pop(j)
                    merged = True
                    break
            if merged:
                break
    return rects


def pressure_at_depth(vehicle: str, n_lanes: int, depth: float, lldf: float) -> dict:
    """Governing uniform pressure (kPa, without m and IM) at ``depth`` below the surface."""
    ex = TIRE_LONGITUDINAL + lldf * depth
    ey = TIRE_TRANSVERSE + lldf * depth
    rects = [(w.x - ex / 2, w.x + ex / 2, w.y - ey / 2, w.y + ey / 2, w.load) for w in wheels(vehicle, n_lanes)]
    best = None
    for x1, x2, y1, y2, load in _clusters(rects):
        area = (x2 - x1) * (y2 - y1)
        p = load / area
        if best is None or p > best["pressure"]:
            best = {"pressure": p, "load": load, "length_along_traffic": x2 - x1, "width_transverse": y2 - y1}
    assert best is not None
    return best


def hl93_through_fill(
    fill_depth: float,
    granular_fill: bool = True,
    max_lanes: int = 1,
    clear_span: float | None = None,
) -> dict:
    """Live load (HL-93) for a buried box culvert under ``fill_depth`` metres of cover."""
    lldf = 1.15 if granular_fill else 1.0
    im = dynamic_allowance_buried(fill_depth)
    warnings: list[str] = []
    if fill_depth < 0.6:
        warnings.append(
            "Cover < 0.6 m: §3.6.1.2.6 spreading does not apply; distribute wheel loads on the top slab "
            "as for a deck slab (§4.6.2.10 / §3.6.1.3.3)."
        )
    if clear_span is not None and fill_depth > 2.4 and fill_depth > clear_span:
        warnings.append("H > 2.4 m and H > clear span: live load may be neglected for a single-span culvert (§3.6.1.2.6).")

    cases = []
    for vehicle in VEHICLES:
        for n in range(1, max_lanes + 1):
            d = pressure_at_depth(vehicle, n, fill_depth, lldf)
            m = multiple_presence(n)
            cases.append(
                {
                    "vehicle": vehicle,
                    "lanes": n,
                    "m": m,
                    **{k: round(v, 3) for k, v in d.items()},
                    "pressure_with_m_IM": round(d["pressure"] * m * (1 + im / 100.0), 3),
                }
            )
    governing = max(cases, key=lambda c: c["pressure_with_m_IM"])

    area = TIRE_TRANSVERSE * TIRE_LONGITUDINAL
    patches = {}
    for vehicle, axles in VEHICLES.items():
        heaviest = max(a for _, a in axles) / 2.0
        patches[vehicle] = {
            "wheel_load_kN": heaviest,
            "patch_m": [TIRE_LONGITUDINAL, TIRE_TRANSVERSE],
            "pressure_kPa": round(heaviest / area, 2),
            "pressure_with_m_IM_kPa": round(heaviest / area * multiple_presence(1) * (1 + im / 100.0), 2),
        }
    return {
        "fill_depth_m": fill_depth,
        "LLDF": lldf,
        "IM_percent": round(im, 2),
        "governing": governing,
        "cases": cases,
        "surface_patches": patches,
        "lane_load": "Not applied to box-culvert top slabs (§3.6.1.3.3).",
        "notes": [
            "Service (unfactored) values. Strength I: gamma_LL = 1.75 applied to LL+IM in the structural check "
            "(TCVN 11823-3:2017 Table 3.4.1-1).",
            "For PLAXIS 3D apply surface_patches at the pavement; use 'governing' only to cross-check.",
        ],
        "warnings": warnings,
    }
