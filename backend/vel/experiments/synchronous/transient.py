"""Studies in the time domain: the sudden three-phase short circuit of the synchronous
generator at no load, and its synchronisation to the grid.

The steady-state short-circuit study gives the sustained current E/Xs. The sudden short circuit
shows the sub-transient and transient currents before it, and the DC offset that depends on
the rotor position at the fault. The run is checked twice: the sustained current against the
steady-state model, and the AC envelope against the IEEE Std 115 formula."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from scipy.optimize import brentq

from vel.engine.simulate import operating_point
from vel.engine.transient.synchronous import (
    SmDynamics,
    ieee_envelope,
    saturate,
    sudden_short_circuit,
    synchronize,
)
from vel.experiments.common import Outcome, Param, StudyError, col
from vel.experiments.synchronous import templates
from vel.experiments.synchronous.spec import SyncSpec

# not in the spec: assumed for a small laboratory machine
XD1_OVER_XD2 = 1.5
TD01 = 0.3  # s
TD02 = 0.02  # s
TQ02 = 0.03  # s
J_SYNC_ASSUMED = 0.02  # kg·m², machine + coupled drive


class SuddenScCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_f: float = Field(default=0.4, gt=0, le=100)
    Xd2: float | None = Field(default=None, gt=0, le=1e5, description="X''d [Ω]; None = X2")
    Xd1: float | None = Field(default=None, gt=0, le=1e5, description="X'd [Ω]; None = 1.5·X''d")
    Td01: float = Field(default=TD01, gt=0, le=20)
    Td02: float = Field(default=TD02, gt=0, le=1)
    Tq02: float = Field(default=TQ02, gt=0, le=1)
    angle_deg: float = Field(default=0.0, ge=-360, le=360)
    t_end: float = Field(default=1.0, gt=0, le=10)


def dynamics(spec: SyncSpec, case: SuddenScCase) -> SmDynamics:
    xs = spec.Xs_unsat
    xd2 = case.Xd2 or spec.ecm.X2
    xd1 = case.Xd1 or XD1_OVER_XD2 * xd2
    return SmDynamics(
        R=spec.ecm.Ra,
        Xl=spec.ecm.Xl,
        Xd=xs,
        Xq=xs,
        Xd1=xd1,
        Xd2=xd2,
        Xq2=xd2,
        Td01=case.Td01,
        Td02=case.Td02,
        Tq02=case.Tq02,
        f=spec.nameplate.f_n,
    )


def run_sudden_sc(spec: SyncSpec, case: SuddenScCase) -> Outcome:
    m = dynamics(spec, case)
    try:
        m.check()
    except ValueError as exc:
        raise StudyError("invalid_input", f"ריאקטנסים לא עקביים: {exc}") from exc
    occ = spec.occ
    e_air = occ.a * (case.I_f + occ.F_res)  # RMS per winding, air-gap line
    e_occ = occ.emf(case.I_f + occ.F_res)  # what the machine really shows at no load
    try:
        r = sudden_short_circuit(m, E_rms=e_air, angle_deg=case.angle_deg, t_end=case.t_end)
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    warnings: list[dict[str, Any]] = []
    assumed = []
    if case.Xd2 is None:
        assumed.append("X''d = X2 (נמדד)")
    if case.Xd1 is None:
        assumed.append(f"X'd = {XD1_OVER_XD2}·X''d")
    if case.Td01 == TD01 and case.Td02 == TD02 and case.Tq02 == TQ02:
        assumed.append(f"T'd0 = {TD01} s, T''d0 = {TD02} s, T''q0 = {TQ02} s")
    if assumed:
        warnings.append(
            {
                "code": "transient_parameters_assumed",
                "message": "פרמטרי מעבר שאינם במפרט: "
                + "; ".join(assumed)
                + ". הזרם המתמיד אינו תלוי בהם",
            }
        )
    if e_occ < 0.95 * e_air:
        warnings.append(
            {
                "code": "saturated_prefault",
                "message": f"בזרם עירור זה עקומת הריקם רוויה: מתח הריקם האמיתי {e_occ:.0f} V "
                f"מול {e_air:.0f} V על קו הפער. המודל הדינמי לינארי, ולכן זרמי ההתחלה גבוהים "
                "מעט מהמציאות; הזרם המתמיד אינו מושפע (מכונה בקצר אינה רוויה)",
            }
        )
    # the steady-state model's sustained three-phase short circuit at the same field current
    lf = spec.line_factor()
    line_k = math.sqrt(3) / lf  # line current = winding current (Y) or √3· (Δ)
    try:
        op = operating_point(
            templates.short_circuit(
                "3", case.I_f, spec.nameplate.n_sync, spec.nameplate.connection
            ),
            spec,
        )
        ik_phasor = float(op.readings["A"]["I"] or 0.0)
    except Exception as exc:  # noqa: BLE001
        ik_phasor = float("nan")
        warnings.append({"code": "no_steady_state", "message": str(exc)})
    ik_dq = r.i_sustained_rms * line_k
    settled = case.t_end > 5 * m.Td01 * m.Xd1 / m.Xd
    if settled and abs(ik_dq / ik_phasor - 1) > 0.005:
        warnings.append(
            {
                "code": "engines_disagree",
                "message": f"הזרם המתמיד {ik_dq:.4g} A שונה ממודל המצב היציב ({ik_phasor:.4g} A)",
            }
        )
    k01 = int(round(0.1 / (r.t[1] - r.t[0])))
    env_dev = None
    if k01 < len(r.t):
        env_dev = float(r.i_ac_env[k01] / ieee_envelope(m, e_air, r.t[k01 : k01 + 1])[0] - 1)
    params = [
        Param("I2_rms", "זרם תת-מעברי I''k = E/X''d", e_air / m.Xd2 * line_k, "A", "", "analytic"),
        Param("I1_rms", "זרם מעברי I'k = E/X'd", e_air / m.Xd1 * line_k, "A", "", "analytic"),
        Param("Ik_rms", "זרם קצר מתמיד (מהסימולציה)", ik_dq, "A", "", "analytic"),
        Param(
            "Ik_check",
            "זרם מתמיד מול מודל המצב היציב",
            ik_dq / ik_phasor - 1 if settled else None,
            "",
            "I_k(t_end) / I_k,phasor − 1",
            "analytic",
            undefined_reason=None if settled else "הסימולציה קצרה מדי להתייצבות",
        ),
        Param("I_peak", "שיא הזרם הרגעי (כולל רכיב DC)", r.i_peak * line_k, "A", "", "analytic"),
        Param(
            "env_check",
            "מעטפת ה-AC ב-0.1 s מול נוסחת IEEE 115",
            env_dev,
            "",
            "סטייה יחסית",
            "analytic",
            note="הנוסחה מקורבת (R ≪ X), ולכן סטייה של אחוזים בודדים צפויה",
        ),
        Param("E_air", "כא״מ לפני הקצר (קו הפער)", e_air, "V", "a·(I_f + F_res)", "analytic"),
        Param("If_peak", "קפיצת זרם העירור", float(np.max(r.if_ratio)), "×I_f", "", "analytic"),
    ]
    step = max(1, len(r.t) // 3000)
    rows = [
        {
            "t": float(r.t[k]),
            "ia": float(r.i_abc[0, k] * line_k),
            "ib": float(r.i_abc[1, k] * line_k),
            "ic": float(r.i_abc[2, k] * line_k),
            "env": None if np.isnan(r.i_ac_env[k]) else float(r.i_ac_env[k] * line_k),
            "ieee": float(ieee_envelope(m, e_air, r.t[k : k + 1])[0] * line_k),
            "if": float(r.if_ratio[k]),
        }
        for k in range(0, len(r.t), step)
    ]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "summary",
                    "title_he": "קצר תלת-פאזי פתאומי בריקם",
                    "columns": [
                        col("I_peak", "שיא זרם", "A"),
                        col("I2", "I''k", "A"),
                        col("Ik", "I_k מתמיד", "A"),
                    ],
                    "rows": [
                        {"I_peak": r.i_peak * line_k, "I2": e_air / m.Xd2 * line_k, "Ik": ik_dq}
                    ],
                },
                {
                    "id": "trace",
                    "title_he": f"קצר ב-I_f = {case.I_f:g} A, זווית הרוטור {case.angle_deg:g}°",
                    "columns": [
                        col("t", "t", "s"),
                        col("ia", "i קו L1", "A"),
                        col("ib", "i קו L2", "A"),
                        col("ic", "i קו L3", "A"),
                        col("env", "מעטפת AC (סימולציה)", "A"),
                        col("ieee", "מעטפת AC (IEEE 115)", "A"),
                        col("if", "I_f / I_f0", ""),
                    ],
                    "rows": rows,
                },
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "i",
                    "title_he": "זרמי הקו",
                    "x": "t",
                    "y": "ia",
                    "y2": "ib",
                    "y3": "ic",
                    "table": "trace",
                },
                {
                    "id": "env",
                    "title_he": "מעטפת ה-AC: סימולציה מול IEEE 115",
                    "x": "t",
                    "y": "env",
                    "y2": "ieee",
                    "table": "trace",
                },
                {"id": "if", "title_he": "זרם העירור", "x": "t", "y": "if", "table": "trace"},
            ],
        },
    )


class SynchronizeCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5, description="None = rated")
    I_f: float | None = Field(
        default=None, gt=0, le=100, description="None = no-load voltage equal to the grid"
    )
    angle_deg: float = Field(default=10.0, ge=-180, le=180, description="phase error at closing")
    df: float = Field(default=0.1, ge=-5, le=5, description="machine − grid frequency [Hz]")
    P_drive: float = Field(default=0.0, ge=-1e5, le=1e5, description="drive power after closing")
    J: float | None = Field(default=None, gt=0, le=100)
    Xd2: float | None = Field(default=None, gt=0, le=1e5)
    Xd1: float | None = Field(default=None, gt=0, le=1e5)
    Td01: float = Field(default=TD01, gt=0, le=20)
    Td02: float = Field(default=TD02, gt=0, le=1)
    Tq02: float = Field(default=TQ02, gt=0, le=1)
    t_end: float = Field(default=10.0, gt=0, le=30)


def _if_for_voltage(spec: SyncSpec, e: float) -> float | None:
    """Field current whose no-load EMF (OCC, rated speed) equals e; None if out of reach."""
    occ = spec.occ

    def g(i_f: float) -> float:
        return occ.emf(i_f + occ.F_res) - e

    hi = 100.0
    if g(0.0) >= 0:
        return 0.0
    if g(hi) < 0:
        return None
    return float(brentq(g, 0.0, hi))


def run_synchronize(spec: SyncSpec, case: SynchronizeCase) -> Outcome:
    npl, occ = spec.nameplate, spec.occ
    lf = spec.line_factor()
    line_k = math.sqrt(3) / lf
    u = case.U_line or npl.U_n
    v_w = u / lf  # winding voltage
    if case.I_f is None:
        i_f = _if_for_voltage(spec, v_w)
        if i_f is None:
            raise StudyError("invalid_input", "אין זרם עירור שמשווה את מתח הריקם למתח הרשת")
    else:
        i_f = case.I_f
    e_occ = occ.emf(i_f + occ.F_res)  # the voltmeter before closing (winding)
    e_air = occ.a * (i_f + occ.F_res)
    warnings: list[dict[str, Any]] = []
    # 1. The steady state on the grid (phasor engine). Its saturation factor at the final
    #    operating point linearises the dynamic model, so the two engines meet at the end.
    p_shaft = -case.P_drive  # motor sign: power taken from the shaft
    try:
        op = operating_point(
            templates.motor_on_grid(u, npl.f_n, spec.nameplate.connection, i_f, p_shaft), spec
        )
        i_phasor = float(op.readings["A"]["I"] or 0.0)
        p_phasor = -3 * float(op.readings["W"]["P"] or 0.0)  # into the grid
        k_sat = 1 / float(op.internals["G.mech"]["saturation"])
    except Exception as exc:  # noqa: BLE001
        i_phasor = p_phasor = float("nan")
        k_sat = e_occ / e_air if e_air > 0 else 1.0
        warnings.append(
            {
                "code": "no_steady_state",
                "message": f"אין מצב יציב על הרשת ({exc}). מקדם הרוויה נלקח מנקודת הריקם",
            }
        )
    xd2 = case.Xd2 or spec.ecm.X2
    xd1 = case.Xd1 or XD1_OVER_XD2 * xd2
    m0 = SmDynamics(
        R=spec.ecm.Ra,
        Xl=spec.ecm.Xl,
        Xd=spec.Xs_unsat,
        Xq=spec.Xs_unsat,
        Xd1=xd1,
        Xd2=xd2,
        Xq2=xd2,
        Td01=case.Td01,
        Td02=case.Td02,
        Tq02=case.Tq02,
        f=npl.f_n,
    )
    try:
        m0.check()
        m = saturate(m0, k_sat)
    except ValueError as exc:
        raise StudyError("invalid_input", f"ריאקטנסים לא עקביים: {exc}") from exc
    j = case.J or J_SYNC_ASSUMED
    try:
        r = synchronize(
            m,
            poles=npl.poles,
            J=j,
            P_fw=spec.ecm.P_fw,
            V_rms=v_w,
            E_rms=e_occ,
            E_fd_rms=k_sat * e_air,
            delta0_deg=case.angle_deg,
            df=case.df,
            P_drive=case.P_drive,
            t_end=case.t_end,
        )
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    assumed = []
    if case.J is None:
        assumed.append(f"J = {J_SYNC_ASSUMED} kg·m²")
    if case.Xd2 is None:
        assumed.append("X''d = X2 (נמדד)")
    if case.Xd1 is None:
        assumed.append(f"X'd = {XD1_OVER_XD2}·X''d")
    if case.Td01 == TD01 and case.Td02 == TD02 and case.Tq02 == TQ02:
        assumed.append(f"T'd0 = {TD01} s, T''d0 = {TD02} s, T''q0 = {TQ02} s")
    if assumed:
        warnings.append(
            {
                "code": "transient_parameters_assumed",
                "message": "פרמטרי מעבר שאינם במפרט: "
                + "; ".join(assumed)
                + ". המצב היציב הסופי אינו תלוי בהם",
            }
        )
    if abs(k_sat * e_air / e_occ - 1) > 0.05:
        warnings.append(
            {
                "code": "saturation_linearised",
                "message": f"המודל הדינמי לינארי עם מקדם רוויה קבוע {k_sat:.3f}, שנלקח מנקודת "
                f"העבודה הסופית. לפני הסגירה הכא״מ האמיתי {e_occ:.0f} V; העירור במודל מחזיק "
                f"{k_sat * e_air:.0f} V — ולכן התנודה הראשונה מקורבת, והמצב הסופי מדויק",
            }
        )
    if not r.pulled_in:
        warnings.append(
            {
                "code": "pole_slip",
                "message": "המכונה לא נכנסה לסנכרון (החלקת קטבים): הפרש הזווית או התדר גדולים "
                "מדי, או שהספק ההנעה עולה על ההספק המרבי בעירור זה",
            }
        )
    elif abs(r.delta_final - case.angle_deg) > 180:
        warnings.append(
            {
                "code": "slipped_poles",
                "message": f"המכונה החליקה {abs(r.delta_final - case.angle_deg) / 360:.1f} "
                "זוגות קטבים לפני שננעלה — מכה מכנית וזרמים גדולים",
            }
        )
    if r.pulled_in and not r.settled:
        warnings.append(
            {
                "code": "not_settled",
                "message": f"התנודה סביב הסנכרון עדיין לא דעכה אחרי {case.t_end:g} s; "
                "ההשוואה למודל המצב היציב לא בוצעה",
            }
        )
    i_final_line = r.i_rms_final * line_k
    check_ok = r.settled and math.isfinite(i_phasor)
    if check_ok and (
        abs(i_final_line - i_phasor) > 0.01 * max(i_phasor, 0.02 * spec.nameplate.I_n)
        or abs(r.p_final - p_phasor) > 0.01 * max(abs(p_phasor), 0.01 * npl.P_n)
    ):
        warnings.append(
            {
                "code": "engines_disagree",
                "message": f"המצב הסופי ({i_final_line:.4g} A, {r.p_final:.4g} W) שונה ממודל "
                f"המצב היציב ({i_phasor:.4g} A, {p_phasor:.4g} W)",
            }
        )
    # the first-swing estimate: the AC sub-transient current the voltage difference drives
    du = abs(
        complex(
            e_occ * math.cos(math.radians(case.angle_deg)),
            e_occ * math.sin(math.radians(case.angle_deg)),
        )
        - v_w
    )
    i2_est = du / xd2 * line_k
    # line currents
    if lf == 1.0:  # delta: i_L1 = i_A − i_C, …
        iw = r.i_abc
        il = np.vstack([iw[0] - iw[2], iw[1] - iw[0], iw[2] - iw[1]])
    else:
        il = r.i_abc
    i_peak = float(np.max(np.abs(il)))
    i_rated_pk = math.sqrt(2) * npl.I_n
    undefined = (
        None if check_ok else ("אין מצב יציב" if not math.isfinite(i_phasor) else "התנודה לא דעכה")
    )
    params = [
        Param("I_f", "זרם עירור", i_f, "A", "", "analytic"),
        Param("E_noload", "מתח ריקם (קווי) לפני הסגירה", e_occ * lf, "V", "", "analytic"),
        Param("dU", "הפרש המתחים בסגירה (פאזה)", du, "V", "|E∠Δθ − U|", "analytic"),
        Param(
            "I2_est",
            "הערכת זרם הסגירה (AC תת-מעברי)",
            i2_est,
            "A",
            "|ΔU| / X''d",
            "analytic",
            note="ללא רכיב DC: השיא האמיתי בין √2 ל-2√2 פעמים הערך הזה",
        ),
        Param("I_peak", "שיא זרם הקו אחרי הסגירה", i_peak, "A", "max|i_L(t)|", "analytic"),
        Param("I_peak_pu", "שיא הזרם ביחס לשיא הנומינלי", i_peak / i_rated_pk, "", "", "analytic"),
        Param("I_final", "זרם קו סופי", i_final_line, "A", "", "analytic"),
        Param("P_final", "הספק סופי לרשת (גנרטור +)", r.p_final, "W", "", "analytic"),
        Param("delta_final", "זווית העומס הסופית", r.delta_final, "°", "", "analytic"),
        Param(
            "I_check",
            "זרם סופי מול מודל המצב היציב",
            i_final_line / i_phasor - 1 if check_ok and i_phasor else None,
            "",
            "I(t_end) / I_phasor − 1",
            "analytic",
            undefined_reason=undefined,
        ),
        Param(
            "P_check",
            "הספק סופי מול מודל המצב היציב",
            r.p_final - p_phasor if check_ok else None,
            "W",
            "P(t_end) − P_phasor",
            "analytic",
            undefined_reason=undefined,
        ),
        Param(
            "k_sat", "מקדם הרוויה (מנקודת העבודה)", k_sat, "", "E / (a·F) בנקודה הסופית", "analytic"
        ),
    ]
    dt = float(r.t[1] - r.t[0])
    n_fast = min(len(r.t), int(round(0.4 / dt)) + 1)  # the first 0.4 s at full resolution
    fast = [
        {
            "t": float(r.t[k]),
            "ia": float(il[0, k]),
            "ib": float(il[1, k]),
            "ic": float(il[2, k]),
        }
        for k in range(n_fast)
    ]
    step = max(1, len(r.t) // 2000)
    slow = [
        {
            "t": float(r.t[k]),
            "p": float(r.p_el[k]),
            "delta": float(r.delta_deg[k]),
            "n": float(r.n[k]),
            "i": float(r.i_rms[k] * line_k),
        }
        for k in range(0, len(r.t), step)
    ]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "summary",
                    "title_he": "סנכרון לרשת",
                    "columns": [
                        col("I_peak", "שיא זרם", "A"),
                        col("I_final", "זרם סופי", "A"),
                        col("P_final", "הספק סופי", "W"),
                        col("delta", "δ סופי", "°"),
                    ],
                    "rows": [
                        {
                            "I_peak": i_peak,
                            "I_final": i_final_line,
                            "P_final": r.p_final,
                            "delta": r.delta_final,
                        }
                    ],
                },
                {
                    "id": "swing",
                    "title_he": f"סגירה ב-{u:.0f} V, I_f = {i_f:.3g} A, Δθ = {case.angle_deg:g}°, "
                    f"Δf = {case.df:g} Hz",
                    "columns": [
                        col("t", "t", "s"),
                        col("p", "P לרשת", "W"),
                        col("delta", "δ", "°"),
                        col("n", "n", "rpm"),
                        col("i", "זרם קו (RMS רגעי)", "A"),
                    ],
                    "rows": slow,
                },
                {
                    "id": "trace",
                    "title_he": "זרמי הקו ב-0.4 s הראשונות",
                    "columns": [
                        col("t", "t", "s"),
                        col("ia", "i קו L1", "A"),
                        col("ib", "i קו L2", "A"),
                        col("ic", "i קו L3", "A"),
                    ],
                    "rows": fast,
                },
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "i",
                    "title_he": "זרמי הקו",
                    "x": "t",
                    "y": "ia",
                    "y2": "ib",
                    "y3": "ic",
                    "table": "trace",
                },
                {
                    "id": "delta",
                    "title_he": "זווית העומס",
                    "x": "t",
                    "y": "delta",
                    "table": "swing",
                },
                {"id": "p", "title_he": "הספק לרשת", "x": "t", "y": "p", "table": "swing"},
                {"id": "irms", "title_he": "זרם הקו (RMS)", "x": "t", "y": "i", "table": "swing"},
                {"id": "n", "title_he": "מהירות", "x": "t", "y": "n", "table": "swing"},
            ],
        },
    )
