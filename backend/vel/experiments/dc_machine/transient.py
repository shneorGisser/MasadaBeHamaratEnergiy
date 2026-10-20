"""Studies: shunt-generator voltage build-up (experiment 6) and shunt-motor start through an
armature starter (experiment 5), in the time domain (vel.engine.transient.dcmachine).

Each study compares its final state with the steady-state DC solver for the same circuit —
the two engines share the fitted machine model, so they must agree."""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine.simulate import operating_point
from vel.engine.transient.dcmachine import DcResult, shunt_buildup, shunt_motor_start
from vel.experiments.common import Outcome, Param, StudyError, col
from vel.experiments.dc_machine import templates
from vel.experiments.dc_machine.spec import DCSpec

# not on the nameplate: assumed for a 0.37 kW, 220 V machine
L_A_ASSUMED = 0.08  # H: armature (τ_a = L_a/R_a ≈ 6 ms)
L_F0_ASSUMED = 92.0  # H: unsaturated shunt field (τ_f = L_f0/R_f ≈ 0.25 s)
J_ASSUMED = 0.003  # kg·m²: armature + coupling + brake
R_OPEN = 1e9


class BuildupCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: float = Field(default=2800.0, gt=0, le=1e4)
    R_rheo: float = Field(default=0.0, ge=0, le=1e5)
    L_a: float = Field(default=L_A_ASSUMED, gt=0, le=100)
    L_f0: float = Field(default=L_F0_ASSUMED, gt=0, le=1e4)
    t_end: float = Field(default=5.0, gt=0, le=60)


class StarterStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    R: float = Field(ge=0, le=1e4)
    t: float = Field(gt=0, le=60)


class MotorStartCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U: float = Field(default=174.0, gt=0, le=1000)
    R_rheo: float = Field(default=0.0, ge=0, le=1e5)
    points: list[StarterStep] = Field(min_length=1, max_length=10)
    M_brake: float = Field(default=0.0, ge=0, le=100)
    field_first: bool = True
    J: float = Field(default=J_ASSUMED, gt=0, le=1e3)
    L_a: float = Field(default=L_A_ASSUMED, gt=0, le=100)
    L_f0: float = Field(default=L_F0_ASSUMED, gt=0, le=1e4)

    @field_validator("points")
    @classmethod
    def _increasing(cls, v: list[StarterStep]) -> list[StarterStep]:
        if any(b.t <= a.t for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("step end times must increase")
        return v


def _assumed(case: BaseModel, keys: dict[str, float]) -> list[dict[str, Any]]:
    names = {"L_a": "השראות העוגן", "L_f0": "השראות העירור", "J": "מומנט ההתמד"}
    used = [f"{names[k]} {getattr(case, k):g}" for k, v in keys.items() if getattr(case, k) == v]
    if not used:
        return []
    return [
        {
            "code": "transient_parameters_assumed",
            "message": "ערכים מוערכים (לא בשלט): " + ", ".join(used) + ". הם קובעים את קצב "
            "השינוי, לא את המצב הסופי",
        }
    ]


def _trace(r: DcResult, title: str) -> dict[str, Any]:
    step = max(1, len(r.t) // 3000)
    rows = [
        {
            "t": float(r.t[k]),
            "U": float(r.u[k]),
            "Ia": float(r.i_a[k]),
            "If": float(r.i_f[k]),
            "n": float(r.n[k]),
            "M_em": float(r.M_em[k]),
        }
        for k in range(0, len(r.t), step)
    ]
    return {
        "id": "trace",
        "title_he": title,
        "columns": [
            col("t", "t", "s"),
            col("U", "U", "V"),
            col("Ia", "Ia", "A"),
            col("If", "If", "A"),
            col("n", "n", "rpm"),
            col("M_em", "M אלקטרומגנטי", "N·m"),
        ],
        "rows": rows,
    }


def _settled(y: Any, rel: float = 1e-3) -> bool:
    tail = np.asarray(y[-max(2, len(y) // 50) :])
    scale = max(abs(float(tail[-1])), 1e-9)
    return float(np.ptp(tail)) <= rel * scale


def run_buildup(spec: DCSpec, case: BuildupCase) -> Outcome:
    try:
        r = shunt_buildup(
            spec, n=case.n, r_rheo=case.R_rheo, L_a=case.L_a, L_f0=case.L_f0, t_end=case.t_end
        )
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    warnings = _assumed(case, {"L_a": L_A_ASSUMED, "L_f0": L_F0_ASSUMED})
    e = spec.ecm
    # linear (air-gap) build-up condition: k·a > R_a + R_f + R_rheo
    r_crit = case.n / spec.occ.n_ref * spec.occ.a - e.R_a - e.R_f
    u_fin = float(r.u[-1])
    # the steady-state solver's criterion: the resultant MMF stays below twice the remanence
    f_fin = float(r.i_f[-1]) * (1 - e.k_ar) + spec.occ.F_res
    built = f_fin >= 2 * spec.occ.F_res
    if not built:
        warnings.append(
            {
                "code": "no_buildup",
                "message": f"אין בנייה: R העירור הכולל {e.R_f + case.R_rheo:.0f} Ω מעל הקריטי "
                f"(ריאוסטט ≤ {r_crit:.0f} Ω במהירות זו). המתח נשאר ליד מתח השטף השיורי",
            }
        )
    if not _settled(r.u):
        warnings.append(
            {"code": "not_settled", "message": "המתח עדיין משתנה — האריכו את זמן הסימולציה"}
        )
    op = operating_point(
        templates.generator(case.n, case.R_rheo, R_OPEN, excitation="shunt", closed=False),
        spec,
        dc=True,
    )
    u_ref = float(op.readings["U1"]["U"] or 0.0)
    above = np.nonzero(r.u >= 0.9 * u_fin)[0]
    t90 = float(r.t[above[0]]) if built and above.size else None
    params = [
        Param("U_final", "מתח סופי", u_fin, "V", "", "analytic"),
        Param("U_res", "מתח שטף שיורי (t = 0)", float(r.u[0]), "V", "", "analytic"),
        Param(
            "t_90",
            "זמן הבנייה עד 90 %",
            t90,
            "s",
            "",
            "analytic",
            undefined_reason=None if t90 is not None else "המכונה לא נבנתה",
        ),
        Param(
            "R_crit",
            "ריאוסטט עירור קריטי (בקירוב הקו הלינארי)",
            r_crit,
            "Ω",
            "(n/n_ref)·a − R_a − R_f",
            "analytic",
            note="בנייה רק כשהתנגדות מעגל העירור קטנה ממנו",
        ),
        Param(
            "dU_check",
            "סטייה מהפותר במצב יציב",
            u_fin - u_ref,
            "V",
            "U(t_end) − U_DC-solver",
            "analytic",
            note="בדיקת עקביות בין שני המנועים",
        ),
    ]
    if _settled(r.u) and abs(u_fin - u_ref) > 0.01 * max(u_ref, 1.0):
        warnings.append(
            {
                "code": "engines_disagree",
                "message": f"המתח הסופי שונה מהפותר במצב יציב ({u_fin:.1f} מול {u_ref:.1f} V)",
            }
        )
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "summary",
                    "title_he": "בניית מתח במחולל מקבילי",
                    "columns": [
                        col("U_res", "מתח שיורי", "V"),
                        col("U_final", "מתח סופי", "V"),
                        col("t_90", "זמן בנייה (90 %)", "s"),
                    ],
                    "rows": [{"U_res": float(r.u[0]), "U_final": u_fin, "t_90": t90}],
                },
                _trace(r, f"בנייה ב-{case.n:g} סל״ד, ריאוסטט עירור {case.R_rheo:g} Ω, ללא עומס"),
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {"id": "u", "title_he": "מתח ההדקים", "x": "t", "y": "U", "table": "trace"},
                {"id": "if", "title_he": "זרם העירור", "x": "t", "y": "If", "table": "trace"},
            ],
            "solver": r.solver,
        },
    )


def default_motor_steps(spec: DCSpec, u: float) -> list[dict[str, float]]:
    """A starter that limits the inrush to ≈ 2·I_n, cut out in two steps."""
    r1 = max(0.0, u / (2 * spec.nameplate.I_n) - spec.ecm.R_a)
    return [{"R": round(r1, 1), "t": 0.5}, {"R": round(r1 / 3, 1), "t": 1.0}, {"R": 0.0, "t": 2.0}]


def run_motor_start(spec: DCSpec, case: MotorStartCase) -> Outcome:
    steps = [(p.R, p.t) for p in case.points]
    try:
        r = shunt_motor_start(
            spec,
            U=case.U,
            r_rheo=case.R_rheo,
            steps=steps,
            J=case.J,
            L_a=case.L_a,
            L_f0=case.L_f0,
            M_brake=case.M_brake,
            field_first=case.field_first,
        )
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    warnings = _assumed(case, {"L_a": L_A_ASSUMED, "L_f0": L_F0_ASSUMED, "J": J_ASSUMED})
    i_peak = float(np.max(np.abs(r.i_a)))
    i_n = spec.nameplate.I_n
    if i_peak > 2.5 * i_n:
        warnings.append(
            {
                "code": "inrush_high",
                "message": f"שיא זרם העוגן {i_peak:.2f} A = {i_peak / i_n:.1f}·In — מתנע "
                "גדול יותר או מדרגות איטיות יותר מגינים על המברשות והקומוטטור",
            }
        )
    if not _settled(r.n):
        warnings.append(
            {"code": "not_settled", "message": "המהירות לא התייצבה — האריכו את המדרגה האחרונה"}
        )
    circ = templates.motor(case.U, case.R_rheo, r_x=case.points[-1].R, m_load=case.M_brake)
    try:
        op = operating_point(circ, spec, dc=True)
        n_ref = float(op.readings["M"]["n"] or 0.0)
    except Exception as exc:  # noqa: BLE001
        n_ref = float("nan")
        warnings.append({"code": "no_steady_state", "message": f"אין נקודת עבודה יציבה: {exc}"})
    n_fin = float(r.n[-1])
    above = np.nonzero(r.n >= 0.95 * n_fin)[0]
    t95 = float(r.t[above[0]]) if n_fin > 1 and above.size else None
    params = [
        Param("Ia_peak", "שיא זרם העוגן", i_peak, "A", "max|Ia(t)|", "analytic"),
        Param("t_95", "זמן עד 95 % מהמהירות הסופית", t95, "s", "", "analytic"),
        Param("n_final", "מהירות סופית", n_fin, "rpm", "", "analytic"),
        Param(
            "dn_check",
            "סטייה מהפותר במצב יציב (מהירות)",
            n_fin - n_ref,
            "rpm",
            "n(t_end) − n_DC-solver",
            "analytic",
            note="בדיקת עקביות בין שני המנועים",
        ),
    ]
    if _settled(r.n) and abs(n_fin - n_ref) > 2:
        warnings.append(
            {
                "code": "engines_disagree",
                "message": f"המהירות הסופית שונה מהפותר במצב יציב ({n_fin:.0f} מול {n_ref:.0f})",
            }
        )
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "summary",
                    "title_he": "התנעת מנוע מקבילי",
                    "columns": [
                        col("Ia_peak", "שיא זרם עוגן", "A"),
                        col("t_95", "זמן התנעה (95 %)", "s"),
                        col("n_final", "מהירות סופית", "rpm"),
                    ],
                    "rows": [{"Ia_peak": i_peak, "t_95": t95, "n_final": n_fin}],
                },
                {
                    "id": "events",
                    "title_he": "אירועי מיתוג",
                    "columns": [col("t", "t", "s"), col("label", "מצב חדש", "")],
                    "rows": r.events,
                },
                _trace(r, f"התנעה ב-{case.U:g} V דרך מתנע עוגן, בלם {case.M_brake:g} N·m"),
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {"id": "ia", "title_he": "זרם העוגן", "x": "t", "y": "Ia", "table": "trace"},
                {"id": "n", "title_he": "מהירות", "x": "t", "y": "n", "table": "trace"},
                {"id": "if", "title_he": "זרם העירור", "x": "t", "y": "If", "table": "trace"},
            ],
            "solver": r.solver,
        },
    )
