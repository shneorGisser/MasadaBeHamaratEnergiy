"""Experiment 2 as a registered module: measurement tables, guide, report texts, bindings."""

from __future__ import annotations

from typing import Any

from vel.experiments.common import SAFETY, InputError, MCol, MeasureDef, Step, study_steps
from vel.experiments.induction_motor import derive
from vel.experiments.induction_motor.derive import MotorLike
from vel.experiments.induction_motor.spec import PRESETS, MotorSpec, assumed_lab_motor
from vel.experiments.induction_motor.studies import MODEL_VERSION, STUDIES, execute
from vel.experiments.induction_motor.templates import WINDINGS
from vel.experiments.induction_motor.transient import J_ASSUMED
from vel.experiments.registry import ExperimentModule

Rows = list[dict[str, Any]]

_DC_LABELS = tuple(f"{label} · נקודה {k}" for _, label in WINDINGS for k in (1, 2, 3))

MEASURE_DEFS: dict[str, MeasureDef] = {
    d.kind: d
    for d in [
        MeasureDef(
            "insulation",
            (MCol("R_ins", "התנגדות בידוד", "MΩ"),),
            "fixed",
            "row",
            row_labels=("ליפוף U – מארז", "ליפוף V – מארז", "ליפוף W – מארז"),
        ),
        MeasureDef(
            "dc_resistance",
            (MCol("I", "I", "A"), MCol("U", "U", "V")),
            "fixed",
            "row",
            row_labels=_DC_LABELS,
        ),
        MeasureDef(
            "no_load",
            (
                MCol("U1L", "U1 קווי", "V"),
                MCol("I0", "I0", "A"),
                MCol("P_W", "קריאת מד ההספק", "W"),
                MCol("pf", "cos φ0", ""),
                MCol("n", "n", "rpm"),
            ),
            "free",
            "U1L",
        ),
        MeasureDef(
            "locked_rotor",
            (
                MCol("U_k", "Uk קווי", "V"),
                MCol("I_k", "Ik", "A"),
                MCol("P_W", "קריאת מד ההספק", "W"),
                MCol("pf", "cos φk", ""),
            ),
            "free",
            "I_k",
        ),
        MeasureDef(
            "load",
            (
                MCol("U1L", "U1 קווי", "V"),
                MCol("I1", "I1", "A"),
                MCol("P_W", "קריאת מד ההספק", "W"),
                MCol("pf", "cos φ", ""),
                MCol("n", "N", "rpm"),
                MCol("M", "M", "N·m"),
            ),
            "free",
            "M",
        ),
        MeasureDef(
            "dol_start",
            (
                MCol("I_peak", "שיא זרם רגעי (סקופ / צבת)", "A"),
                MCol("I_start", "זרם התנעה RMS", "A"),
                MCol("t_95", "זמן התנעה", "s"),
                MCol("n_final", "מהירות סופית", "rpm"),
            ),
            "fixed",
            "row",
            row_labels=("התנעה ישירה",),
        ),
        MeasureDef(
            "inverter",
            (
                MCol("f", "f", "Hz"),
                MCol("U_out", "Vout", "V"),
                MCol("I_out", "Iout", "A"),
                MCol("P_W", "קריאת מד ההספק", "W"),
                MCol("pf", "cos φ", ""),
                MCol("n", "n", "rpm"),
                MCol("M", "M", "N·m"),
            ),
            "free",
            "f,M",
            condition_keys=("U_boost",),
        ),
    ]
}

DERIVED_COLUMNS: dict[str, list[dict[str, str]]] = {
    "no_load": [{"key": "P0", "label_he": "P0 = 3·P", "unit": "W"}],
    "locked_rotor": [{"key": "P_k", "label_he": "Pk = 3·P", "unit": "W"}],
    "load": [
        {"key": "P1", "label_he": "P1 = 3·P", "unit": "W"},
        {"key": "P2", "label_he": "P2 = M·n/9.55", "unit": "W"},
        {"key": "eta", "label_he": "η", "unit": ""},
        {"key": "slip", "label_he": "s", "unit": ""},
    ],
    "inverter": [
        {"key": "P1", "label_he": "Pin = 3·P", "unit": "W"},
        {"key": "P2", "label_he": "Pout = M·n/9.55", "unit": "W"},
        {"key": "eta", "label_he": "η", "unit": ""},
        {"key": "slip", "label_he": "s", "unit": ""},
    ],
    "dc_resistance": [{"key": "R", "label_he": "R = U/I", "unit": "Ω"}],
}


def analyse(kind: str, rows: Rows, spec: MotorLike) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "no_load":
        r2, params, at, w = derive.no_load(rows, spec)
        out.update(
            rows=r2, parameters=[p.to_json() for p in params], parameters_at=at or None, warnings=w
        )
    elif kind == "locked_rotor":
        r2, params, at, w = derive.locked_rotor(rows, spec)
        out.update(
            rows=r2, parameters=[p.to_json() for p in params], parameters_at=at or None, warnings=w
        )
    elif kind == "load":
        out["rows"] = derive.load(rows, spec)
    elif kind == "inverter":
        out["rows"] = derive.inverter(rows, spec)
    elif kind == "dc_resistance":
        r2, summary = derive.dc_resistance(rows)
        out.update(rows=r2, summary=summary)
    out["warnings"] = list(out["warnings"]) + derive.plausibility(kind, rows, spec)
    return out


def _vals(rows: Rows, key: str) -> list[float]:
    return [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]


def matching_case(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: MotorLike
) -> dict[str, Any]:
    if kind == "no_load":
        u = [x for x in _vals(rows, "U1L") if x > 0]
        if not u:
            raise InputError("no_operating_points", "no measured U1 values")
        return {"U_line_values": u}
    if kind == "locked_rotor":
        i = [x / spec.nameplate.I_n for x in _vals(rows, "I_k") if x > 0]
        if not i:
            raise InputError("no_operating_points", "no measured Ik values")
        return {"I_targets_pu": i}
    if kind == "load":
        m = _vals(rows, "M")
        if not m:
            raise InputError("no_operating_points", "no measured torques")
        u1 = _vals(rows, "U1L")
        return {
            "M_targets": m,
            "U_line": (sum(u1) / len(u1)) if u1 else None,
            "torque_speed_curve": False,
        }
    if kind == "inverter":
        pts = [
            {"f": float(r["f"]), "M": float(r["M"])}
            for r in rows
            if isinstance(r.get("f"), (int, float))
            and r["f"] > 0
            and isinstance(r.get("M"), (int, float))
            and r["M"] >= 0
        ]
        if not pts:
            raise InputError("no_operating_points", "no rows with both f and M")
        boost = conditions.get("U_boost", 0.0)
        return {"points": pts, "law": "V/f", "U_boost": float(boost or 0.0), "f_start": 10.0}
    if kind == "dol_start":
        return {"U_line": None, "J": J_ASSUMED, "M_brake": 0.0, "t_end": 1.0, "angle_deg": 0.0}
    if kind == "dc_resistance":
        cur = [rows[i].get("I") for i in range(min(3, len(rows)))]
        targets = [float(x) for x in cur if isinstance(x, (int, float)) and x > 0]
        return {"I_targets": targets or [0.3, 0.6, 0.9]}
    return {"U_test": 500.0}


def theory_values(spec: MotorSpec) -> dict[str, float]:
    """Model values of the extracted parameters, star equivalent (Δ windings ÷ 3). The no-load
    and locked-rotor formulas are approximations (they neglect R1/X1 and the magnetizing branch
    respectively), so even a perfect measurement differs from these by a few percent."""
    e = spec.ecm
    k = 1.0 if spec.nameplate.connection == "Y" else 1 / 3
    return {
        "r_k": (e.R1 + e.R2p) * k,
        "x_k": (e.X1 + e.X2p) * k,
        "R2p_est": e.R2p * k,
        "g0": 1 / (e.R_fe * k),
        "b0": 1 / (e.Xm * k),
    }


def row_extra(kind: str, i: int) -> dict[str, Any]:
    if kind == "dc_resistance":
        return {"winding": WINDINGS[i // 3][1] if i // 3 < len(WINDINGS) else "?"}
    return {}


def derived_spec(spec: MotorSpec) -> dict[str, float]:
    return {
        "n_sync": spec.n_sync,
        "slip_n": spec.slip_n,
        "M_n": spec.M_n,
        "U_winding": spec.U_winding,
        "I_winding": spec.I_winding,
    }


STUDY_STEPS: list[tuple[str, str, str]] = [
    (
        "insulation",
        "בדיקת בידוד",
        "מחברים את המגר בין גוף המנוע (הארקה) לכל אחת מיציאות הליפופים (ציור 4-1) ומודדים "
        "במתח 500 V. רושמים בטבלה 4.1.",
    ),
    (
        "dc_resistance",
        "התנגדות ליפופי הסטטור",
        "מחברים ספק DC, מד זרם ומד מתח לכל ליפוף בנפרד (ציור 4-2): U1–U2, V1–V2, W1–W2. מודדים "
        "שלוש נקודות לכל ליפוף ורושמים ממוצע בטבלה 4.2.",
    ),
    (
        "no_load",
        "ניסוי ריקם",
        "מחברים לפי ציור 4-3, הבלם משוחרר. מעלים את המתח בווריאק עד 380 V על הדקים V1–U1–W1, "
        "מודדים U1, I0, P0 ו-cos φ0 ורושמים בטבלה 4.4. מחשבים Y0, g0, b0.",
    ),
    (
        "locked_rotor",
        "ניסוי רוטור נעול (קצר)",
        "נועלים את הרוטור. מעלים בזהירות את המתח מאפס ורושמים 3–4 נקודות; הזרם לא יעבור את "
        "הזרם הנומינלי. רושמים Uk, Ik, Pk, cos φk בטבלה 4.5 ומחשבים Rk, Zk, Xk.",
    ),
    (
        "load",
        "ניסוי עומס",
        "סוגרים את S1 ומעלים את המתח מ-0 עד 380 V. מעמיסים בעזרת בלם האבקה המגנטית ורושמים "
        "6–8 נקודות: I1, P1, N, M (טבלה 4.6). מחשבים P2, η, s, cos φ ומשרטטים את "
        "S, M, I1, cos φ כפונקציה של P2.",
    ),
    (
        "inverter",
        "מנוע עם אינוורטר",
        "מחברים את המנוע דרך האינוורטר (ציור 4-5). בכל תדר (20, 35, 50, 60 Hz) מעמיסים ב-4 "
        "נקודות ורושמים Vout, Iout, M, n. משווים את זרם ההתנעה ב-10 Hz להתנעה ישירה ב-50 Hz.",
    ),
    (
        "dol_start",
        "התנעה ישירה בזמן",
        "מחברים את המנוע ישירות לרשת (ללא אינוורטר) ורושמים בסקופ/צבת את שיא הזרם ואת זמן "
        "ההתנעה. הסימולציה מראה את זרם הקו, המהירות והמומנט כפונקציה של הזמן.",
    ),
]


def guide_steps() -> list[Step]:
    return [
        Step("safety", "ack", "הוראות בטיחות", SAFETY + " ציר המנוע מסתובב: אין לגעת בצימוד."),
        Step(
            "nameplate",
            "spec",
            "נתוני שלט המנוע",
            "מעיינים בנתוני השלט (הספק, מתח, זרם, מהירות, cos φ, חיבור) ומזינים אותם במפרט המנוע. "
            "עד שמזינים אותם, כל התוצאות מבוססות על ערכים מוערכים.",
        ),
        *study_steps(STUDY_STEPS),
        Step("report", "report", "דו״ח מעבדה", "מפיקים דו״ח ומוסיפים דיון משלכם על הפערים שנמצאו."),
    ]


def report_info(spec: MotorSpec) -> dict[str, Any]:
    n, e = spec.nameplate, spec.ecm
    return {
        "goals": [
            "הכרת מבנה מנוע ההשראה ועקרון פעולתו.",
            "בדיקת מצב הבידוד ומדידת התנגדויות הליפופים.",
            "בדיקת המנוע בריקם, ברוטור נעול (קצר) ובעומס.",
            "בדיקת המנוע עם אינוורטר.",
        ],
        "equipment_title": "המנוע והנחות המודל",
        "spec_table": [
            ("P<sub>n</sub> [W]", n.P_n),
            ("U<sub>n</sub> [V]", n.U_n),
            ("I<sub>n</sub> [A]", n.I_n),
            ("f [Hz]", n.f_n),
            ("n<sub>n</sub> [rpm]", n.n_n),
            ("קטבים", n.poles),
            ("חיבור", n.connection),
            ("R1 [Ω]", e.R1),
            ("X1 [Ω]", e.X1),
            ("R2' [Ω]", e.R2p),
            ("X2' [Ω]", e.X2p),
            ("R<sub>Fe</sub> [Ω]", e.R_fe),
            ("X<sub>m</sub> [Ω]", e.Xm),
            ("P<sub>fw,n</sub> [W]", e.P_fw_n),
        ],
        "model_html": (
            "מודל: מעגל תמורה T לכל ליפוף, במצב מתמיד סינוסי, עם ענף רוטור "
            "<span class=\"formula\">R2'/s + jX2'</span>. ההחלקה נקבעת מאיזון המומנטים "
            '<span class="formula">M<sub>em</sub>(s) − M<sub>fw</sub>(n) = M<sub>בלם</sub></span> '
            "על הענף היציב. הפסדי חיכוך ואוורור ∝ n². מכשירים אידיאליים."
        ),
        "not_modelled": (
            "רוויה של ענף המגנוט ושל שיני הרוטור, אפקט העור ברוטור (R2' קבוע בכל ההחלקות), "
            "הפסדי עומס נלווים, תלות טמפרטורה, הזנה לא סימטרית (רכיב סדר שלילי), תופעות מעבר "
            "בהתנעה, והרמוניות של האינוורטר."
        ),
        "assumed_limitation": (
            "פרמטרי המנוע מוערכים; השוואה כמותית מדויקת מחייבת נתוני שלט ומדידות ריקם ורוטור נעול."
        ),
        "general_limitation": (
            "R2' קבוע: מומנט ההתנעה וזרם ההתנעה של מנוע כלוב אמיתי (אפקט עור) שונים מהמודל."
        ),
    }


MODULE = ExperimentModule(
    id="induction_motor",
    version=1,
    title_he="ניסוי 2: בדיקת מנוע השראה עם רוטור כלוב",
    summary_he="בידוד, התנגדות ליפופים, ריקם, רוטור נעול, עומס בבלם ואינוורטר V/f",
    manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 2",
    equipment_he="המנוע",
    spec_model=MotorSpec,
    default_spec=assumed_lab_motor,
    presets=PRESETS,
    model_version=MODEL_VERSION,
    studies=STUDIES,
    execute=execute,
    measure_defs=MEASURE_DEFS,
    derived_columns=DERIVED_COLUMNS,
    analyse=analyse,
    matching_case=matching_case,
    theory_values=theory_values,
    row_extra=row_extra,
    guide_steps=guide_steps,
    derived_spec=derived_spec,
    report_info=report_info,
)
