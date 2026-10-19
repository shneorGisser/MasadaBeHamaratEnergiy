"""Parameter extraction from test readings (works identically on simulated or measured data).

Two formula sets are reported side by side:

* "consistent" — per-phase, star-equivalent quantities. P is the TOTAL three-phase power
  (single-phase wattmeter × 3, as the manual instructs), U_L / I_L are line quantities.
* "manual" — the formulas exactly as printed in the lab manual, evaluated with line voltage
  and total power. They mix line and phase quantities; where that makes a square root of a
  negative number the value is reported as undefined with the reason, never as NaN or 0.
"""

from __future__ import annotations

import math
from typing import Any

from vel.experiments.common import Param

__all__ = ["Param"]

SQ3 = math.sqrt(3)


def _sqrt_diff(a2: float, b2: float) -> tuple[float | None, str | None]:
    d = a2 - b2
    if d < 0:
        return None, f"הביטוי מתחת לשורש שלילי ({d:.4g}); אין פתרון ממשי"
    return math.sqrt(d), None


def no_load_parameters(
    U_L: float, I0: float, P0: float, U_ph1: float, U_ph2: float, U_L2: float
) -> list[Param]:
    """U_L line voltage [V], I0 line current [A], P0 total three-phase power [W]."""
    out: list[Param] = []
    if U_L <= 0 or I0 <= 0:
        reason = "מתח או זרם אפס — לא ניתן לחשב"
        return [Param("g_m", "מוליכות ענף מגנוט g_m", None, "S", "", "consistent", reason)]
    out.append(
        Param(
            "a_ph",
            "יחס השנאה (פאזי) U1ph/U2ph",
            U_ph1 / U_ph2 if U_ph2 > 0 else None,
            "",
            "U1ph / U2ph",
            "consistent",
            None if U_ph2 > 0 else "U2ph = 0",
        )
    )
    out.append(
        Param(
            "a_line",
            "יחס מתחים קוויים U1/U2",
            U_L / U_L2 if U_L2 > 0 else None,
            "",
            "U1L / U2L",
            "consistent",
            None if U_L2 > 0 else "U2L = 0",
        )
    )
    S = SQ3 * U_L * I0
    out.append(
        Param("cos_phi0", "גורם הספק בריקם cos φ0", P0 / S, "", "P0 / (√3·U_L·I0)", "consistent")
    )
    Y = SQ3 * I0 / U_L
    g = P0 / U_L**2
    b, why = _sqrt_diff(Y**2, g**2)
    out += [
        Param(
            "Y_m", "אדמיטנס ענף מגנוט Y_m (לפאזה, כוכב שקול)", Y, "S", "√3·I0 / U_L", "consistent"
        ),
        Param("g_m", "מוליכות g_m", g, "S", "P0 / U_L²", "consistent"),
        Param("b_m", "סוספטנס b_m", b, "S", "√(Y_m² − g_m²)", "consistent", why),
        Param(
            "R_fe",
            "התנגדות הפסדי ברזל R_Fe = 1/g_m",
            1 / g if g > 0 else None,
            "Ω",
            "1 / g_m",
            "consistent",
            None if g > 0 else "g_m = 0",
        ),
        Param(
            "X_m",
            "ריאקטנס מגנוט X_m = 1/b_m",
            (1 / b) if b else None,
            "Ω",
            "1 / b_m",
            "consistent",
            why if b is None else None,
        ),
    ]
    # Manual's printed formulas: Y_m = I0/V1, g_m = P0/U1², b_m = √(Y_m² − g_m²) with V1 = U1 = U_L
    Ym_man = I0 / U_L
    bm_man, why_m = _sqrt_diff(Ym_man**2, g**2)
    out += [
        Param(
            "Y_m_manual",
            "Y_m לפי החוברת",
            Ym_man,
            "S",
            "I0 / V1  (V1 = מתח קווי)",
            "manual",
            note="קטן פי √3 מהערך העקבי אם V1 הוא מתח קווי",
        ),
        Param("b_m_manual", "b_m לפי החוברת", bm_man, "S", "√(Y_m² − g_m²)", "manual", why_m),
    ]
    return out


def short_circuit_parameters(
    U_k: float, I_k: float, P_k: float, U1n: float, I1n: float
) -> list[Param]:
    """U_k line voltage, I_k primary line current, P_k total three-phase power."""
    if I_k <= 0:
        return [Param("Z_k", "Z_k", None, "Ω", "", "consistent", "זרם קצר אפס")]
    S = SQ3 * U_k * I_k
    Z = U_k / (SQ3 * I_k)
    r = P_k / (3 * I_k**2)
    x, why = _sqrt_diff(Z**2, r**2)
    Z_man = U_k / I_k
    r_man = P_k / I_k**2
    x_man, why_man = _sqrt_diff(Z_man**2, r_man**2)
    # scale to rated current (linear series branch) for u_k%
    U_k_rated = U_k * I1n / I_k
    return [
        Param(
            "cos_phik",
            "גורם הספק בקצר cos φk",
            P_k / S if S > 0 else None,
            "",
            "P_k / (√3·U_k·I_k)",
            "consistent",
        ),
        Param("Z_k", "עכבת קצר Z_k (לפאזה, כוכב שקול)", Z, "Ω", "U_k / (√3·I_k)", "consistent"),
        Param("r_k", "התנגדות קצר r_k", r, "Ω", "P_k / (3·I_k²)", "consistent"),
        Param("x_k", "ריאקטנס קצר x_k", x, "Ω", "√(Z_k² − r_k²)", "consistent", why),
        Param(
            "u_k_pct",
            "מתח קצר u_k%",
            100 * U_k_rated / U1n,
            "%",
            "100·U_k(I_n) / U_1n",
            "consistent",
            note="U_k מוקטן לזרם נומינלי בהנחת ענף טורי ליניארי",
        ),
        Param("Z_k_manual", "Z_k לפי החוברת", Z_man, "Ω", "U_k / I_1", "manual"),
        Param("r_k_manual", "r_k לפי החוברת", r_man, "Ω", "P_k / I_1²", "manual"),
        Param(
            "x_k_manual",
            "x_k לפי החוברת",
            x_man,
            "Ω",
            "√(Z_k² − r_k²)",
            "manual",
            why_man,
            note="r_k/Z_k = √3·cos φk; שלילי מתחת לשורש כאשר cos φk > 0.577",
        ),
    ]


def efficiency_table(
    S_n: float, P0: float, Pk_rated: float, betas: list[float], cos_phis: list[float]
) -> dict[str, Any]:
    """η(β) = β S_n cosφ / (β S_n cosφ + P0 + β² Pk) — conventional-loss method."""
    rows = []
    for beta in betas:
        row: dict[str, float | None] = {"beta": beta}
        for c in cos_phis:
            p2 = beta * S_n * c
            den = p2 + P0 + beta**2 * Pk_rated
            row[f"eta_{c:g}"] = (p2 / den) if den > 0 else None
        rows.append(row)
    cols = [{"key": "beta", "label_he": "β = I2/I2n", "unit": ""}] + [
        {"key": f"eta_{c:g}", "label_he": f"η ב-cos φ2 = {c:g}", "unit": ""} for c in cos_phis
    ]
    beta_opt = math.sqrt(P0 / Pk_rated) if Pk_rated > 0 else None
    return {"columns": cols, "rows": rows, "beta_eta_max": beta_opt}


def vector_group_parameters(U_aAB: float, U_aAb: float, U_Bb: float) -> list[Param]:
    """Manual section 6: cos(B1·aA·b1) = (|aAB|² + |aAb|² − |Bb|²) / (2·|aAB|·|aAb|)."""
    if U_aAB <= 0 or U_aAb <= 0:
        return [Param("theta", "זווית", None, "°", "", "manual", "מתח אפס — הזווית אינה מוגדרת")]
    c = (U_aAB**2 + U_aAb**2 - U_Bb**2) / (2 * U_aAB * U_aAb)
    if c > 1 + 1e-9 or c < -1 - 1e-9:
        return [
            Param(
                "theta",
                "זווית",
                None,
                "°",
                "",
                "manual",
                f"cos = {c:.4f} מחוץ ל-[−1, 1]: המדידות אינן יכולות ליצור משולש",
            )
        ]
    theta = math.degrees(math.acos(max(-1.0, min(1.0, c))))
    a = round(theta / 30) % 12
    b = round((360 - theta) / 30) % 12
    cands = sorted({a, b})
    return [
        Param(
            "cos_theta",
            "cos של הזווית (משפט הקוסינוס)",
            c,
            "",
            "(aAB² + aAb² − Bb²) / (2·aAB·aAb)",
            "manual",
        ),
        Param("theta", "הזווית הפנימית θ", theta, "°", "arccos(…)", "manual"),
        Param(
            "clock_candidates",
            "מספרי שעון אפשריים (θ/30 או (360−θ)/30)",
            None if len(cands) > 1 else float(cands[0]),
            "",
            "θ/30 , (360° − θ)/30",
            "manual",
            "יש להכריע לפי ציור הפאזורים (פנימית/חיצונית)" if len(cands) > 1 else None,
            note=" או ".join(str(x) for x in cands),
        ),
    ]
