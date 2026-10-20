"""Study: direct-on-line start of the induction motor in the time domain.

The transient model (vel.engine.transient.induction) and the steady-state phasor model share the
spec. The study reports how far the transient's final state is from the steady-state solver's
answer for the same machine and brake — the self-consistency check of the two engines — and
how much the neglected iron loss moves that answer.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vel.engine.simulate import operating_point
from vel.engine.transient.induction import dol_start
from vel.experiments.common import Outcome, Param, StudyError, col
from vel.experiments.induction_motor import templates
from vel.experiments.induction_motor.spec import MotorSpec

# rotor + coupling + brake [kg·m²]: not on any nameplate. A 0.37 kW 4-pole rotor is ≈ 1e-3;
# the powder brake and coupling are assumed to double it.
J_ASSUMED = 0.003


class DolStartCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5)
    J: float = Field(default=J_ASSUMED, gt=0, le=1e4)
    M_brake: float = Field(default=0.0, ge=0, le=1e4)
    t_end: float = Field(default=1.0, gt=0, le=10.0)
    angle_deg: float = Field(default=0.0, ge=-360, le=360)


def run_dol_start(spec: MotorSpec, case: DolStartCase) -> Outcome:
    npl = spec.nameplate
    u = case.U_line or npl.U_n
    conn = npl.connection
    warnings: list[dict[str, Any]] = []
    try:
        r = dol_start(
            spec,
            U_line=u,
            f=npl.f_n,
            connection=conn,
            J=case.J,
            M_brake=case.M_brake,
            t_end=case.t_end,
            angle_deg=case.angle_deg,
        )
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    if case.J == J_ASSUMED:
        warnings.append(
            {
                "code": "inertia_assumed",
                "message": f"מומנט ההתמד J = {J_ASSUMED} kg·m² "
                "מוערך (רוטור + צימוד + בלם); הוא קובע את זמן ההתנעה, לא את זרם ההתנעה",
            }
        )
    # the steady state of the same machine from the phasor solver, with and without iron loss
    no_fe = spec.model_copy(update={"ecm": spec.ecm.model_copy(update={"R_fe": 1e9})})
    circ = templates.load_test(u, npl.f_n, conn, m_load=case.M_brake)
    ref: dict[str, float] = {}
    for key, sp in (("no_fe", no_fe), ("full", spec)):
        try:
            op = operating_point(circ, sp)
            ref[f"n_{key}"] = float(op.readings["M"]["n"] or 0.0)
            ref[f"I_{key}"] = float(op.readings["A"]["I"] or 0.0)
        except Exception as exc:  # noqa: BLE001 — a stalled steady state is a finding, not a crash
            warnings.append({"code": "no_steady_state", "message": f"אין נקודת עבודה יציבה: {exc}"})
    settled = abs(r.n[-1] - r.n[max(0, len(r.n) - 41)]) < 0.5  # < 0.5 rpm over the last 10 ms
    if not settled:
        warnings.append(
            {
                "code": "not_settled",
                "message": f"המהירות לא התייצבה תוך {case.t_end:g} s — האריכו את זמן הסימולציה",
            }
        )
    rows = [
        {"t": float(t), "i_L1": float(i), "I_rms": float(e), "n": float(n), "M_em": float(m)}
        for t, i, e, n, m in zip(r.t, r.i_line, r.i_line_rms, r.n, r.M_em, strict=True)
    ]
    i_start = float(max(r.i_line_rms[: max(1, len(r.t) // 20)]))
    params = [
        Param(
            "I_peak",
            "שיא זרם הקו הרגעי",
            r.i_peak,
            "A",
            "max|i_L1(t)|",
            "analytic",
            note="כולל רכיב DC שתלוי ברגע החיבור (זווית החיבור)",
        ),
        Param("I_start", "זרם התנעה (RMS, בתחילת ההתנעה)", i_start, "A", "|i_s|/√2", "analytic"),
        Param(
            "t_95",
            "זמן עד 95 % מהמהירות הסופית",
            r.t_95,
            "s",
            "",
            "analytic",
            undefined_reason=None if r.t_95 is not None else "המנוע לא הסתובב",
        ),
        Param("n_final", "מהירות סופית", r.n_final, "rpm", "", "analytic"),
        Param("I_final", "זרם קו סופי (RMS)", r.i_line_rms_final, "A", "", "analytic"),
    ]
    if "n_no_fe" in ref and settled:
        dn = r.n_final - ref["n_no_fe"]
        di = r.i_line_rms_final / ref["I_no_fe"] - 1 if ref["I_no_fe"] else math.nan
        params.append(
            Param(
                "dn_check",
                "סטייה מהפותר במצב יציב (מהירות)",
                dn,
                "rpm",
                "n(t_end) − n_MNA",
                "analytic",
                note="אותה מכונה ללא R_Fe; בדיקת עקביות בין שני המנועים",
            )
        )
        if abs(dn) > 2 or abs(di) > 0.005:
            warnings.append(
                {
                    "code": "engines_disagree",
                    "message": f"המצב הסופי שונה מהפותר במצב "
                    f"יציב (Δn = {dn:.2g} rpm, ΔI = {di:.2%})",
                }
            )
    if "I_full" in ref and ref.get("I_no_fe"):
        params.append(
            Param(
                "iron_effect",
                "השפעת הפסדי הברזל (לא במודל הדינמי) על הזרם",
                ref["I_full"] / ref["I_no_fe"] - 1,
                "",
                "I(R_Fe)/I(∞) − 1",
                "analytic",
            )
        )
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "summary",
                    "title_he": "התנעה ישירה — סיכום",
                    "columns": [
                        col("I_peak", "שיא זרם רגעי", "A"),
                        col("I_start", "זרם התנעה RMS", "A"),
                        col("t_95", "זמן התנעה (95 %)", "s"),
                        col("n_final", "מהירות סופית", "rpm"),
                    ],
                    "rows": [
                        {
                            "I_peak": r.i_peak,
                            "I_start": i_start,
                            "t_95": r.t_95,
                            "n_final": r.n_final,
                        }
                    ],
                },
                {
                    "id": "trace",
                    "title_he": f"התנעה ישירה ב-{u:g} V ({conn}), J = {case.J:g} kg·m², "
                    f"בלם {case.M_brake:g} N·m",
                    "columns": [
                        col("t", "t", "s"),
                        col("i_L1", "i קו L1 (רגעי)", "A"),
                        col("I_rms", "I קו (RMS)", "A"),
                        col("n", "n", "rpm"),
                        col("M_em", "M אלקטרומגנטי", "N·m"),
                    ],
                    "rows": rows,
                },
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "i",
                    "title_he": "זרם הקו בהתנעה",
                    "x": "t",
                    "y": "i_L1",
                    "y2": "I_rms",
                    "table": "trace",
                },
                {"id": "n", "title_he": "מהירות", "x": "t", "y": "n", "table": "trace"},
                {
                    "id": "M",
                    "title_he": "מומנט אלקטרומגנטי",
                    "x": "t",
                    "y": "M_em",
                    "table": "trace",
                },
            ],
            "solver": r.solver,
        },
    )
