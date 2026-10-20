"""The network module (load flow, IEC 60909 short circuit) as a registered experiment.

Not one of the course's lab experiments: an extension that puts the lab in its supply network
— where the bench's voltage drop and fault-loop impedance (experiment 8) come from."""

from __future__ import annotations

import math
from typing import Any

from vel.experiments.common import SAFETY, MCol, MeasureDef, Step, study_steps
from vel.experiments.network import studies
from vel.experiments.network.spec import BUS_LABELS, BUSES, PRESETS, NetworkSpec, typical_substation
from vel.experiments.registry import ExperimentModule

Rows = list[dict[str, Any]]
ROW_LABELS = tuple(f"{b} — {BUS_LABELS[b]}" for b in BUSES)

MEASURE_DEFS: dict[str, MeasureDef] = {
    "load_flow": MeasureDef(
        "load_flow",
        (MCol("U", "U קווי", "V"),),
        "fixed",
        "row",
        row_labels=ROW_LABELS,
    ),
    "short_circuit": MeasureDef(
        "short_circuit",
        (MCol("Z_loop", "Z לולאת L-PE (מכשיר בדיקת מתקן)", "Ω"),),
        "fixed",
        "row",
        row_labels=ROW_LABELS,
    ),
}

DERIVED: dict[str, list[dict[str, str]]] = {
    "load_flow": [{"key": "du", "label_he": "מפל מתח", "unit": "%"}],
    "short_circuit": [{"key": "I_pf", "label_he": "זרם קצר צפוי U0/Z", "unit": "A"}],
}


def _f(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def analyse(kind: str, rows: Rows, spec: NetworkSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "load_flow":
        un = [spec.grid.U_n_kV * 1e3] + [spec.trafo.U2_V] * 3
        out["rows"] = [
            {**r, "du": 100 * (1 - u / un[i]) if (u := _f(r.get("U"))) and i < 4 else None}
            for i, r in enumerate(rows)
        ]
    elif kind == "short_circuit":
        u0 = spec.trafo.U2_V / math.sqrt(3)
        out["rows"] = [{**r, "I_pf": u0 / z if (z := _f(r.get("Z_loop"))) else None} for r in rows]
    return out


def matching_case(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: NetworkSpec
) -> dict[str, Any]:
    if kind == "load_flow":
        return {"scales": [1.0]}
    return {"t_k": 1.0}


def theory_values(spec: NetworkSpec) -> dict[str, float]:
    return {}


def row_extra(kind: str, i: int) -> dict[str, Any]:
    return {}


def derived_spec(spec: NetworkSpec) -> dict[str, float]:
    t = spec.trafo
    return {
        "I_n_lv": spec.I_n_lv,
        "Z_T": t.uk / 100 * t.U2_V**2 / (t.S_n_kVA * 1e3),
        "Ik_T": spec.I_n_lv / (t.uk / 100) / 1e3,
        "R_C1": spec.cable1.r * spec.cable1.L_m / 1000,
        "R_C2": spec.cable2.r * spec.cable2.L_m / 1000,
    }


STEPS: list[tuple[str, str, str]] = [
    (
        "load_flow",
        "זרימת עומסים",
        "מודדים את המתח הקווי בלוח הראשי, בלוח המעבדה ובעמדה, בעומס הרגיל של הבניין. "
        "משווים למפל המתח המחושב.",
    ),
    (
        "short_circuit",
        "זרמי קצר ועכבת לולאה",
        "מכשיר בדיקת המתקן במצב Z-LOOP (L-PE) בלוח המעבדה ובעמדה. העכבה המחושבת היא |2Z1 + Z0|/3 "
        "לפי IEC 60909.",
    ),
]


def guide_steps() -> list[Step]:
    return [
        Step(
            "safety",
            "ack",
            "הוראות בטיחות",
            SAFETY + " מדידות בלוחות חיים — רק בנוכחות חשמלאי מוסמך ובמכשירים מתאימים לקטגוריה.",
        ),
        Step("nameplate", "spec", "נתוני הרשת", "מזינים את נתוני השנאי, הכבלים והעומסים."),
        *study_steps(STEPS),
        Step("report", "report", "דו״ח", "מסכמים מפלי מתח, זרמי קצר ואת ההשוואה למדידות."),
    ]


MODEL_HTML = (
    "הרשת היא הזנה רדיאלית: רשת מתח גבוה (S''<sub>k</sub>) → שנאי Dyn → שני כבלים → העמדה. זרימת "
    "העומסים: עומסים בהספק קבוע, שנאי במודל T. הקצר: IEC 60909-0 (מקור שקול c·U<sub>n</sub>/√3, "
    "K<sub>T</sub>, κ בשיטה C, Z0 של כבל = 4·Z1). כל חישוב נפתר פעמיים — pandapower ופותר ישיר "
    "שכתבנו — והשניים חייבים להתאים."
)


def report_info(spec: NetworkSpec) -> dict[str, Any]:
    t = spec.trafo
    return {
        "goals": [
            "חישוב מפלי המתח וההעמסה בהזנת המעבדה.",
            "חישוב זרמי קצר מרביים ומזעריים לפי IEC 60909-0.",
            "הקשר בין עכבת לולאת התקלה (ניסוי 8) לבין רשת ההזנה.",
        ],
        "equipment_title": "רשת ההזנה והנחות המודל",
        "spec_table": [
            ("U<sub>n</sub> רשת [kV]", spec.grid.U_n_kV),
            ("S''<sub>k</sub> מרבי [MVA]", spec.grid.Sk_max_MVA),
            ("S<sub>n</sub> שנאי [kVA]", t.S_n_kVA),
            ("u<sub>k</sub> [%]", t.uk),
            ("כבל ראשי [m]", spec.cable1.L_m),
            ("כבל לעמדה [m]", spec.cable2.L_m),
        ],
        "model_html": MODEL_HTML,
        "not_modelled": "תרומת מנועים לזרם הקצר, הרמוניות, חוסר סימטריה של העומסים, שינוי "
        "מגעי השנאי, התנגדות התקלה, עכבת מוליך ה-PE בנפרד מ-Z0 של הכבל.",
        "assumed_limitation": studies.ASSUMED,
        "general_limitation": "טופולוגיה קבועה (רדיאלית, ארבעה צמתים); עורך רשת כללי יבוא בהמשך.",
    }


MODULE = ExperimentModule(
    id="network",
    version=1,
    title_he="מודול רשת: זרימת עומסים וקצרים",
    summary_he="הזנת המעבדה: מפלי מתח, העמסה, זרמי קצר לפי IEC 60909 ועכבת לולאה",
    manual_ref="הרחבה (לא בחוברת)",
    equipment_he="הרשת",
    spec_model=NetworkSpec,
    default_spec=typical_substation,
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
