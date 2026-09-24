"""Load combinations (TCVN 11823-3:2017) and RC section checks (TCVN 11823-5:2017).

TCVN 11823 is harmonised with AASHTO LRFD (2014 edition numbering is quoted in
brackets). Units: N, mm, MPa internally; inputs in kN, kNm per metre width.

Combination of FE results
-------------------------
A nonlinear PLAXIS analysis cannot be superposed exactly. The usual design
practice ("factoring of effects", also Eurocode 7 DA2*) is used:

    permanent effect  E_P  = result of the last permanent phase (self weight, EV, EH)
    live-load effect  E_LL = result(traffic phase) - result(permanent phase)
    Strength I:  E_u = eta * (gamma_P * E_P + 1.75 * E_LL),  gamma_P in {max, min}
    Service I :  E_s = E_P + 1.0 * E_LL

Because DC, EV and EH are not separated in one FE run, a single gamma_P is
applied to the permanent effect. The default max value 1.35 is the largest of
DC 1.25, EV (rigid frame) 1.35 and EH at rest 1.35 (Tables 3.4.1-1/-2) and is
therefore conservative; the minimum 0.90 covers the reduced-permanent case.
Separate runs (e.g. with EH only) are needed to reproduce AASHTO 3.11.7's
"50 % reduction of lateral pressure" case exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ES = 200000.0  # MPa, reinforcement modulus (TCVN 11823-5 §5.4.3.2)

LOAD_FACTORS = {
    # TCVN 11823-3:2017 Table 3.4.1-2 (max, min)
    "DC": (1.25, 0.90),
    "DW": (1.50, 0.65),
    "EH_active": (1.50, 0.90),
    "EH_at_rest": (1.35, 0.90),
    "EV_rigid_buried": (1.30, 0.90),
    "EV_rigid_frame": (1.35, 0.90),
    "ES": (1.50, 0.75),
    # Table 3.4.1-1
    "LL_strength_I": (1.75, 1.75),
    "LL_service_I": (1.00, 1.00),
}


@dataclass
class Section:
    """Rectangular RC section, 1 m wide strip.

    ``as_pos``: steel area (mm2/m) on the face in tension under POSITIVE moment
    (PLAXIS local sign), ``as_neg`` on the opposite face. ``cover`` is measured
    to the bar centroid.
    """

    h: float  # mm
    as_pos: float  # mm2/m
    as_neg: float  # mm2/m
    cover: float = 60.0  # mm to bar centre
    fc: float = 30.0  # MPa, f'c (cylinder)
    fy: float = 400.0  # MPa (CB400-V, TCVN 1651-2:2018)
    b: float = 1000.0
    spacing: float = 150.0  # mm, bar spacing for crack control
    gamma_e: float = 0.75  # exposure factor: 1.0 class 1, 0.75 class 2 (§5.7.3.4)
    wc: float = 2400.0  # kg/m3 concrete density for Ec


def beta1(fc: float) -> float:
    """Stress-block factor (§5.7.2.2)."""
    return min(0.85, max(0.65, 0.85 - 0.05 * (fc - 28.0) / 7.0))


def ec(fc: float, wc: float = 2400.0) -> float:
    """Ec = 0.043 K1 wc^1.5 sqrt(f'c), K1 = 1 (§5.4.2.4)."""
    return 0.043 * wc**1.5 * math.sqrt(fc)


def phi_flexure(eps_t: float, fy: float) -> float:
    """Resistance factor, compression- to tension-controlled transition (§5.5.4.2)."""
    eps_cl = fy / ES
    if eps_t <= eps_cl:
        return 0.75
    if eps_t >= 0.005:
        return 0.90
    return 0.75 + 0.15 * (eps_t - eps_cl) / (0.005 - eps_cl)


def _forces(sec: Section, c: float, as_t: float, as_c: float):
    d = sec.h - sec.cover
    dp = sec.cover
    a = min(beta1(sec.fc) * c, sec.h)
    cc = 0.85 * sec.fc * a * sec.b
    eps_c = 0.003 * (c - dp) / c
    fs_c = max(-sec.fy, min(sec.fy, ES * eps_c))
    if a > dp and fs_c > 0:
        fs_c -= 0.85 * sec.fc  # displaced concrete
    eps_t = 0.003 * (d - c) / c
    fs_t = max(-sec.fy, min(sec.fy, ES * eps_t))
    n = cc + as_c * fs_c - as_t * fs_t  # compression positive
    m = cc * (sec.h / 2 - a / 2) + as_c * fs_c * (sec.h / 2 - dp) + as_t * fs_t * (d - sec.h / 2)
    return n, m, eps_t


def flexure_capacity(sec: Section, pu_kN: float, positive: bool) -> dict:
    """phi*Mn (kNm/m) under axial load Pu (kN/m, compression +) by strain compatibility."""
    as_t, as_c = (sec.as_pos, sec.as_neg) if positive else (sec.as_neg, sec.as_pos)
    pu = pu_kN * 1e3
    lo, hi = 1e-3, 20.0 * sec.h
    if _forces(sec, hi, as_t, as_c)[0] < pu:
        return {"phiMn": 0.0, "ok_axial": False, "c": None, "phi": 0.75}
    if _forces(sec, lo, as_t, as_c)[0] > pu:
        return {"phiMn": 0.0, "ok_axial": False, "c": None, "phi": 0.9}
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _forces(sec, mid, as_t, as_c)[0] < pu:
            lo = mid
        else:
            hi = mid
    c = 0.5 * (lo + hi)
    _, m, eps_t = _forces(sec, c, as_t, as_c)
    phi = phi_flexure(eps_t, sec.fy)
    return {"phiMn": phi * m / 1e6, "Mn": m / 1e6, "phi": phi, "c": c, "eps_t": eps_t, "ok_axial": True}


def shear_capacity(sec: Section, vu_kN: float, mu_kNm: float, member: str, fill_depth: float | None) -> dict:
    """phi*Vc (kN/m), no shear reinforcement.

    Culvert slabs with >= 600 mm fill: §5.14.5.3 (AASHTO 2017+: 5.12.7.3)
        Vc = (0.178 sqrt(f'c) + 32 rho Vu de/Mu) b de  <= 0.332 sqrt(f'c) b de,
        and >= 0.25 sqrt(f'c) b de for single-cell boxes cast monolithically.
    Other members (walls, slabs under shallow fill): simplified §5.8.3.4.1,
        beta = 2.0: Vc = 0.083 * 2 * sqrt(f'c) b dv.
    phi_v = 0.90 (§5.5.4.2).
    """
    de = sec.h - sec.cover
    vu, mu = abs(vu_kN) * 1e3, abs(mu_kNm) * 1e6
    if member in ("top_slab", "bottom_slab") and fill_depth is not None and fill_depth >= 0.6:
        rho = max(sec.as_pos, sec.as_neg) / (sec.b * de)
        ratio = 1.0 if mu <= 0 else min(1.0, vu * de / mu)
        vc = (0.178 * math.sqrt(sec.fc) + 32.0 * rho * ratio) * sec.b * de
        vc = min(vc, 0.332 * math.sqrt(sec.fc) * sec.b * de)
        vc = max(vc, 0.25 * math.sqrt(sec.fc) * sec.b * de)
        method = "culvert slab §5.14.5.3"
    else:
        dv = max(0.9 * de, 0.72 * sec.h)
        vc = 0.083 * 2.0 * math.sqrt(sec.fc) * sec.b * dv
        method = "simplified beta=2 §5.8.3.4.1"
    return {"phiVc": 0.9 * vc / 1e3, "method": method}


def crack_control(sec: Section, ms_kNm: float) -> dict:
    """Max bar spacing for crack control under service moment (§5.7.3.4), axial force ignored."""
    positive = ms_kNm >= 0
    as_t = sec.as_pos if positive else sec.as_neg
    d = sec.h - sec.cover
    if as_t <= 0:
        return {"ok": False, "reason": "no tension reinforcement"}
    n = ES / ec(sec.fc, sec.wc)
    rho = as_t / (sec.b * d)
    k = math.sqrt(2 * rho * n + (rho * n) ** 2) - rho * n
    j = 1 - k / 3
    fss = min(abs(ms_kNm) * 1e6 / (as_t * j * d), 0.6 * sec.fy)
    dc = sec.cover
    beta_s = 1 + dc / (0.7 * (sec.h - dc))
    s_max = 123000 * sec.gamma_e / (beta_s * fss) - 2 * dc if fss > 0 else float("inf")
    return {"fss": fss, "s_max": s_max, "spacing": sec.spacing, "ok": sec.spacing <= s_max}


def check_point(sec: Section, mu: float, pu: float, vu: float, ms: float, member: str, fill: float | None) -> dict:
    """Utilisation ratios at one point. mu, vu, ms in kNm/m, kN/m; pu compression +."""
    fl = flexure_capacity(sec, pu, mu >= 0)
    sh = shear_capacity(sec, vu, mu, member, fill)
    cr = crack_control(sec, ms)
    u_m = abs(mu) / fl["phiMn"] if fl["phiMn"] > 0 else math.inf
    u_v = abs(vu) / sh["phiVc"] if sh["phiVc"] > 0 else math.inf
    u_c = sec.spacing / cr["s_max"] if cr.get("s_max", 0) > 0 else math.inf
    return {
        "flexure": round(u_m, 3), "shear": round(u_v, 3), "crack": round(u_c, 3),
        "phiMn": round(fl["phiMn"], 1), "phiVc": round(sh["phiVc"], 1), "s_max": round(cr.get("s_max", 0), 1),
        "phi": round(fl["phi"], 3), "shear_method": sh["method"],
    }


def combine(perm: float, total: float, gamma_p: float, gamma_ll: float, eta: float = 1.0) -> float:
    """eta * (gamma_p * E_P + gamma_ll * (E_total - E_P))."""
    return eta * (gamma_p * perm + gamma_ll * (total - perm))
