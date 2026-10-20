"""Experiment 4 as a registered module. Shared motor tests delegate to experiment 2's
measurement tables and derivations (same quantities, same manual formulas)."""

from __future__ import annotations

from typing import Any

from vel.experiments.common import SAFETY, InputError, MCol, MeasureDef, Step, study_steps
from vel.experiments.induction_motor import derive as im_derive
from vel.experiments.induction_motor import module as im_module
from vel.experiments.registry import ExperimentModule
from vel.experiments.wound_rotor.spec import PRESETS, WoundSpec, nameplate_fit
from vel.experiments.wound_rotor.studies import MODEL_VERSION, STUDIES, execute
from vel.experiments.wound_rotor.templates import WINDINGS

Rows = list[dict[str, Any]]
SHARED = ("no_load", "locked_rotor", "load", "inverter")

_DC_LABELS = tuple(f"{label} · נקודה {k}" for _, label in WINDINGS for k in (1, 2, 3))

MEASURE_DEFS: dict[str, MeasureDef] = {
    **{k: im_module.MEASURE_DEFS[k] for k in SHARED},
    "starter_start": MeasureDef(
        "starter_start",
        (
            MCol("I_peak", "שיא זרם רגעי", "A"),
            MCol("I_start", "זרם התנעה RMS", "A"),
            MCol("t_95", "זמן התנעה", "s"),
            MCol("n_final", "מהירות סופית", "rpm"),
        ),
        "fixed",
        "row",
        row_labels=("התנעה דרך מתנע",),
    ),
    "load_rext": MeasureDef(
        "load_rext",
        im_module.MEASURE_DEFS["load"].columns,
        "free",
        "M",
        condition_keys=("R_ext",),
    ),
    "insulation": MeasureDef(
        "insulation",
        (MCol("R_ins", "התנגדות בידוד", "MΩ"),),
        "fixed",
        "row",
        row_labels=("סטטור U – מארז", "סטטור V – מארז", "סטטור W – מארז", "רוטור – מארז"),
    ),
    "dc_resistance": MeasureDef(
        "dc_resistance",
        (MCol("I", "I", "A"), MCol("U", "U", "V")),
        "fixed",
        "row",
        row_labels=_DC_LABELS,
    ),
    "ratio": MeasureDef(
        "ratio",
        (MCol("U1", "U1", "V"), MCol("U2", "U2 (רוטור)", "V")),
        "fixed",
        "row",
        row_labels=("רוטור נח", "מסובב בכיוון השדה", "מסובב נגד השדה"),
    ),
    "regulator": MeasureDef(
        "regulator",
        (MCol("angle", "α גאומטרית", "°"), MCol("U2", "U2", "V")),
        "free",
        "angle",
        condition_keys=("U_line",),
    ),
    "generator": MeasureDef(
        "generator",
        (
            MCol("n", "n", "rpm"),
            MCol("I1", "I1", "A"),
            MCol("P_W", "קריאת מד ההספק", "W"),
            MCol("pf", "cos φ", ""),
        ),
        "free",
        "n",
    ),
}

DERIVED_COLUMNS: dict[str, list[dict[str, str]]] = {
    **{k: v for k, v in im_module.DERIVED_COLUMNS.items() if k in SHARED},
    "load_rext": im_module.DERIVED_COLUMNS["load"],
    "dc_resistance": [{"key": "R", "label_he": "R = U/I", "unit": "Ω"}],
    "ratio": [{"key": "k", "label_he": "k = U1/U2", "unit": ""}],
    "generator": [{"key": "P1", "label_he": "P1 = 3·P", "unit": "W"}],
}


def analyse(kind: str, rows: Rows, spec: WoundSpec) -> dict[str, Any]:
    if kind in SHARED or kind == "load_rext":
        return im_module.analyse("load" if kind == "load_rext" else kind, rows, spec)
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "dc_resistance":
        r2, summary = im_derive.dc_resistance(rows)
        out.update(rows=r2, summary=summary)
    elif kind == "ratio":
        out["rows"] = [
            {
                **r,
                "k": (r["U1"] / r["U2"])
                if isinstance(r.get("U1"), (int, float))
                and isinstance(r.get("U2"), (int, float))
                and r["U2"]
                else None,
            }
            for r in rows
        ]
    elif kind == "generator":
        out["rows"] = [
            {**r, "P1": 3 * r["P_W"] if isinstance(r.get("P_W"), (int, float)) else None}
            for r in rows
        ]
    return out


def matching_case(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: WoundSpec
) -> dict[str, Any]:
    if kind in SHARED:
        return im_module.matching_case(kind, conditions, rows, spec)
    if kind == "starter_start":
        from vel.experiments.wound_rotor.transient import J_ASSUMED, default_steps

        return {"points": default_steps(spec), "J": J_ASSUMED, "M_brake": 0.0, "angle_deg": 0.0}
    if kind == "load_rext":
        base = im_module.matching_case("load", conditions, rows, spec)
        try:
            r_ext = float(conditions.get("R_ext", 3.0))
        except (TypeError, ValueError):
            r_ext = 3.0
        return {**base, "R_ext": r_ext}
    if kind == "regulator":
        ang = [float(r["angle"]) for r in rows if isinstance(r.get("angle"), (int, float))]
        if not ang:
            raise InputError("no_operating_points", "no angles")
        try:
            u = float(conditions.get("U_line", 100.0))
        except (TypeError, ValueError):
            u = 100.0
        return {"U_line": u, "angles": ang}
    if kind == "generator":
        n = [float(r["n"]) for r in rows if isinstance(r.get("n"), (int, float))]
        if not n:
            raise InputError("no_operating_points", "no speeds")
        return {"U_line": None, "n_values": n}
    if kind == "ratio":
        u1 = [float(r["U1"]) for r in rows if isinstance(r.get("U1"), (int, float))]
        return {"U_line": u1[0] if u1 else None, "n_hand": 30.0}
    if kind == "dc_resistance":
        cur = [rows[i].get("I") for i in range(min(3, len(rows)))]
        t = [float(x) for x in cur if isinstance(x, (int, float)) and x > 0]
        return {"I_targets": t or [0.2, 0.4, 0.6]}
    return {"U_test": 500.0}


def theory_values(spec: WoundSpec) -> dict[str, float]:
    e = spec.ecm
    k = 1.0 if spec.nameplate.connection == "Y" else 1 / 3
    return {
        "r_k": (e.R1 + spec.R2_referred) * k,
        "x_k": (e.X1 + spec.X2_referred) * k,
        "R2p_est": spec.R2_referred * k,
        "g0": 1 / (e.R_fe * k),
        "b0": 1 / (e.Xm * k),
        "k_turns": e.k,
        "R2_phase": e.R2,
    }


def row_extra(kind: str, i: int) -> dict[str, Any]:
    if kind == "dc_resistance":
        return {"winding": WINDINGS[i // 3][1] if i // 3 < len(WINDINGS) else "?"}
    return {}


def derived_spec(spec: WoundSpec) -> dict[str, float]:
    return {
        "n_sync": spec.n_sync,
        "slip_n": spec.slip_n,
        "M_n": spec.M_n,
        "R2_referred": spec.R2_referred,
        "X2_referred": spec.X2_referred,
    }


STUDY_STEPS: list[tuple[str, str, str]] = [
    ("insulation", "בדיקת בידוד", "מגר בין גוף המנוע ליציאות הסטטור והרוטור (ציור 4-1). טבלה 4.1."),
    (
        "dc_resistance",
        "התנגדות ליפופים",
        "ספק DC, מד זרם ומד מתח לכל ליפוף סטטור ובין כל זוג טבעות רוטור, שלוש נקודות (ציור 4-2). "
        "טבלה 4.2.",
    ),
    (
        "ratio",
        "מקדם השנאה",
        "מנתקים את הרוטור מהמתנע, 380 V על הסטטור, מודדים את מתח הרוטור. מסובבים את הרוטור ביד "
        "לשני הכיוונים ומודדים שוב (למה המתח משתנה?). טבלה 4.3.",
    ),
    (
        "no_load",
        "ניסוי ריקם",
        "מחזירים את הרוטור למתנע במצב אפס. מודדים I0, P0 ו-cos φ0 ב-380 V; מחשבים Y0, g0, b0. "
        "טבלה 4.4.",
    ),
    (
        "locked_rotor",
        "ניסוי קצר",
        "בולמים את הרוטור, מעלים מתח עד הזרם הנומינלי, 3–4 נקודות; מחשבים Rk, Zk, Xk. טבלה 4.5.",
    ),
    ("load", "ניסוי עומס", "S1 סגור, 380 V, מעמיסים בבלם, 6–8 נקודות I1, P1, N, M. טבלה 4.6."),
    (
        "load_rext",
        "עומס עם נגד ברוטור",
        "ידית המתנע במצב ביניים וחוזרים על ניסוי העומס. טבלה 4.7; משווים את האופיינים.",
    ),
    (
        "regulator",
        "ווסת מתח",
        "רוטור נעול, חיבור לפי ציור 4-6, כ-100 V. מתחילים במצב שבו U2 מינימלי ומודדים U2 מ-0 עד "
        "360 מעלות. טבלה 5.1.",
    ),
    (
        "generator",
        "מחולל במקביל לרשת",
        "מגבירים את מהירות הרוטור מעל הסינכרונית (ציור 4-8) ומודדים את ההספק המוחזר לרשת.",
    ),
    (
        "inverter",
        "מנוע עם אינוורטר",
        "טבעות הרוטור מגושרות. בכל תדר 4 נקודות עומס; משווים זרם התנעה ב-10 Hz מול 50 Hz.",
    ),
    (
        "starter_start",
        "התנעה דרך מתנע רוטור",
        "מתניעים עם מתנע הרוטור על הדרגה הגבוהה ומורידים אותו בשלבים עד קיצור הטבעות. "
        "הסימולציה מראה את הזרם, המהירות והמומנט בכל שלב.",
    ),
]


def guide_steps() -> list[Step]:
    return [
        Step(
            "safety",
            "ack",
            "הוראות בטיחות",
            SAFETY + " אין לנתק את מעגל הרוטור כשהמנוע עובד בעומס.",
        ),
        Step(
            "nameplate",
            "spec",
            "נתוני שלט המנוע",
            "רושמים את נתוני השלט (סטטור ורוטור) ומזינים במפרט המכונה.",
        ),
        *study_steps(STUDY_STEPS),
        Step("report", "report", "דו״ח מעבדה", "מפיקים דו״ח ומוסיפים דיון משלכם על הפערים."),
    ]


def report_info(spec: WoundSpec) -> dict[str, Any]:
    n, e = spec.nameplate, spec.ecm
    return {
        "goals": [
            "הכרת מבנה מנוע השראה עם רוטור מלופף.",
            "בדיקת בידוד והתנגדויות ליפופים; מקדם ההשנאה.",
            "ריקם, קצר ועומס; השפעת נגד נוסף ברוטור.",
            "המכונה כווסת מתח וכמחולל במקביל לרשת; הפעלה עם אינוורטר.",
        ],
        "equipment_title": "המכונה והנחות המודל",
        "spec_table": [
            ("P<sub>n</sub> [W]", n.P_n),
            ("U<sub>n</sub> [V]", n.U_n),
            ("I<sub>n</sub> [A]", n.I_n),
            ("n<sub>n</sub> [rpm]", n.n_n),
            ("U<sub>2n</sub> [V]", n.U2_n),
            ("I<sub>2n</sub> [A]", n.I2_n),
            ("R1 [Ω]", e.R1),
            ("X1 [Ω]", e.X1),
            ("R2 [Ω]", e.R2),
            ("X2 [Ω]", e.X2),
            ("k", e.k),
            ("R<sub>Fe</sub> [Ω]", e.R_fe),
            ("X<sub>m</sub> [Ω]", e.Xm),
        ],
        "model_html": (
            "מודל: מעגל תמורה T לכל פאזה עם שנאי אידיאלי ביחס k בין הסטטור לרוטור, כך שהדקי "
            "הטבעות נגישים. ברוטור מסתובב, המעגל החיצוני של הרוטור (מתנע, מכשירים) נפתר במעבר "
            "לתדר הסטטור (Z(s·f)/s) וקריאות המכשירים בו מוחזרות לתדר ההחלקה. רוטור נעול בזווית α: "
            "יחס מרוכב k·e<sup>j(p/2)α</sup>."
        ),
        "not_modelled": (
            "רוויה, אפקט עור, הרמוניות מרחביות (וריאציה של המתח בזווית מעבר לסינוס), הפסדי עומס "
            "נלווים, תלות טמפרטורה, הרמוניות האינוורטר."
        ),
        "assumed_limitation": "פרמטרי המכונה הותאמו לשלט ואינם מאומתים במדידה.",
        "general_limitation": "R2 קבוע: מומנט וזרם ההתנעה של מכונה אמיתית שונים במעט.",
    }


MODULE = ExperimentModule(
    id="wound_rotor",
    version=1,
    title_he="ניסוי 4: מכונת השראה עם רוטור מלופף",
    summary_he="מקדם השנאה, ריקם, קצר, עומס עם/בלי נגד ברוטור, ווסת מתח, מחולל ואינוורטר",
    manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 4",
    equipment_he="המכונה",
    spec_model=WoundSpec,
    default_spec=nameplate_fit,
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
