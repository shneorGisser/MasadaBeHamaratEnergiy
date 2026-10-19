"""Derived quantities and parameter extraction for experiment 3 (synchronous machine).

One code path for simulated and measured tables. Voltages are LINE values as read on the U1
voltmeter, currents LINE currents; per-winding quantities assume the nameplate connection
(Y: U_winding = U_line/√3). Short-circuit parameters are taken against the AIR-GAP LINE of
the open-circuit characteristic (a steady short circuit is unsaturated), using the OCC of the
project's spec — so a measured short-circuit table is interpreted with the spec's OCC, which
is stated on every such parameter.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from vel.experiments.common import Param, num
from vel.experiments.synchronous.spec import SyncSpec

Row = dict[str, Any]
SQ3 = math.sqrt(3)
LINEAR_TOL = 0.10  # a short-circuit point deviating > 10 % from the median Z is flagged


def _ph(spec: SyncSpec, u_line: float) -> float:
    return u_line / spec.line_factor()


def _i_winding(spec: SyncSpec, i_line: float) -> float:
    return i_line if spec.nameplate.connection == "Y" else i_line / SQ3


def e_airgap(spec: SyncSpec, i_f: float) -> float:
    """Per-winding EMF on the air-gap line (unsaturated OCC) at rated speed."""
    return spec.occ.a * abs(i_f + spec.occ.F_res)


# --------------------------------------------------------------------------- open circuit


def open_circuit(
    rows: list[Row], spec: SyncSpec
) -> tuple[list[Row], list[Param], list[dict[str, Any]]]:
    out = []
    for r in rows:
        up, down = num(r.get("Ef_up")), num(r.get("Ef_down"))
        out.append({**r, "dE": (down - up) if (up is not None and down is not None) else None})
    pts = sorted(
        (float(r["If"]), float(r["Ef_up"]))
        for r in out
        if num(r.get("If")) is not None and num(r.get("Ef_up")) is not None
    )
    params: list[Param] = []
    warnings: list[dict[str, Any]] = []
    if not pts:
        return out, params, [{"code": "no_data", "message": "אין נקודות (If, Ef) מלאות"}]
    zero = [e for i, e in pts if abs(i) < 1e-9]
    if zero:
        params.append(
            Param(
                "E_res",
                "מתח שיורי E0 (If = 0)",
                zero[0],
                "V",
                "Ef(If=0)",
                "consistent",
                note="מקורו בשטף השיורי של הרוטור",
            )
        )
    lin = [(i, e) for i, e in pts if i > 1e-9][:2]
    if lin:
        e0 = zero[0] if zero else 0.0
        slope = (lin[0][1] - e0) / lin[0][0]
        params.append(
            Param(
                "airgap_slope",
                "שיפוע קו הפער (קווי)",
                slope,
                "V/A",
                "(Ef₁ − E0)/If₁",
                "consistent",
                note="מהנקודה הראשונה מעל אפס — האזור הלא רווי",
            )
        )
        un = spec.nameplate.U_n
        if_un = _interp_x(pts, un)
        if if_un is None:
            params.append(
                Param(
                    "If_Un",
                    "If למתח נקוב בריקם",
                    None,
                    "A",
                    "Ef(If) = Un",
                    "consistent",
                    f"Un = {un:g} V לא הושג בתחום שנמדד (מקסימום {max(e for _, e in pts):.4g} V)",
                )
            )
        else:
            params.append(
                Param("If_Un", "If למתח נקוב בריקם", if_un, "A", "Ef(If) = Un", "consistent")
            )
            params.append(
                Param(
                    "k_sat",
                    "מקדם רוויה במתח נקוב",
                    if_un / ((un - e0) / slope),
                    "",
                    "If(Un) / If_קו_הפער(Un)",
                    "consistent",
                )
            )
    if any(num(r.get("dE")) is not None for r in out):
        d = [abs(float(r["dE"])) for r in out if num(r.get("dE")) is not None and num(r.get("If"))]
        if d:
            params.append(
                Param(
                    "hyst_max",
                    "הפרש מרבי עלייה/ירידה",
                    max(d),
                    "V",
                    "max |Ef↓ − Ef↑|",
                    "consistent",
                )
            )
    return out, params, warnings


def _interp_x(pts: list[tuple[float, float]], y: float) -> float | None:
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        if (y0 - y) * (y1 - y) <= 0 and y1 != y0:
            return x0 + (y - y0) * (x1 - x0) / (y1 - y0)
    return None


# --------------------------------------------------------------------------- short circuit


def short_circuit(
    rows: list[Row], spec: SyncSpec
) -> tuple[list[Row], list[Param], list[dict[str, Any]]]:
    ra = spec.ecm.Ra
    out: list[Row] = []
    z: dict[str, list[tuple[int, float]]] = {"3": [], "2": [], "1": []}
    for idx, r in enumerate(rows):
        i_f = num(r.get("If"))
        ik3, ik2, ik1 = num(r.get("Ik3")), num(r.get("Ik2")), num(r.get("Ik1"))
        row = {
            **r,
            "r2": (ik2 / ik3) if (ik2 is not None and ik3) else None,
            "r1": (ik1 / ik3) if (ik1 is not None and ik3) else None,
        }
        out.append(row)
        if i_f is None or i_f <= 0:
            continue
        e = e_airgap(spec, i_f)
        for key, ik, fac in (("3", ik3, 1.0), ("2", ik2, SQ3), ("1", ik1, 3.0)):
            if ik is not None and ik > 0:
                z[key].append((idx, fac * e / _i_winding(spec, ik)))
    warnings: list[dict[str, Any]] = []
    med: dict[str, float] = {}
    for key, vals in z.items():
        if not vals:
            continue
        m = statistics.median(v for _, v in vals)
        med[key] = statistics.fmean(v for _, v in vals if abs(v - m) <= LINEAR_TOL * m)
        for idx, v in vals:
            if abs(v - m) > LINEAR_TOL * m:
                warnings.append(
                    {
                        "code": "sc_nonlinear",
                        "row": idx,
                        "column": f"Ik{key}",
                        "message": f"שורה {idx + 1}: Ik({key}) אינו על הקו הישר של אופיין הקצר "
                        f"(עכבה {v:.4g} Ω מול חציון {m:.4g} Ω, סטייה {abs(v - m) / m:.0%}). אופיין "
                        "קצר מתמיד אינו רווי ולכן ישר — כנראה טעות קריאה; הנקודה לא שימשה לחישוב",
                    }
                )
    note = "E_ag = קו הפער של עקומת הריקם מהמפרט; לפאזה של חיבור הכוכב"
    params: list[Param] = []
    xs = x2 = None
    if "3" in med:
        xs2 = med["3"] ** 2 - ra**2
        xs = math.sqrt(xs2) if xs2 > 0 else None
        params.append(
            Param(
                "Xs",
                "היגב סינכרוני (לא רווי) Xs",
                xs,
                "Ω",
                "√((E_ag/Ik3)² − Ra²)",
                "consistent",
                None if xs else "Ik3 גדול מדי ביחס ל-Ra",
                note,
            )
        )
        params.append(
            Param(
                "Xs_pu",
                "Xs ביחידות יחסיות",
                (xs / spec.Z_base) if xs else None,
                "pu",
                "Xs / Z_base",
                "consistent",
            )
        )
    if "2" in med and xs:
        x12 = med["2"] ** 2 - (2 * ra) ** 2
        x2 = math.sqrt(x12) - xs if x12 > 0 else None
        params.append(
            Param(
                "X2",
                "היגב סדר שלילי X2",
                x2,
                "Ω",
                "√((√3·E/Ik2)² − (2Ra)²) − Xs",
                "consistent",
                None,
                note,
            )
        )
    if "1" in med and xs and x2 is not None:
        x120 = med["1"] ** 2 - (3 * ra) ** 2
        x0 = math.sqrt(x120) - xs - x2 if x120 > 0 else None
        params.append(
            Param(
                "X0",
                "היגב סדר אפס X0",
                x0,
                "Ω",
                "√((3E/Ik1)² − (3Ra)²) − Xs − X2",
                "consistent",
                None,
                note,
            )
        )
    # short-circuit ratio: field current for rated voltage at no load / for rated current in SC
    if "3" in med:
        i_f_isc = _if_for_current(spec, spec.nameplate.I_n, med["3"])
        params.append(
            Param(
                "If_sc",
                "If לזרם נקוב בקצר תלת-פזי",
                i_f_isc,
                "A",
                "E_ag(If)/|Z1| = In",
                "consistent",
            )
        )
    return out, params, warnings


def _if_for_current(spec: SyncSpec, i_line: float, z1: float) -> float:
    e_needed = z1 * _i_winding(spec, i_line)
    return e_needed / spec.occ.a - spec.occ.F_res


# --------------------------------------------------------------------------- loads


def load(rows: list[Row], spec: SyncSpec) -> list[Row]:
    out = []
    for r in rows:
        p = num(r.get("P_W"))
        u, i = num(r.get("U1")), num(r.get("I1"))
        p1 = 3 * p if p is not None else None
        out.append({**r, "P": p1, "S": (SQ3 * u * i) if (u and i) else None})
    return out


def zpf(rows: list[Row], spec: SyncSpec, i_const: float) -> tuple[list[Row], list[Param]]:
    """Potier: on a zero-power-factor load U_ph + I·X_l = OCC(If − k_a·I) (all in quadrature,
    Ra neglected). With ≥ 2 points and the spec's OCC, X_l and k_a follow by least squares."""
    pts = [
        (float(r["If"]), float(r["U1"]))
        for r in rows
        if num(r.get("If")) is not None and num(r.get("U1")) is not None
    ]
    params: list[Param] = []
    if len(pts) < 2 or i_const <= 0:
        return rows, params
    iw = _i_winding(spec, i_const)
    best: tuple[float, float, float] | None = None
    occ = spec.occ
    for ka_i in range(0, 801):
        ka = ka_i * 0.01
        # for fixed k_a the residual is linear in X_l → closed-form least squares
        res = [occ.emf(i_f + occ.F_res - ka * iw) - _ph(spec, u) for i_f, u in pts]
        xl = sum(res) / (len(res) * iw)
        sse = sum((x - xl * iw) ** 2 for x in res)
        if best is None or sse < best[0]:
            best = (sse, xl, ka)
    assert best is not None
    sse, xl, ka = best
    rms = math.sqrt(sse / len(pts))
    note = f"התאמה לעקומת הריקם מהמפרט; שארית rms {rms:.3g} V; Ra מוזנח"
    params += [
        Param(
            "Xl_potier",
            "היגב פוטייה X_l",
            xl,
            "Ω",
            "U + I·X_l = OCC(If − k_a·I)",
            "consistent",
            None if xl > 0 else "יצא שלילי — הנקודות אינן עקביות",
            note,
        ),
        Param(
            "k_a",
            "תגובת עוגן k_a",
            ka,
            "A/A",
            "הזזה אופקית של משולש פוטייה",
            "consistent",
            None,
            note,
        ),
    ]
    return rows, params


def v_curves(rows: list[Row]) -> tuple[list[Row], list[Param]]:
    out = [
        {**r, "P1": (3 * float(r["P_W"])) if num(r.get("P_W")) is not None else None} for r in rows
    ]
    params: list[Param] = []
    groups: dict[float, list[Row]] = {}
    for r in out:
        if num(r.get("P_set")) is not None and num(r.get("Ia")) is not None:
            groups.setdefault(float(r["P_set"]), []).append(r)
    for p, rs in sorted(groups.items()):
        best = min(rs, key=lambda r: float(r["Ia"]))
        params.append(
            Param(
                f"If_min_{p:g}",
                f"If בזרם מינימלי (P = {p:g} W)",
                num(best.get("If")),
                "A",
                "argmin Ia(If)",
                "consistent",
                note="קרוב ל-cos φ = 1; בדיוק רק אם נמדדה הנקודה עצמה",
            )
        )
    return out, params


def dc_resistance(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    from vel.experiments.transformer3ph.derive import dc_resistance as _dc

    return _dc(rows)


def plausibility(kind: str, rows: list[Row], spec: SyncSpec) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        pf = num(r.get("pf"))
        if pf is not None and not 0 <= pf <= 1:
            out.append(
                {
                    "code": "pf_range",
                    "row": i,
                    "column": "pf",
                    "message": f"שורה {i + 1}: cos φ = {pf:g} מחוץ ל-[0, 1]",
                }
            )
    if kind == "open_circuit":
        seq = [(num(r.get("If")), num(r.get("Ef_up"))) for r in rows]
        seq2 = [(a, b) for a, b in seq if a is not None and b is not None]
        for (i0, e0), (i1, e1) in zip(seq2, seq2[1:], strict=False):
            if i1 > i0 and e1 < e0:
                out.append(
                    {
                        "code": "occ_not_monotonic",
                        "column": "Ef_up",
                        "message": f"Ef יורד ({e0:g} → {e1:g} V) בזמן ש-If עולה "
                        f"({i0:g} → {i1:g} A) — האם הערכים נרשמו בסדר הפוך?",
                    }
                )
                break
        downs = [(num(r.get("If")), num(r.get("Ef_down"))) for r in rows]
        d2 = [(a, b) for a, b in downs if a is not None and b is not None]
        if len(d2) >= 3:
            inc = sum(
                1
                for (a0, b0), (a1, b1) in zip(d2, d2[1:], strict=False)
                if (a1 - a0) * (b1 - b0) < 0
            )
            if inc > len(d2) // 2:
                out.append(
                    {
                        "code": "occ_down_reversed",
                        "column": "Ef_down",
                        "message": "עמודת הירידה יורדת כש-If עולה — כנראה נרשמה בסדר "
                        "הפוך לזרמי העירור (בדוק את שיוך הערכים לשורות)",
                    }
                )
    if kind == "load_characteristic":
        pts = [(num(r.get("I1")), num(r.get("U1"))) for r in rows]
        p2 = [(a, b) for a, b in pts if a is not None and b is not None]
        for (i0, _u0), (i1, _u1) in zip(p2, p2[1:], strict=False):
            if i1 < i0:
                out.append(
                    {
                        "code": "load_not_monotonic",
                        "column": "I1",
                        "message": f"I1 יורד ({i0:g} → {i1:g} A) בין שורות סמוכות — "
                        "טעות הקלדה או יחידות (mA/A)?",
                    }
                )
                break
    return out
