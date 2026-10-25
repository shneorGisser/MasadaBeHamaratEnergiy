"""Study: energising the transformer (no load) in the time domain — the inrush current.

The steady-state no-load study gives the RMS magnetising current. Switching the transformer
on shows what that number hides: depending on the instant of switching and on the flux left
in the core, a limb may be driven into deep saturation and draw tens of times its no-load
current for a few cycles, decaying with the circuit's R/L.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from vel.engine.simulate import operating_point
from vel.engine.transient.transformer import energise
from vel.experiments.common import Outcome, Param, StudyError, col
from vel.experiments.transformer3ph import templates
from vel.experiments.transformer3ph.spec import TransformerSpec


class InrushCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5)
    angle_deg: float = Field(default=0.0, ge=-360, le=360)
    remanence: float = Field(default=0.6, ge=-0.95, le=0.95, description="× rated peak flux")
    t_end: float = Field(default=0.5, gt=0, le=5.0)
    neutral: bool = False


def run_inrush(spec: TransformerSpec, case: InrushCase) -> Outcome:
    npl = spec.nameplate
    u = case.U_line or npl.U1n
    try:
        r = energise(
            spec,
            U_line=u,
            angle_deg=case.angle_deg,
            remanence=case.remanence,
            t_end=case.t_end,
            neutral=case.neutral,
        )
        ref = energise(
            spec,
            U_line=u,
            angle_deg=0.0,
            remanence=0.0,
            t_end=0.1,
            steady_start=True,
            neutral=case.neutral,
        )
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    warnings: list[dict[str, Any]] = []
    i_rated_pk = float(np.sqrt(2) * spec.I1n_line)
    i0_pk = ref.i0_peak_steady
    if r.t_decay is None:
        warnings.append(
            {
                "code": "not_decayed",
                "message": f"זרם הכניסה לא דעך לפחות מפי 2 מזרם הריקם תוך {case.t_end:g} s. "
                "במודל אין הפסדי היסטרזיס, ולכן הדעיכה איטית מעט מהמציאות",
            }
        )
    if case.remanence != 0:
        warnings.append(
            {
                "code": "remanence_assumed",
                "message": f"השטף השיורי ({case.remanence:+.2f}·Φ_n בפאזה A, הפוך בפאזה B) "
                "מוערך — במעבדה הוא תלוי ברגע הניתוק הקודם ואינו ידוע",
            }
        )
    # second-harmonic content of the worst phase over the first two cycles: the signature a
    # differential relay uses to tell inrush from an internal fault (blocking above ≈ 15 %)
    f_n = spec.nameplate.f_n
    n2 = int(round(2 / f_n / (r.t[1] - r.t[0])))
    h2 = None
    if n2 + 1 <= len(r.t):
        seg = r.i_line[r.i_peak_phase, : n2 + 1]
        tt = r.t[: n2 + 1] - r.t[0]

        def harm(k: int) -> float:
            w = 2 * np.pi * f_n * k
            c = np.trapezoid(seg * np.cos(w * tt), tt)
            sn = np.trapezoid(seg * np.sin(w * tt), tt)
            return float(np.hypot(c, sn))

        h1 = harm(1)
        h2 = harm(2) / h1 if h1 > 0 else None
    params = [
        Param("I_peak", "שיא זרם הכניסה", r.i_peak, "A", "max|i_L(t)|", "analytic"),
        Param(
            "H2_ratio",
            "הרמוניה שנייה בשני המחזורים הראשונים (בפאזה עם השיא)",
            h2,
            "",
            "I₂ / I₁",
            "analytic",
            note="ממסר דיפרנציאלי חוסם ניתוק מעל ≈ 15 % — כך הוא מבחין בין זרם כניסה לקצר פנימי",
            undefined_reason=None if h2 is not None else "הסימולציה קצרה משני מחזורים",
        ),
        Param(
            "I_peak_pu_rated",
            "שיא זרם הכניסה ביחס לשיא הזרם הנומינלי",
            r.i_peak / i_rated_pk,
            "",
            "I_peak / (√2·I1n)",
            "analytic",
        ),
        Param(
            "I_peak_pu_noload",
            "שיא זרם הכניסה ביחס לשיא זרם הריקם",
            r.i_peak / i0_pk,
            "",
            "",
            "analytic",
        ),
        Param(
            "t_decay",
            "זמן עד שהשיאים יורדים מתחת לפי 2 מזרם הריקם",
            r.t_decay,
            "s",
            "",
            "analytic",
            undefined_reason=None if r.t_decay is not None else "לא דעך בזמן הסימולציה",
        ),
        Param(
            "c_inst",
            "מקדם הרוויה של העקומה הרגעית",
            r.c_inst,
            "",
            "מכויל כך שהרכיב היסודי בשטף הנקוב = מודל המצב היציב",
            "analytic",
        ),
    ]
    # the two engines at the rated point: fundamental of the steady no-load current
    try:
        op = operating_point(templates.no_load(u, npl.f_n), spec)
        i0_phasor = float(op.readings["A"]["I"] or 0.0)
        params.append(
            Param(
                "I0_check",
                "זרם ריקם (יסודי) מול מודל המצב היציב",
                ref.i0_rms_fund / i0_phasor - 1 if i0_phasor else None,
                "",
                "I0,fund(t) / I0,phasor − 1",
                "analytic",
                note="כוכב ללא אפס: זרמי ההרמוניה השלישית אינם יכולים לזרום, השטף אינו "
                "סינוסי והרכיב היסודי שונה במעט ממודל הפאזורים (שמניח שטף סינוסי)"
                if npl.primary == "Y" and not case.neutral
                else "אמור להתאים בקירוב טוב",
            )
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append({"code": "no_steady_state", "message": f"אין מצב יציב לריקם: {exc}"})
    step = max(1, len(r.t) // 3000)
    rows = [
        {
            "t": float(r.t[k]),
            "i1": float(r.i_line[0, k]),
            "i2": float(r.i_line[1, k]),
            "i3": float(r.i_line[2, k]),
            "l1": float(r.lam_pu[0, k]),
            "l2": float(r.lam_pu[1, k]),
            "l3": float(r.lam_pu[2, k]),
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
                    "title_he": "זרם הכניסה בחיבור השנאי לרשת",
                    "columns": [
                        col("I_peak", "שיא זרם הכניסה", "A"),
                        col("I0_peak", "שיא זרם הריקם (מצב יציב)", "A"),
                        col("t_decay", "זמן דעיכה", "s"),
                    ],
                    "rows": [{"I_peak": r.i_peak, "I0_peak": i0_pk, "t_decay": r.t_decay}],
                },
                {
                    "id": "trace",
                    "title_he": f"חיבור ב-{u:.0f} V, זווית {case.angle_deg:g}°, שטף שיורי "
                    f"{case.remanence:+.2f}·Φ_n",
                    "columns": [
                        col("t", "t", "s"),
                        col("i1", "i L1", "A"),
                        col("i2", "i L2", "A"),
                        col("i3", "i L3", "A"),
                        col("l1", "Φ A / Φ_n", ""),
                        col("l2", "Φ B / Φ_n", ""),
                        col("l3", "Φ C / Φ_n", ""),
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
                    "y": "i1",
                    "y2": "i2",
                    "y3": "i3",
                    "table": "trace",
                },
                {
                    "id": "flux",
                    "title_he": "השטף בעמודים (יחסית לנקוב)",
                    "x": "t",
                    "y": "l1",
                    "y2": "l2",
                    "y3": "l3",
                    "table": "trace",
                },
            ],
        },
    )
