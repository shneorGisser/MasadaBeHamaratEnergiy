"""Result layout and checks shared by the machine-start studies (time-domain engine).

Every start study reports the same things: a one-row summary (the quantities a student can
measure: peak current with a scope or clamp meter, starting time, final speed), the folded
time series behind the curves, and the self-consistency check against the steady-state phasor
solver for the same machine and brake. Switching events are listed so the curves can be read.
"""

from __future__ import annotations

import math
from typing import Any

from vel.engine.transient.induction import StartResult
from vel.experiments.common import Outcome, Param, col


def start_outcome(
    r: StartResult,
    *,
    title: str,
    t_end: float,
    J: float,
    J_assumed: float,
    ref: dict[str, float],
    ref_warnings: list[dict[str, Any]],
    extra_params: list[Param] | None = None,
    extra_warnings: list[dict[str, Any]] | None = None,
) -> Outcome:
    """`ref` holds the phasor solver's steady state: n_no_fe / I_no_fe (same machine without
    R_Fe — the dq model has no iron loss) and n_full / I_full (with it)."""
    warnings: list[dict[str, Any]] = list(ref_warnings) + list(extra_warnings or [])
    if J_assumed == J:
        warnings.append(
            {
                "code": "inertia_assumed",
                "message": f"מומנט ההתמד J = {J_assumed} kg·m² מוערך (רוטור + צימוד + בלם); "
                "הוא קובע את זמן ההתנעה, לא את זרם ההתנעה",
            }
        )
    settled = abs(r.n[-1] - r.n[max(0, len(r.n) - 41)]) < 0.5  # < 0.5 rpm over the last 10 ms
    if not settled:
        warnings.append(
            {
                "code": "not_settled",
                "message": f"המהירות לא התייצבה תוך {t_end:g} s — האריכו את זמן הסימולציה",
            }
        )
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
        *(extra_params or []),
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
                    "message": f"המצב הסופי שונה מהפותר במצב יציב (Δn = {dn:.2g} rpm, "
                    f"ΔI = {di:.2%})",
                }
            )
    if ref.get("I_full") and ref.get("I_no_fe"):
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
    rows = [
        {"t": float(t), "i_L1": float(i), "I_rms": float(e), "n": float(n), "M_em": float(m)}
        for t, i, e, n, m in zip(r.t, r.i_line, r.i_line_rms, r.n, r.M_em, strict=True)
    ]
    tables: list[dict[str, Any]] = [
        {
            "id": "summary",
            "title_he": "סיכום ההתנעה",
            "columns": [
                col("I_peak", "שיא זרם רגעי", "A"),
                col("I_start", "זרם התנעה RMS", "A"),
                col("t_95", "זמן התנעה (95 %)", "s"),
                col("n_final", "מהירות סופית", "rpm"),
            ],
            "rows": [
                {"I_peak": r.i_peak, "I_start": i_start, "t_95": r.t_95, "n_final": r.n_final}
            ],
        },
        {
            "id": "trace",
            "title_he": title,
            "columns": [
                col("t", "t", "s"),
                col("i_L1", "i קו L1 (רגעי)", "A"),
                col("I_rms", "I קו (RMS)", "A"),
                col("n", "n", "rpm"),
                col("M_em", "M אלקטרומגנטי", "N·m"),
            ],
            "rows": rows,
        },
    ]
    if r.events:
        tables.insert(
            1,
            {
                "id": "events",
                "title_he": "אירועי מיתוג",
                "columns": [col("t", "t", "s"), col("label", "מצב חדש", "")],
                "rows": r.events,
            },
        )
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": tables,
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "i",
                    "title_he": "זרם הקו",
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
