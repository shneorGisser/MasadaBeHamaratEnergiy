"""Experiment 3 as a registered module."""

from __future__ import annotations

import math
from typing import Any

from vel.experiments.common import SAFETY, InputError, MCol, MeasureDef, Step, study_steps
from vel.experiments.registry import ExperimentModule
from vel.experiments.synchronous import derive
from vel.experiments.synchronous.spec import PRESETS, SyncSpec, fitted_lab_machine
from vel.experiments.synchronous.studies import MODEL_VERSION, STUDIES, execute
from vel.experiments.synchronous.templates import WINDINGS

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
            row_labels=(
                "סטטור U – מארז",
                "סטטור V – מארז",
                "סטטור W – מארז",
                "רוטור F1–F2 – מארז",
                "סטטור – רוטור",
            ),
        ),
        MeasureDef(
            "dc_resistance",
            (MCol("U", "U", "V"), MCol("I", "I", "A")),
            "fixed",
            "row",
            row_labels=_DC_LABELS,
        ),
        MeasureDef(
            "open_circuit",
            (
                MCol("If", "If", "A"),
                MCol("Ef_up", "Ef בעלייה", "V"),
                MCol("Ef_down", "Ef בירידה", "V"),
            ),
            "free",
            "If",
        ),
        MeasureDef(
            "short_circuit",
            (
                MCol("If", "If", "A"),
                MCol("Ik3", "Ik(3)", "A"),
                MCol("Ik2", "Ik(2)", "A"),
                MCol("Ik1", "Ik(1)", "A"),
            ),
            "free",
            "If",
        ),
        MeasureDef(
            "load_characteristic",
            (MCol("I1", "I1", "A"), MCol("U1", "U1", "V")),
            "free",
            "I1",
            condition_keys=("load_kind",),
        ),
        MeasureDef(
            "regulation",
            (MCol("I1", "Ia", "A"), MCol("If", "If", "A")),
            "free",
            "I1",
            condition_keys=("U_ref",),
        ),
        MeasureDef(
            "zpf",
            (MCol("If", "If", "A"), MCol("U1", "U1", "V")),
            "free",
            "If",
            condition_keys=("I_const",),
        ),
        MeasureDef(
            "v_curves",
            (
                MCol("P_set", "P בציר (עקומה)", "W"),
                MCol("If", "If", "A"),
                MCol("Ia", "Ia", "A"),
                MCol("pf", "cos φ", ""),
                MCol("P_W", "קריאת מד ההספק", "W"),
            ),
            "free",
            "P_set,If",
            condition_keys=("U_line",),
        ),
    ]
}

DERIVED_COLUMNS: dict[str, list[dict[str, str]]] = {
    "dc_resistance": [{"key": "R", "label_he": "R = U/I", "unit": "Ω"}],
    "open_circuit": [{"key": "dE", "label_he": "Ef↓ − Ef↑", "unit": "V"}],
    "short_circuit": [
        {"key": "r2", "label_he": "Ik(2)/Ik(3)", "unit": ""},
        {"key": "r1", "label_he": "Ik(1)/Ik(3)", "unit": ""},
    ],
    "v_curves": [{"key": "P1", "label_he": "P1 = 3·P", "unit": "W"}],
}


def analyse(kind: str, rows: Rows, spec: SyncSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "open_circuit":
        r2, params, w = derive.open_circuit(rows, spec)
        out.update(rows=r2, parameters=[p.to_json() for p in params], warnings=w)
    elif kind == "short_circuit":
        r2, params, w = derive.short_circuit(rows, spec)
        out.update(rows=r2, parameters=[p.to_json() for p in params], warnings=w)
    elif kind == "zpf":
        r2, params = derive.zpf(rows, spec, spec.nameplate.I_n)
        out.update(rows=r2, parameters=[p.to_json() for p in params])
    elif kind == "v_curves":
        r2, params = derive.v_curves(rows)
        out.update(rows=r2, parameters=[p.to_json() for p in params])
    elif kind == "dc_resistance":
        r2, summary = derive.dc_resistance(rows)
        out.update(rows=r2, summary=summary)
    out["warnings"] = list(out["warnings"]) + derive.plausibility(kind, rows, spec)
    return out


def _vals(rows: Rows, key: str) -> list[float]:
    return [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]


def _cond_float(conditions: dict[str, Any], key: str) -> float | None:
    try:
        v = float(conditions.get(key, ""))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def matching_case(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: SyncSpec
) -> dict[str, Any]:
    if kind in ("open_circuit", "short_circuit"):
        i_f = [x for x in _vals(rows, "If") if x >= 0]
        if not i_f:
            raise InputError("no_operating_points", "no field currents")
        return {"If_values": i_f, "n_drive": None}
    if kind == "zpf":
        i_f = [x for x in _vals(rows, "If") if x >= 0]
        if not i_f:
            raise InputError("no_operating_points", "no field currents")
        return {"If_values": i_f, "I_const": _cond_float(conditions, "I_const"), "n_drive": None}
    if kind == "load_characteristic":
        pairs = [
            (float(r["I1"]), float(r.get("U1") or 0))
            for r in rows
            if isinstance(r.get("I1"), (int, float))
        ]
        loaded = [i for i, _ in pairs if i > 1e-6]
        if not loaded:
            raise InputError("no_operating_points", "no load currents")
        u0 = next((u for i, u in pairs if i <= 1e-6 and u > 0), 240.0)
        return {
            "load_kind": conditions.get("load_kind", "R"),
            "U0": u0,
            "I_targets": loaded,
            "include_no_load": any(i <= 1e-6 for i, _ in pairs),
            "n_drive": None,
        }
    if kind == "regulation":
        ia = [x for x in _vals(rows, "I1") if x >= 0]
        if not ia:
            raise InputError("no_operating_points", "no armature currents")
        return {
            "U_ref": _cond_float(conditions, "U_ref") or 240.0,
            "I_targets": ia,
            "n_drive": None,
        }
    if kind == "v_curves":
        pts = [
            {"P": float(r["P_set"]), "If": float(r["If"])}
            for r in rows
            if isinstance(r.get("P_set"), (int, float))
            and isinstance(r.get("If"), (int, float))
            and r["If"] >= 0
        ]
        if not pts:
            raise InputError("no_operating_points", "no rows with both P and If")
        return {"U_line": _cond_float(conditions, "U_line"), "points": pts}
    if kind == "dc_resistance":
        u = [rows[i].get("U") for i in range(min(3, len(rows)))]
        targets = [float(x) for x in u if isinstance(x, (int, float)) and 0 < x <= 25]
        return {"U_values": targets or [8.0, 16.0, 20.0]}
    return {"U_test": 500.0}


def theory_values(spec: SyncSpec) -> dict[str, float]:
    return {
        "Xs": spec.Xs_unsat,
        "Xs_pu": spec.Xs_unsat / spec.Z_base,
        "X2": spec.ecm.X2,
        "X0": spec.ecm.X0,
        "Xl_potier": spec.ecm.Xl,
        "k_a": spec.ecm.k_a,
        "E_res": spec.line_factor() * spec.occ.emf(spec.occ.F_res),
    }


def row_extra(kind: str, i: int) -> dict[str, Any]:
    if kind == "dc_resistance":
        return {"winding": WINDINGS[i // 3][1] if i // 3 < len(WINDINGS) else "?"}
    return {}


def derived_spec(spec: SyncSpec) -> dict[str, float]:
    return {
        "n_sync": spec.nameplate.n_sync,
        "U_winding": spec.U_winding,
        "I_winding": spec.I_winding,
        "Z_base": spec.Z_base,
        "Xs_unsat": spec.Xs_unsat,
        "Xs_pu": spec.Xs_unsat / spec.Z_base,
    }


STUDY_STEPS: list[tuple[str, str, str]] = [
    (
        "insulation",
        "בדיקת בידוד",
        "מחברים את המגר בין גוף המכונה ליציאות הסטטור והרוטור, ובין הסטטור לרוטור (ציור 6-1). "
        "רושמים בטבלה 6.1.",
    ),
    (
        "dc_resistance",
        "התנגדות ליפופים",
        "לכל ליפוף (U1–U2, V1–V2, W1–W2, F1–F2) מודדים זרם ומתח בשלושה מתחים של הספק 0–25 V "
        "(ציור 6-2) ומחשבים התנגדות ממוצעת. טבלה 6.2.",
    ),
    (
        "open_circuit",
        "אופיין ריקם",
        "מנוע הסרוו מסובב את המחולל במהירות קבועה. מעלים את זרם העירור מאפס עד כ-1.2–1.3·Un "
        "ורושמים "
        "10 נקודות, ואז יורדים לאפס באותם זרמים. שימו לב לנקודה E0. טבלה 6.3.",
    ),
    (
        "short_circuit",
        "אופייני קצר",
        "מאפסים את העירור, מקצרים את הדקי העומס (תלת-פזי, אחר כך דו-פזי, אחר כך פאזה–אפס) ומעלים "
        "את זרם העירור עד שזרם הקצר מגיע לנומינלי, במהירות קבועה. טבלה 6.4.",
    ),
    (
        "load_characteristic",
        "אופייני עומס",
        "מכוונים עירור למתח ריקם של 240 V ושומרים אותו ואת התדר קבועים. סוגרים את S3 ומעמיסים: "
        "התנגדותי, השראי, קיבולי (לא לעבור 300 V). 8 נקודות לכל עומס. טבלה 6.5.",
    ),
    (
        "regulation",
        "אופיין ויסות",
        "בעומס התנגדותי, מגדילים את העומס בהדרגה ומווסתים את זרם העירור כך שהמתח נשאר נומינלי. "
        "רושמים 5–6 נקודות If מול Ia. טבלה 6.6.",
    ),
    (
        "zpf",
        "אופיין הגבי בזרם קבוע",
        "עומס השראי משתנה. מגיעים לזרם נומינלי במתח נומינלי, ואז מקטינים את העירור תוך שמירה "
        "על זרם "
        "קבוע (בשינוי העומס). 6 נקודות If ו-U1.",
    ),
    (
        "v_curves",
        "אופייני V",
        "המכונה עובדת כמנוע מחובר לרשת. בהספק קבוע משנים את זרם העירור ורושמים Ia ו-cos φ. "
        "טבלה 6.7.",
    ),
]


def guide_steps() -> list[Step]:
    return [
        Step(
            "safety",
            "ack",
            "הוראות בטיחות",
            SAFETY + " מכונות מסתובבות; אין לנתק את מעגל העירור כשהמכונה מחוברת לרשת.",
        ),
        Step(
            "nameplate",
            "spec",
            "נתוני שלט המכונה",
            "רושמים את נתוני השלט ומזינים במפרט המכונה. עד אז התוצאות מבוססות על ערכים "
            "מותאמים/מוערכים.",
        ),
        *study_steps(STUDY_STEPS),
        Step("report", "report", "דו״ח מעבדה", "מפיקים דו״ח ומוסיפים דיון משלכם על הפערים."),
    ]


def report_info(spec: SyncSpec) -> dict[str, Any]:
    n, e, o = spec.nameplate, spec.ecm, spec.occ
    return {
        "goals": [
            "הכרת מבנה המכונה הסינכרונית.",
            "בדיקת מצב הבידוד ומדידת התנגדויות הליפופים.",
            "אופיין ריקם ואופייני קצר תלת-, דו- וחד-פזי.",
            "אופייני עומס (R, L, C), אופיין ויסות ואופיין הגבי בזרם קבוע.",
            "אופייני V של המכונה בפעולה כמנוע.",
        ],
        "equipment_title": "המכונה והנחות המודל",
        "spec_table": [
            ("P<sub>n</sub> [W]", n.P_n),
            ("U<sub>n</sub> [V]", n.U_n),
            ("I<sub>n</sub> [A]", n.I_n),
            ("f [Hz]", n.f_n),
            ("קטבים", n.poles),
            ("חיבור", n.connection),
            ("I<sub>f,n</sub> [A]", n.If_n),
            ("R<sub>a</sub> [Ω]", e.Ra),
            ("X<sub>l</sub> [Ω]", e.Xl),
            ("k<sub>a</sub>", e.k_a),
            ("X<sub>s</sub> [Ω]", spec.Xs_unsat),
            ("X<sub>2</sub> [Ω]", e.X2),
            ("X<sub>0</sub> [Ω]", e.X0),
            ("R<sub>f</sub> [Ω]", e.R_f),
            (
                "OCC: a, I<sub>s</sub>, m, F<sub>res</sub>",
                f"{o.a:g}, {o.I_s:g}, {o.m:g}, {o.F_res:g}",
            ),
        ],
        "model_html": (
            "מודל: מכונה עם רוטור גלילי במצב מתמיד, שיטת הכוחות המגנטומניעים עם רוויה: "
            '<span class="formula">E<sub>r</sub> = '
            "OCC(|F<sub>f</sub> + k<sub>a</sub>I<sub>1</sub>|)</span> "
            "מאחורי עכבות הסדרים Z<sub>1</sub> = R<sub>a</sub> + jX<sub>l</sub>, "
            "Z<sub>2</sub>, Z<sub>0</sub> "
            "(לכן קצרים לא סימטריים ממודלים). השטף השיורי כהיסט בזרם העירור. מחובר לרשת: זווית "
            "העומס נפתרת מאיזון ההספקים על הענף היציב."
        ),
        "not_modelled": (
            "קטביות בולטת (X_d ≠ X_q, מומנט רלקטנס), היסטרזיס בעקומת הריקם, תופעות מעבר בקצר "
            "(X''_d, X'_d), הפסדי ברזל, תלות טמפרטורה, ווסת מהירות של המנוע המניע."
        ),
        "assumed_limitation": "פרמטרי המכונה מוערכים; השוואה כמותית מחייבת נתוני שלט ומדידות.",
        "general_limitation": (
            "הקצר מחושב במצב מתמיד בלבד; זרם הקצר הרגעי (התת-מעברי) אינו ממודל."
        ),
    }


MODULE = ExperimentModule(
    id="synchronous",
    version=1,
    title_he="ניסוי 3: בדיקת מכונה סינכרונית",
    summary_he="ריקם, קצר תלת/דו/חד-פזי, אופייני עומס, ויסות, אופיין הגבי ואופייני V",
    manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 3",
    equipment_he="המכונה",
    spec_model=SyncSpec,
    default_spec=fitted_lab_machine,
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
