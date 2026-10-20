"""Experiment 8 (testing an electrical installation) as a registered module."""

from __future__ import annotations

import math
from typing import Any

from vel.experiments.common import SAFETY, InputError, MCol, MeasureDef, Step, study_steps
from vel.experiments.installation import physics as ph
from vel.experiments.installation import studies
from vel.experiments.installation.spec import K_INST, PRESETS, InstallSpec, lab_2025
from vel.experiments.registry import ExperimentModule

Rows = list[dict[str, Any]]

MEASURE_DEFS: dict[str, MeasureDef] = {
    "grid_voltages": MeasureDef(
        "grid_voltages",
        (MCol("U", "U", "V"),),
        "fixed",
        "row",
        row_labels=tuple(f"U {p}" for p in (*ph.LN_PAIRS, *ph.LL_PAIRS)),
    ),
    "fault_loop": MeasureDef(
        "fault_loop", (MCol("Z", "Z", "Ω"),), "fixed", "row", row_labels=ph.LOOPS
    ),
    "mcb_trip": MeasureDef(
        "mcb_trip",
        (
            MCol("In", "סוג מא״ז In", "A"),
            MCol("I", "זרם הקפיצה", "A"),
            MCol("t", "זמן עד קפיצה", "s"),
        ),
        "free",
        "In,I",
    ),
    "rcd": MeasureDef(
        "rcd",
        (MCol("mult", "כפולה של IΔn", ""), MCol("t", "זמן ניתוק", "ms")),
        "free",
        "mult",
    ),
    "insulation": MeasureDef(
        "insulation",
        (MCol("ph1", "פזה 1", "MΩ"), MCol("ph2", "פזה 2", "MΩ"), MCol("ph3", "פזה 3", "MΩ")),
        "fixed",
        "row",
        row_labels=tuple(label for _, label in studies.INS_PAIRS),
    ),
    "earth": MeasureDef(
        "earth",
        (MCol("x", "r1-2", "m"), MCol("R", "R = U/I", "Ω")),
        "free",
        "x",
        condition_keys=("r13",),
    ),
    "continuity": MeasureDef(
        "continuity",
        (MCol("U", "U", "V"), MCol("I", "I", "A")),
        "fixed",
        "row",
        row_labels=("מוליך מאריק",),
    ),
}

DERIVED: dict[str, list[dict[str, str]]] = {
    "fault_loop": [{"key": "I_pf", "label_he": "I קצר צפוי = U/Z", "unit": "A"}],
    "mcb_trip": [{"key": "k", "label_he": "I/In", "unit": ""}],
    "continuity": [{"key": "R", "label_he": "R = U/I", "unit": "Ω"}],
}


def _f(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


# --------------------------------------------------------------------------- analysis


def plausibility(kind: str, rows: Rows) -> list[dict[str, Any]]:
    """Checks that need no model — physics every reading must obey. Never changes the data."""
    w: list[dict[str, Any]] = []
    if kind == "grid_voltages" and len(rows) >= 6:
        ln = [_f(rows[i].get("U")) for i in range(3)]
        ll = [_f(rows[i].get("U")) for i in range(3, 6)]
        for i, v in enumerate(ll):
            if v is None:
                continue
            a, b = ln[i], ln[(i + 1) % 3]
            if a is None or b is None:
                continue
            # |Va − Vb| for any angle between 90° and 150° — a generous bracket around 120°
            lo, hi = math.hypot(a, b), math.sqrt(a * a + b * b + math.sqrt(3) * a * b)
            if not 0.98 * lo <= v <= 1.02 * hi:
                w.append(
                    {
                        "code": "line_voltage_inconsistent",
                        "row": 3 + i,
                        "message": f"U קו = {v:g} V אינו מתאים למתחי הפאזה {a:g} V ו-{b:g} V "
                        f"(צפוי ≈ {math.sqrt(a * a + b * b + a * b):.0f} V)",
                    }
                )
    if kind == "fault_loop" and len(rows) >= 7:
        z = [_f(r.get("Z")) for r in rows]
        zll = z[6]
        for i in range(6):
            if z[i] is None or zll is None:
                continue
            # every loop contains one phase conductor; the L1-L2 loop contains two
            if z[i] < 0.5 * zll - 0.01:  # type: ignore[operator]
                w.append(
                    {
                        "code": "loop_below_phase",
                        "row": i,
                        "message": f"{ph.LOOPS[i]}: Z = {z[i]:g} Ω קטן ממחצית לולאת L1-L2 "
                        f"({zll:g} Ω). כל לולאה כוללת מוליך פאזה, ולכן ערך כזה אינו אפשרי — "
                        "כנראה הקריאה לא נרשמה או נמדד גודל אחר",
                    }
                )
    if kind == "mcb_trip":
        for i, r in enumerate(rows):
            a, b, t = _f(r.get("In")), _f(r.get("I")), _f(r.get("t"))
            if a and b is not None and b / a < 1.13:
                w.append(
                    {
                        "code": "below_non_trip",
                        "row": i,
                        "message": f"שורה {i + 1}: I/In = {b / a:.2f} < 1.13 — מא״ז תקין לא מנתק "
                        "בזרם זה בשעה הראשונה",
                    }
                )
            if a and b is not None and t is not None and b / a >= 2.55 and t > 60:
                w.append(
                    {
                        "code": "slow_trip",
                        "row": i,
                        "message": f"שורה {i + 1}: {t:g} s ב-{b / a:.2f}·In — איטי מהתחום של "
                        "IEC 60898-1 (≤ 60 s ב-2.55·In)",
                    }
                )
    if kind == "insulation":
        for i, r in enumerate(rows):
            vals = [_f(r.get(k)) for k in ("ph1", "ph2", "ph3")]
            if any(v is not None and v >= 999 for v in vals):
                w.append(
                    {
                        "code": "display_limit",
                        "row": i,
                        "message": f"שורה {i + 1}: 999 MΩ הוא גבול התצוגה של המגר, לא ערך נמדד",
                    }
                )
    if kind == "earth":
        pts = sorted(
            (x, rr)
            for r in rows
            if (x := _f(r.get("x"))) is not None and (rr := _f(r.get("R"))) is not None
        )
        for (x0, r0), (x1, r1) in zip(pts, pts[1:], strict=False):
            if r1 < r0 * 0.97:
                w.append(
                    {
                        "code": "profile_not_monotone",
                        "message": f"R יורד בין {x0:g} m ל-{x1:g} m — בקרקע אחידה הוא עולה "
                        "לאורך הקו. ייתכן תשתית תת-קרקעית או קריאה שגויה",
                    }
                )
    return w


def analyse(kind: str, rows: Rows, spec: InstallSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "fault_loop":
        out["rows"] = [
            {
                **r,
                "I_pf": ph.loop_voltage(spec, ph.LOOPS[min(i, 6)]) / z
                if (z := _f(r.get("Z")))
                else None,
            }
            for i, r in enumerate(rows)
        ]
    elif kind == "mcb_trip":
        out["rows"] = [
            {
                **r,
                "k": b / a
                if (a := _f(r.get("In"))) and (b := _f(r.get("I"))) is not None
                else None,
            }
            for r in rows
        ]
    elif kind == "continuity":
        out["rows"] = [
            {
                **r,
                "R": u / i if (u := _f(r.get("U"))) is not None and (i := _f(r.get("I"))) else None,
            }
            for r in rows
        ]
    out["warnings"] = plausibility(kind, rows)
    return out


# --------------------------------------------------------------------------- matching


def matching_case(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: InstallSpec
) -> dict[str, Any]:
    if kind == "mcb_trip":
        pts = [{"In": a, "I": b} for r in rows if (a := _f(r.get("In"))) and (b := _f(r.get("I")))]
        if not pts:
            raise InputError("no_operating_points", "no breaker rating / current pairs")
        return {"points": pts, "theta0": 0.0}
    if kind == "rcd":
        m = [x for r in rows if (x := _f(r.get("mult"))) and 0 < x <= 20]
        if not m:
            raise InputError("no_operating_points", "no multiples of IΔn")
        return {"multiples": m}
    if kind == "earth":
        try:
            r13 = float(conditions.get("r13", ""))
        except (TypeError, ValueError):
            raise InputError("missing_condition", "the distance r13 is required") from None
        if not math.isfinite(r13) or r13 <= 0:
            raise InputError("missing_condition", "the distance r13 is required")
        fr = [x / r13 for r in rows if (x := _f(r.get("x"))) and 0 < x < r13]
        if len(fr) < 2:
            raise InputError("no_operating_points", "at least two probe positions inside r13")
        return {"r13": r13, "fractions": fr}
    if kind == "continuity":
        i = next((x for r in rows if (x := _f(r.get("I")))), 10.0)
        return {"I_test": i, "R_extra": 0.0}
    if kind == "insulation":
        return {"U_test": 500.0, "t_read": 60.0, "guard": False}
    return {}


# --------------------------------------------------------------------------- texts


def theory_values(spec: InstallSpec) -> dict[str, float]:
    return {
        "Z_max": spec.Z_max,
        "R_g": spec.R_g,
        "R_062": spec.R_g,
        "R_pe": spec.R_pe,
        "I_trip": spec.rcd.k_trip * spec.rcd.I_dn * 1000,
    }


def row_extra(kind: str, i: int) -> dict[str, Any]:
    return {}


def derived_spec(spec: InstallSpec) -> dict[str, float]:
    n = spec.network
    return {
        "Z_LPE": n.Z_L + n.Z_PE,
        "I_pf_LPE": n.U0 / (n.Z_L + n.Z_PE),
        "Z_max": spec.Z_max,
        "R_g": spec.R_g,
        "R_pe": spec.R_pe,
        "I_5s": ph.mcb_current_for_time(spec.mcb, n.t_disc),
    }


def _spec_table(spec: InstallSpec) -> list[tuple[str, float]]:
    n, m, r, e = spec.network, spec.mcb, spec.rcd, spec.earth
    return [
        ("U<sub>L1-N</sub> [V]", n.U1),
        ("U<sub>L2-N</sub> [V]", n.U2),
        ("U<sub>L3-N</sub> [V]", n.U3),
        ("Z<sub>L</sub> [Ω] (לפאזה)", n.Z_L),
        ("Z<sub>N</sub> [Ω]", n.Z_N),
        ("Z<sub>PE</sub> [Ω]", n.Z_PE),
        (f"מא״ז מגן In [A] (אופיין {n.curve_prot})", n.In_prot),
        (
            f"Z<sub>max</sub> = U<sub>0</sub>/({K_INST[n.curve_prot]:g}·I<sub>n</sub>) [Ω]",
            spec.Z_max,
        ),
        ("τ תרמי של המא״ז [s]", m.tau),
        ("k<sub>t</sub> [×I<sub>n</sub>]", m.k_t),
        ("k<sub>m</sub> מגנטי [×I<sub>n</sub>]", m.k_m),
        ("IΔn [mA]", r.I_dn * 1000),
        ("ρ קרקע [Ω·m]", e.rho),
        ("R<sub>g</sub> [Ω] (מוט, Dwight)", spec.R_g),
        ("R מוליך מאריק [Ω]", spec.R_pe),
    ]


MODEL_HTML = (
    "מודל: לולאות התקלה הן סכום טורי של מוליך הפאזה, האפס וה-PE; זרם הקצר הצפוי U<sub>0</sub>/Z. "
    "מא״ז: מתג דו-מתכתי מסדר ראשון θ' = (k² − θ)/τ שמנתק ב-θ = k<sub>t</sub>², ושחרור מגנטי "
    "ב-k<sub>m</sub>·I<sub>n</sub>. מפסק פחת: מנתק כש-|I<sub>L</sub> + I<sub>N</sub>| ≥ "
    "k<sub>trip</sub>·IΔn. בידוד: R<sub>is</sub> ‖ R<sub>su</sub> ‖ C עם התנגדות פנימית של המגר. "
    "הארקה: מוט בקרקע אחידה; פרופיל נפילת המתח לפי אלקטרודה חצי-כדורית שקולה."
)
NOT_MODELLED = (
    "השראות הלולאות והזווית בין הפאזות (המכשיר מציג גודל בלבד), זיכרון תרמי בין בדיקות עוקבות "
    "(θ0 = 0 אלא אם נקבע), פיזור הייצור של המא״ז והמפסק, קרקע לא אחידה ותשתית תת-קרקעית, "
    "השראה הדדית בין חוטי אלקטרודות העזר, תלות הבידוד בטמפרטורה ולחות."
)

STEPS: list[tuple[str, str, str]] = [
    ("grid_voltages", "מתחי הרשת", "מודדים U בין כל פאזה לאפס ובין הפאזות (שקע תלת-פאזי בעמדה)."),
    (
        "fault_loop",
        "עכבת לולאת התקלה",
        "מכשיר בדיקת המתקן (MI 3125) במצב Z-LOOP; L-N, L-PE לכל פאזה ו-L1-L2. משווים ל-"
        "Z = 230/(k·In) של המבטח (תקנה 22: ניתוק תוך 5 s).",
    ),
    (
        "mcb_trip",
        "בדיקת מא״ז",
        "מזרימים זרם קבוע דרך המא״ז ומודדים את הזמן עד הניתוק. בין בדיקות ממתינים שהמא״ז "
        "יתקרר — אחרת הוא מנתק מהר יותר.",
    ),
    (
        "rcd",
        "מפסק מגן (פחת)",
        "MI 3125 במצב RCD: זמן ניתוק ב-½, 1 ו-5·IΔn, וזרם הניתוק ברמפה. ב-½IΔn המפסק אסור שינתק.",
    ),
    (
        "insulation",
        "התנגדות בידוד",
        "מגר 500 V בין כל ליפוף לערכה ובין הליפופים; קוראים אחרי שהקריאה מתייצבת. הדק G (Guard) "
        "מבטל את זרם הפנים.",
    ),
    (
        "earth",
        "התנגדות הארקה",
        "אלקטרודת זרם ב-r1-3 ≥ 5D ו-≥ 50 m, אלקטרודת מתח בקו אחד ב-0.2–0.8·r1-3; הערך ב-0.62·r1-3. "
        "אם בתחום 0.4–0.6 הפיזור מעל 10–15 % — חוזרים.",
    ),
    (
        "continuity",
        "רציפות מוליך ההארקה",
        "אמפרמטר–וולטמטר או מכשיר ייעודי בין גוף הציוד לפס ההארקה; מותר ≈ 0.05 Ω.",
    ),
]


def guide_steps() -> list[Step]:
    return [
        Step(
            "safety",
            "ack",
            "הוראות בטיחות",
            SAFETY + " בדיקת לולאה ומפסק פחת נעשות על רשת חיה — רק בשקעי הבדיקה, במכשיר תקין "
            "ובנוכחות המדריך. המגר מפעיל מתח ישר גבוה: לא נוגעים בהדקים ופורקים את הקיבול בסוף.",
        ),
        Step(
            "nameplate",
            "spec",
            "נתוני הרשת וההגנות",
            "רושמים את סוג המבטחים ואת IΔn ומזינים במפרט.",
        ),
        *study_steps(STEPS),
        Step("report", "report", "דו״ח מעבדה", "מפיקים דו״ח ומסכמים איזו בדיקה עמדה בדרישה ולמה."),
    ]


def report_info(spec: InstallSpec) -> dict[str, Any]:
    return {
        "goals": [
            "מדידת עכבת לולאת התקלה ובדיקת תנאי הניתוק (תקנה 22).",
            "אופיין זמן–זרם של מא״ז.",
            "בדיקת מפסק מגן (פחת) והבנת עקרון הטורואיד.",
            "מדידת התנגדות בידוד, התנגדות הארקה ורציפות מוליך ההארקה.",
        ],
        "equipment_title": "הרשת, ההגנות והנחות המודל",
        "spec_table": _spec_table(spec),
        "model_html": MODEL_HTML,
        "not_modelled": NOT_MODELLED,
        "assumed_limitation": "מפסק הפחת, הבידוד, ההארקה ומוליך ההארקה לא נמדדו בדוח 2025 — "
        "ערכיהם במפרט מוערכים, והסימולציה מדגימה את השיטה בלבד.",
        "general_limitation": "מודל המא״ז הותאם לבדיקה אחת (פיזור ≈ 24 %); k_t ו-τ אינם ניתנים "
        "להפרדה מהנתונים.",
    }


MODULE = ExperimentModule(
    id="installation",
    version=1,
    title_he="ניסוי 8: בדיקות במתקן חשמלי",
    summary_he="לולאת תקלה, מא״ז, מפסק פחת, התנגדות בידוד, הארקה ורציפות מוליך ההארקה",
    manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 8",
    equipment_he="המתקן",
    spec_model=InstallSpec,
    default_spec=lab_2025,
    presets=PRESETS,
    model_version=studies.MODEL_VERSION,
    studies=studies.STUDIES,
    execute=studies.execute,
    measure_defs=MEASURE_DEFS,
    derived_columns=DERIVED,
    analyse=analyse,
    matching_case=matching_case,
    theory_values=theory_values,
    row_extra=row_extra,
    guide_steps=guide_steps,
    derived_spec=derived_spec,
    report_info=report_info,
)
