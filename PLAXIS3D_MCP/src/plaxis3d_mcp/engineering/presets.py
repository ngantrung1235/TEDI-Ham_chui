"""Material presets.

Concrete: TCVN 5574:2018 (Kết cấu bê tông và bê tông cốt thép), bảng 10 –
initial modulus Eb for heavy concrete (natural hardening). Values in MPa.

Soils: *indicative* Mohr-Coulomb parameters for preliminary models only. They
must be replaced by values from the project geotechnical report (khảo sát
địa chất theo TCVN 9363:2012 / TCVN 9437:2012) before any design use.

Units follow PLAXIS defaults: kN, m, kN/m2, kN/m3.
"""

from __future__ import annotations

# TCVN 5574:2018 Table 10 – Eb (MPa), heavy concrete, natural hardening
CONCRETE_EB_MPA = {
    "B15": 24000,
    "B20": 27500,
    "B25": 30000,
    "B30": 32500,
    "B35": 34500,
    "B40": 36000,
    "B45": 37000,
    "B50": 38000,
}
REINFORCED_CONCRETE_GAMMA = 25.0  # kN/m3 (TCVN 5574:2018 / TCVN 2737)
CONCRETE_NU = 0.2  # Poisson ratio of concrete, TCVN 5574:2018


def concrete_plate_props(grade: str, thickness: float, name: str | None = None) -> dict:
    """Isotropic elastic plate material for PLAXIS 3D (2023+ property names).

    Plates overlap the soil continuum. For a plate fully embedded in soil the
    PLAXIS manual recommends Gamma_concrete - Gamma_soil; a culvert slab has soil
    on one side only, so the full concrete weight used here slightly
    overestimates self-weight (conservative for slab moments).
    """
    g = grade.upper()
    if g not in CONCRETE_EB_MPA:
        raise RuntimeError(f"Unknown concrete grade {grade}. Use one of {sorted(CONCRETE_EB_MPA)}.")
    E = CONCRETE_EB_MPA[g] * 1000.0  # MPa -> kN/m2
    return {
        "Identification": name or f"RC_{g}_d{int(round(thickness * 1000))}",
        "MaterialType": "Elastic",
        "IsIsotropic": True,
        "d": thickness,
        "Gamma": REINFORCED_CONCRETE_GAMMA,
        "E1": E,
        "nu12": CONCRETE_NU,
    }


# SoilModel enumeration used by PLAXIS: 1 Linear elastic, 2 Mohr-Coulomb,
# 3 Hardening soil, 4 HS small, 5 Soft soil, ...
SOIL_PRESETS = {
    # Compacted embankment fill, K95 (TCVN 9436:2012) – sandy/gravelly soil
    "embankment_K95": {
        "SoilModel": 2, "DrainageType": 0, "gammaUnsat": 19.0, "gammaSat": 20.0,
        "Eref": 25000.0, "nu": 0.3, "cref": 5.0, "phi": 30.0, "psi": 0.0,
        "InterfaceStrengthDetermination": 1, "Rinter": 0.67,
    },
    # Select granular backfill around the culvert (K98)
    "backfill_granular_K98": {
        "SoilModel": 2, "DrainageType": 0, "gammaUnsat": 19.5, "gammaSat": 20.5,
        "Eref": 40000.0, "nu": 0.3, "cref": 1.0, "phi": 34.0, "psi": 4.0,
        "InterfaceStrengthDetermination": 1, "Rinter": 0.67,
    },
    "soft_clay": {
        "SoilModel": 2, "DrainageType": 1, "gammaUnsat": 16.0, "gammaSat": 17.0,
        "Eref": 3000.0, "nu": 0.35, "cref": 8.0, "phi": 5.0, "psi": 0.0,
    },
    "stiff_clay": {
        "SoilModel": 2, "DrainageType": 0, "gammaUnsat": 19.0, "gammaSat": 19.5,
        "Eref": 15000.0, "nu": 0.3, "cref": 25.0, "phi": 18.0, "psi": 0.0,
    },
    "medium_dense_sand": {
        "SoilModel": 2, "DrainageType": 0, "gammaUnsat": 18.0, "gammaSat": 20.0,
        "Eref": 30000.0, "nu": 0.3, "cref": 1.0, "phi": 32.0, "psi": 2.0,
    },
}


def soil_props(preset: str, name: str | None = None, overrides: dict | None = None) -> dict:
    if preset not in SOIL_PRESETS:
        raise RuntimeError(f"Unknown soil preset '{preset}'. Use one of {sorted(SOIL_PRESETS)}.")
    props = {"Identification": name or preset}
    props.update(SOIL_PRESETS[preset])
    props.update(overrides or {})
    return props
