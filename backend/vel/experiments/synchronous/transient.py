"""Study: sudden three-phase short circuit of the synchronous generator at no load (time domain).

The steady-state short-circuit study gives the sustained current E/Xs. The sudden short circuit
shows the sub-transient and transient currents before it, and the DC offset that depends on
the rotor position at the fault. The run is checked twice: the sustained current against the
steady-state model, and the AC envelope against the IEEE Std 115 formula."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from vel.engine.simulate import operating_point
from vel.engine.transient.synchronous import SmDynamics, ieee_envelope, sudden_short_circuit
from vel.experiments.common import Outcome, Param, StudyError, col
from vel.experiments.synchronous import templates
from vel.experiments.synchronous.spec import SyncSpec

# not in the spec: assumed for a small laboratory machine
XD1_OVER_XD2 = 1.5
TD01 = 0.3  # s
TD02 = 0.02  # s
TQ02 = 0.03  # s


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
