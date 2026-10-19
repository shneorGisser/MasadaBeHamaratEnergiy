"""Experiment 1 as a registered module: binds spec, studies, derivation and texts together."""

from __future__ import annotations

from typing import Any

from vel.experiments.common import InputError
from vel.experiments.registry import ExperimentModule
from vel.experiments.transformer3ph import derive, guide
from vel.experiments.transformer3ph.measure_defs import MEASURE_DEFS
from vel.experiments.transformer3ph.spec import (
    PRESETS,
    TransformerSpec,
    assumed_lab_transformer,
)
from vel.experiments.transformer3ph.studies import MODEL_VERSION, STUDIES, WINDINGS, execute

Rows = list[dict[str, Any]]


def analyse(kind: str, rows: Rows, spec: TransformerSpec) -> dict[str, Any]:
    """Derived table + parameters for a table of readings (same functions as for simulation)."""
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "no_load":
        r2, params, at, w = derive.no_load(rows, spec)
        out.update(
            rows=r2, parameters=[p.to_json() for p in params], parameters_at=at or None, warnings=w
        )
    elif kind == "short_circuit":
        r2, params, at, w = derive.short_circuit(rows, spec)
        out.update(
            rows=r2, parameters=[p.to_json() for p in params], parameters_at=at or None, warnings=w
        )
    elif kind == "load":
        out["rows"] = derive.load(rows, spec)
    elif kind == "vector_group":
        out["parameters"] = [p.to_json() for p in derive.vector_group(rows)]
    elif kind == "dc_resistance":
        r2, summary = derive.dc_resistance(rows)
        out.update(rows=r2, summary=summary)
    out["warnings"] = list(out["warnings"]) + derive.plausibility(kind, rows, spec)
    return out


DERIVED_COLUMNS: dict[str, list[dict[str, str]]] = {
    "no_load": [{"key": "P0", "label_he": "P0 = 3·P", "unit": "W"}],
    "short_circuit": [{"key": "P_k", "label_he": "Pk = 3·P", "unit": "W"}],
    "load": [
        {"key": "P1", "label_he": "P1 = 3·P", "unit": "W"},
        {"key": "P2", "label_he": "P2 = 3·P", "unit": "W"},
        {"key": "beta", "label_he": "β", "unit": ""},
        {"key": "eta", "label_he": "η", "unit": ""},
        {"key": "dU_pct", "label_he": "ΔU%", "unit": "%"},
    ],
    "dc_resistance": [{"key": "R", "label_he": "R = U/I", "unit": "Ω"}],
}


def _vals(rows: Rows, key: str) -> list[float]:
    return [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]


def matching_case(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: TransformerSpec
) -> dict[str, Any]:
    if kind == "no_load":
        u = _vals(rows, "U1L")
        if not u:
            raise InputError("no_operating_points", "no measured U1 values")
        return {"U_line_values": u}
    if kind == "short_circuit":
        i = [x / spec.I1n_line for x in _vals(rows, "I1k") if x > 0]
        if not i:
            raise InputError("no_operating_points", "no measured I1k values")
        return {"I_targets_pu": i}
    if kind == "load":
        i2 = _vals(rows, "I2")
        loaded = [x / spec.I2n_line for x in i2 if x > 1e-6]
        if not loaded:
            raise InputError("no_operating_points", "no measured load currents")
        u1 = _vals(rows, "U1L")
        return {
            "load_kind": conditions.get("load_kind", "R"),
            "I2_targets_pu": loaded,
            "include_no_load": any(abs(x) <= 1e-6 for x in i2),
            "U_line": (sum(u1) / len(u1)) if u1 else None,
        }
    if kind == "vector_group":
        u = _vals(rows, "U_aAB")
        return {"U_line": u[0] if u else 100.0}
    if kind == "dc_resistance":
        cur = [rows[i].get("I") for i in range(min(3, len(rows)))]
        targets = [float(x) for x in cur if isinstance(x, (int, float)) and x > 0]
        return {"I_targets": targets or [1.0, 2.0, 3.0]}
    return {"U_test": 500.0}


def theory_values(spec: TransformerSpec) -> dict[str, float]:
    """Model values of the extracted parameters, per-phase star-equivalent, referred to the
    primary. Exact only within the approximations of the extraction formulas."""
    e = spec.ecm
    a = spec.turns_ratio
    star = spec.nameplate.primary == "Y"
    xm = e.Xm_unsat / (1 + e.sat_c)
    k = 1.0 if star else 1 / 3  # delta winding → star equivalent
    return {
        "a_ph": a,
        "R_fe": e.R_fe * k,
        "X_m": xm * k,
        "r_k": (e.R1 + a * a * e.R2) * k,
        "x_k": (e.X1 + a * a * e.X2) * k,
    }


def row_extra(kind: str, i: int) -> dict[str, Any]:
    if kind == "dc_resistance":
        return {"winding": WINDINGS[i // 3][1] if i // 3 < len(WINDINGS) else "?"}
    return {}


def derived_spec(spec: TransformerSpec) -> dict[str, float]:
    return {
        "U1_winding": spec.U1_winding,
        "U2_winding": spec.U2_winding,
        "turns_ratio": spec.turns_ratio,
        "I1n_line": spec.I1n_line,
        "I2n_line": spec.I2n_line,
    }


def report_info(spec: TransformerSpec) -> dict[str, Any]:
    n, e = spec.nameplate, spec.ecm
    return {
        "goals": [
            "הכרת מבנה השנאי התלת-פזי.",
            "בדיקת מצב הבידוד ומדידת התנגדויות הליפופים.",
            "בדיקת השנאי בריקם (יחס השנאה, ענף המגנוט), בקצר (הענף הטורי) ובעומס.",
            "קביעת קבוצת החיבורים בשיטת השעון.",
        ],
        "equipment_title": "השנאי והנחות המודל",
        "spec_table": [
            ("S<sub>n</sub> [VA]", n.S_n),
            ("U<sub>1n</sub> [V]", n.U1n),
            ("U<sub>2n</sub> [V]", n.U2n),
            ("f [Hz]", n.f_n),
            ("חיבור נקוב", f"{n.primary}{n.secondary.lower()}"),
            ("R1 [Ω]", e.R1),
            ("X1 [Ω]", e.X1),
            ("R2 [Ω]", e.R2),
            ("X2 [Ω]", e.X2),
            ("R<sub>Fe</sub> [Ω]", e.R_fe),
            ("X<sub>m,unsat</sub> [Ω]", e.Xm_unsat),
            ("c, n", f"{e.sat_c:g}, {e.sat_n:g}"),
        ],
        "model_html": (
            'מודל: מעגל תמורה T לכל עמוד (מודל "בנק"), במצב מתמיד סינוסי ב-f, עם ענף מגנוט רווי '
            '<span class="formula">X<sub>m</sub>(E) = X<sub>m,unsat</sub> / '
            "(1 + c·(E/E<sub>n</sub>)<sup>n</sup>)</span>. מכשירים אידיאליים."
        ),
        "not_modelled": (
            "הרמוניות של זרם המגנוט וקריאת מכשיר true-RMS, זרם התנעה ותופעות מעבר, צימוד מגנטי "
            "בין העמודים (האסימטריה של העמוד האמצעי), תלות טמפרטורה, דיוק המכשירים והעמסתם. מד "
            "הבידוד מציג פרמטר מודל ולא סימולציה."
        ),
        "assumed_limitation": (
            "פרמטרי השנאי מוערכים; השוואה כמותית מדויקת מחייבת נתוני שלט ומדידות ריקם וקצר."
        ),
        "general_limitation": (
            "המודל אינו כולל הרמוניות, תופעות מעבר, אסימטריית ליבה ודיוק מכשירים (ראו סעיף 2)."
        ),
    }


MODULE = ExperimentModule(
    id="transformer3ph",
    version=1,
    title_he="ניסוי 1: בדיקת שנאי תלת-פזי",
    summary_he="בידוד, התנגדות ליפופים, ריקם, קצר, עומס R/L/C וקבוצות חיבורים (שיטת השעון)",
    manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 1",
    equipment_he="השנאי",
    spec_model=TransformerSpec,
    default_spec=assumed_lab_transformer,
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
    guide_steps=guide.steps,
    derived_spec=derived_spec,
    report_info=report_info,
)
