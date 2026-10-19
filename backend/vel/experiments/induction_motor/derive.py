"""Derived quantities and parameter extraction for experiment 2.

Used for BOTH simulated and measured tables (one code path). Conventions follow the manual:
U is the LINE voltage, I the LINE current, P the TOTAL three-phase power (single wattmeter on
one phase × 3). Admittances/impedances are per phase of the STAR equivalent — for a Δ motor
that is not the per-winding value (Z_winding = 3·Z_star); the conversion is stated in notes.

Manual formulas (p. 1–2): Y0 = √3·I0/U1, g0 = P0/U1², b0 = √(Y0² − g0²),
cos φ = P/(U·I·√3), Z_k = U_k/(√3·I_k), r_k = P_k/(3·I_k²), x_k = √(Z_k² − r_k²),
P2 = M·n/9.55, s = (n_s − n)/n_s. Unlike experiment 1 these are mutually consistent, so a
single formula set is reported.
"""

from __future__ import annotations

import math
from typing import Any

from vel.experiments.common import Param, num
from vel.experiments.induction_motor.spec import MotorSpec

Row = dict[str, Any]
SQ3 = math.sqrt(3)


def _times3(v: Any) -> float | None:
    x = num(v)
    return 3 * x if x is not None else None


def _pf(p: float | None, u: float | None, i: float | None) -> float | None:
    if p is None or u is None or i is None or u * i <= 0:
        return None
    return p / (SQ3 * u * i)


def _nearest(rows: list[Row], key: str, target: float, needed: tuple[str, ...]) -> int | None:
    cands = [
        i for i, r in enumerate(rows) if all(num(r.get(k)) is not None for k in (key, *needed))
    ]
    if not cands:
        return None
    return min(cands, key=lambda i: abs(float(rows[i][key]) - target))


def r1_star(spec: MotorSpec) -> float:
    """Stator resistance of the star equivalent (Δ winding → R/3)."""
    r = spec.ecm.R1
    return r if spec.nameplate.connection == "Y" else r / 3


def _sqrt_diff(a2: float, b2: float) -> tuple[float | None, str | None]:
    d = a2 - b2
    if d < 0:
        return None, f"הביטוי מתחת לשורש שלילי ({d:.4g}); אין פתרון ממשי — בדוק את המדידות"
    return math.sqrt(d), None


# --------------------------------------------------------------------------- no load


def no_load(
    rows: list[Row], spec: MotorSpec
) -> tuple[list[Row], list[Param], dict[str, Any], list[dict[str, Any]]]:
    out = []
    for r in rows:
        p0 = _times3(r.get("P_W"))
        u, i0 = num(r.get("U1L")), num(r.get("I0"))
        out.append({**r, "P0": p0, "pf_calc": _pf(p0, u, i0)})
    warnings: list[dict[str, Any]] = []
    k = _nearest(out, "U1L", spec.nameplate.U_n, ("I0", "P0"))
    if k is None:
        return out, [], {}, [{"code": "rated_point_missing", "message": "אין שורה מלאה (U, I0, P)"}]
    r = out[k]
    u, i0, p0 = float(r["U1L"]), float(r["I0"]), float(r["P0"])
    if abs(u - spec.nameplate.U_n) > 0.02 * spec.nameplate.U_n:
        warnings.append(
            {
                "code": "rated_point_missing",
                "message": f"אין מדידה ב-Un = {spec.nameplate.U_n:g} V; הפרמטרים חושבו ב-{u:g} V",
            }
        )
    params: list[Param] = []
    if u <= 0 or i0 <= 0:
        return out, [], {}, [{"code": "zero_reading", "message": "מתח או זרם אפס"}]
    y0 = SQ3 * i0 / u
    g0 = p0 / u**2
    b0, why = _sqrt_diff(y0**2, g0**2)
    params += [
        Param("Y0", "אדמיטנס ריקם Y0", y0, "S", "√3·I0 / U1", "consistent"),
        Param("g0", "מוליכות g0", g0, "S", "P0 / U1²", "consistent"),
        Param("b0", "סוספטנס b0", b0, "S", "√(Y0² − g0²)", "consistent", why),
        Param("pf0", "cos φ0", _pf(p0, u, i0), "", "P0 / (√3·U1·I0)", "consistent"),
    ]
    p_rot = p0 - 3 * i0**2 * r1_star(spec)
    params.append(
        Param(
            "P_fe_fw",
            "הפסדי ברזל + חיכוך ואוורור",
            p_rot,
            "W",
            "P0 − 3·I0²·R1",
            "consistent",
            note="R1 מתוך מפרט המנוע (או ממדידת DC). הפסדי הנחושת ברוטור בריקם זניחים",
        )
    )
    # Separation of mechanical losses: P0 − 3·I0²·R1 = P_fw + k·U² → intercept at U = 0.
    pts = [
        (float(x["U1L"]) ** 2, float(x["P0"]) - 3 * float(x["I0"]) ** 2 * r1_star(spec))
        for x in out
        if all(num(x.get(c)) is not None for c in ("U1L", "I0", "P0"))
    ]
    if len({round(p[0], 6) for p in pts}) >= 3:
        n = len(pts)
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        sxx = sum((p[0] - mx) ** 2 for p in pts)
        slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
        intercept = my - slope * mx
        params.append(
            Param(
                "P_fw_est",
                "הפסדי חיכוך ואוורור (אקסטרפולציה ל-U=0)",
                intercept,
                "W",
                "P0 − 3I0²R1 = P_fw + k·U²",
                "consistent",
                note="רגרסיה ליניארית ב-U². מדויקת רק כשהמהירות כמעט קבועה בכל הנקודות",
            )
        )
    return out, params, {"row": k, "U1L": u}, warnings


# --------------------------------------------------------------------------- locked rotor


def locked_rotor(
    rows: list[Row], spec: MotorSpec
) -> tuple[list[Row], list[Param], dict[str, Any], list[dict[str, Any]]]:
    out = []
    for r in rows:
        pk = _times3(r.get("P_W"))
        out.append({**r, "P_k": pk, "pf_calc": _pf(pk, num(r.get("U_k")), num(r.get("I_k")))})
    k = _nearest(out, "I_k", spec.nameplate.I_n, ("U_k", "P_k"))
    if k is None:
        return out, [], {}, [{"code": "rated_point_missing", "message": "אין שורה מלאה"}]
    r = out[k]
    u, i, p = float(r["U_k"]), float(r["I_k"]), float(r["P_k"])
    warnings: list[dict[str, Any]] = []
    if abs(i - spec.nameplate.I_n) > 0.05 * spec.nameplate.I_n:
        warnings.append(
            {
                "code": "rated_point_missing",
                "message": f"אין מדידה ב-In = {spec.nameplate.I_n:g} A; חושב ב-{i:.4g} A",
            }
        )
    if i <= 0 or u <= 0:
        return out, [], {}, [{"code": "zero_reading", "message": "מתח או זרם אפס"}]
    zk = u / (SQ3 * i)
    rk = p / (3 * i**2)
    xk, why = _sqrt_diff(zk**2, rk**2)
    r2 = rk - r1_star(spec)
    conn_note = "" if spec.nameplate.connection == "Y" else " · ליפוף בחיבור Δ: Z_ליפוף = 3·Z"
    params = [
        Param(
            "Z_k", "עכבת קצר Zk", zk, "Ω", "Uk / (√3·Ik)", "consistent", note=conn_note.strip(" ·")
        ),
        Param("r_k", "התנגדות קצר rk", rk, "Ω", "Pk / (3·Ik²)", "consistent"),
        Param("x_k", "היגב קצר xk = X1 + X2'", xk, "Ω", "√(Zk² − rk²)", "consistent", why),
        Param("pf_k", "cos φk", _pf(p, u, i), "", "Pk / (√3·Uk·Ik)", "consistent"),
        Param(
            "R2p_est",
            "התנגדות רוטור מוחזרת R2' (הערכה)",
            r2 if r2 > 0 else None,
            "Ω",
            "rk − R1",
            "consistent",
            None if r2 > 0 else "rk קטן מ-R1 — סתירה בין המדידות למפרט",
            note="מקורב: ענף המגנוט מוזנח ברוטור נעול. R1 מתוך המפרט",
        ),
        Param(
            "I_start_est",
            "זרם התנעה במתח נקוב (אקסטרפולציה)",
            i * spec.nameplate.U_n / u,
            "A",
            "Ik · Un / Uk",
            "consistent",
            note="מניח עכבה קבועה; ברוויה של שיני הרוטור הזרם האמיתי גבוה יותר",
        ),
    ]
    return out, params, {"row": k, "I_k": i}, warnings


# --------------------------------------------------------------------------- load


def load(rows: list[Row], spec: MotorSpec, f: float | None = None) -> list[Row]:
    ns = 120 * (f or spec.nameplate.f_n) / spec.nameplate.poles
    out = []
    for r in rows:
        p1 = _times3(r.get("P_W"))
        m, n = num(r.get("M")), num(r.get("n"))
        u, i = num(r.get("U1L")), num(r.get("I1"))
        p2 = m * n / 9.55 if (m is not None and n is not None) else None
        out.append(
            {
                **r,
                "P1": p1,
                "P2": p2,
                "eta": (p2 / p1) if (p2 is not None and p1) else None,
                "slip": (ns - n) / ns if n is not None else None,
                "pf_calc": _pf(p1, u, i),
            }
        )
    return out


def inverter(rows: list[Row], spec: MotorSpec) -> list[Row]:
    out = []
    for r in rows:
        f = num(r.get("f"))
        base = load([{**r, "U1L": r.get("U_out"), "I1": r.get("I_out")}], spec, f if f else None)[0]
        u = num(r.get("U_out"))
        base.pop("U1L", None)
        base.pop("I1", None)
        if f is None:
            base["slip"] = None
        base["U_per_f"] = (u / f) if (u is not None and f) else None
        out.append(base)
    return out


def dc_resistance(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    from vel.experiments.transformer3ph.derive import dc_resistance as _dc

    return _dc(rows)


# --------------------------------------------------------------------------- plausibility


def plausibility(kind: str, rows: list[Row], spec: MotorSpec) -> list[dict[str, Any]]:
    """Checks that point at entries that cannot all be right. Values are never changed."""
    out: list[dict[str, Any]] = []
    cols = {
        "no_load": ("U1L", "I0", "P_W", "pf"),
        "locked_rotor": ("U_k", "I_k", "P_W", "pf"),
        "load": ("U1L", "I1", "P_W", "pf"),
        "inverter": ("U_out", "I_out", "P_W", "pf"),
    }.get(kind)
    ns = spec.n_sync
    for i, r in enumerate(rows):
        if cols:
            uk, ik, pk, pfk = cols
            u, cur, p, pf = num(r.get(uk)), num(r.get(ik)), num(r.get(pk)), num(r.get(pfk))
            if pf is not None and not (0 <= pf <= 1):
                out.append(
                    {
                        "code": "pf_range",
                        "row": i,
                        "column": pfk,
                        "message": f"שורה {i + 1}: cos φ = {pf:g} מחוץ ל-[0, 1]",
                    }
                )
            if u and cur and p is not None:
                s_ph = u / SQ3 * cur
                if abs(p) > 1.05 * s_ph:
                    out.append(
                        {
                            "code": "power_exceeds_apparent",
                            "row": i,
                            "column": pk,
                            "message": f"שורה {i + 1}: קריאת מד ההספק {p:.4g} W גדולה מ-U·I/√3 = "
                            f"{s_ph:.4g} VA — בלתי אפשרי (יחידה? מתח קווי/פאזי?)",
                        }
                    )
                elif pf is not None and abs(pf - p / s_ph) > 0.1:
                    out.append(
                        {
                            "code": "pf_inconsistent",
                            "row": i,
                            "column": pfk,
                            "message": f"שורה {i + 1}: cos φ = {pf:g} אבל 3P/(√3·U·I) = "
                            f"{p / s_ph:.3f}",
                        }
                    )
        if kind in ("load", "no_load"):
            n = num(r.get("n"))
            if n is not None and n > ns * 1.001:
                out.append(
                    {
                        "code": "speed_above_sync",
                        "row": i,
                        "column": "n",
                        "message": f"שורה {i + 1}: n = {n:g} סל״ד גבוה מהמהירות הסינכרונית "
                        f"{ns:g} — מנוע לא יכול להגיע לכך (מספר קטבים? תדר?)",
                    }
                )
        if kind == "load":
            p1, m, n = _times3(r.get("P_W")), num(r.get("M")), num(r.get("n"))
            if p1 and m is not None and n is not None and m * n / 9.55 > p1:
                out.append(
                    {
                        "code": "efficiency_above_one",
                        "row": i,
                        "column": "M",
                        "message": f"שורה {i + 1}: P2 = M·n/9.55 = {m * n / 9.55:.4g} W "
                        f"גדול מ-P1 = {p1:.4g} W — נצילות מעל 1",
                    }
                )
    return out
