"""Experiments 5 (DC motor) and 6 (DC generator) as registered modules. They share the
machine spec, the insulation/resistance tests and the plausibility checks."""

from __future__ import annotations

import math
from typing import Any

from vel.experiments.common import SAFETY, InputError, MCol, MeasureDef, Step, study_steps
from vel.experiments.dc_machine import studies
from vel.experiments.dc_machine.spec import PRESETS, DCSpec, fitted_lab_dc_machine
from vel.experiments.dc_machine.templates import WINDINGS
from vel.experiments.registry import ExperimentModule

Rows = list[dict[str, Any]]
W = 2 * math.pi / 60

_DC_LABELS = (
    *(f"{WINDINGS[0][1]} · נקודה {k}" for k in (1, 2, 3)),
    *(f"{WINDINGS[1][1]} · נקודה {k}" for k in (1, 2, 3)),
    f"{WINDINGS[2][1]} (אום-מטר)",
)

COMMON_DEFS: dict[str, MeasureDef] = {
    "insulation": MeasureDef(
        "insulation",
        (MCol("R_ins", "התנגדות בידוד", "MΩ"),),
        "fixed",
        "row",
        row_labels=("עוגן – גוף", "עירור מקבילי – גוף", "עירור טורי – גוף"),
    ),
    "dc_resistance": MeasureDef(
        "dc_resistance",
        (MCol("U", "U", "V"), MCol("I", "I", "A")),
        "fixed",
        "row",
        row_labels=_DC_LABELS,
    ),
}

_MOTOR_LOAD_COLS = (MCol("I1", "I1", "A"), MCol("n", "n", "rpm"), MCol("M", "M", "N·m"))

MOTOR_DEFS: dict[str, MeasureDef] = {
    **COMMON_DEFS,
    "no_load_field": MeasureDef(
        "no_load_field",
        (MCol("If", "If", "A"), MCol("I1", "I1", "A"), MCol("n", "n", "rpm")),
        "free",
        "If",
        condition_keys=("U",),
    ),
    "load": MeasureDef("load", _MOTOR_LOAD_COLS, "free", "M", condition_keys=("U", "If")),
    "load_rext": MeasureDef(
        "load_rext", _MOTOR_LOAD_COLS, "free", "M", condition_keys=("U", "If", "R_x")
    ),
    "rx_speed": MeasureDef(
        "rx_speed",
        (MCol("R_x", "R נוסף", "Ω"), MCol("n", "n", "rpm")),
        "free",
        "R_x",
        condition_keys=("U", "If", "M_load"),
    ),
    "field_speed": MeasureDef(
        "field_speed",
        (MCol("If", "If", "A"), MCol("n", "n", "rpm")),
        "free",
        "If",
        condition_keys=("U", "M_load"),
    ),
    "compound": MeasureDef("compound", _MOTOR_LOAD_COLS, "free", "M", condition_keys=("U", "If")),
}

GEN_DEFS: dict[str, MeasureDef] = {
    **COMMON_DEFS,
    "occ": MeasureDef(
        "occ",
        (MCol("If", "If", "A"), MCol("E_up", "E בעלייה", "V"), MCol("E_down", "E בירידה", "V")),
        "free",
        "If",
        condition_keys=("n",),
    ),
    "ext_separate": MeasureDef(
        "ext_separate",
        (MCol("Ia", "Ia", "A"), MCol("U1", "V1", "V")),
        "free",
        "Ia",
        condition_keys=("n",),
    ),
    "regulation": MeasureDef(
        "regulation",
        (MCol("If", "If", "A"), MCol("U1", "V1", "V")),
        "free",
        "If",
        condition_keys=("n", "Ia"),
    ),
    "shunt_load": MeasureDef(
        "shunt_load",
        (MCol("If", "If", "A"), MCol("Ia", "Ia", "A"), MCol("U1", "V1", "V")),
        "free",
        "Ia",
        condition_keys=("n",),
    ),
    "compound": MeasureDef(
        "compound",
        (
            MCol("pol", "קוטביות הטורי (+1 = S1-S2, −1 = S2-S1)", ""),
            MCol("Ia", "Ia", "A"),
            MCol("U1", "V1", "V"),
        ),
        "free",
        "pol,Ia",
        condition_keys=("n",),
    ),
    "grid": MeasureDef(
        "grid",
        (MCol("If", "If", "A"), MCol("Ia", "Ia (לרשת)", "A")),
        "free",
        "If",
        condition_keys=("U", "n"),
    ),
}

_P2 = [{"key": "P2", "label_he": "P2 = M·n/9.55", "unit": "W"}]
_R = [{"key": "R", "label_he": "R = U/I", "unit": "Ω"}]
MOTOR_DERIVED: dict[str, list[dict[str, str]]] = {
    "dc_resistance": _R,
    "load": _P2,
    "load_rext": _P2,
    "compound": _P2,
}
GEN_DERIVED: dict[str, list[dict[str, str]]] = {
    "dc_resistance": _R,
    "occ": [{"key": "dE", "label_he": "E↓ − E↑", "unit": "V"}],
    "ext_separate": [{"key": "P_out", "label_he": "P = V1·Ia", "unit": "W"}],
    "shunt_load": [{"key": "P_out", "label_he": "P = V1·Ia", "unit": "W"}],
}


# --------------------------------------------------------------------------- analysis


def _f(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def _dc_resistance(rows: Rows) -> tuple[Rows, Rows]:
    out = []
    for r in rows:
        u, i = _f(r.get("U")), _f(r.get("I"))
        out.append({**r, "R": u / i if u is not None and i else None})
    summary = []
    for k, (_, label) in enumerate(WINDINGS):
        sl = out[3 * k : 3 * k + 3] if k < 2 else out[6:7]
        vals = [float(x["R"]) for x in sl if x.get("R") is not None]
        summary.append({"winding": label, "R_avg": sum(vals) / len(vals) if vals else None})
    return out, summary


def plausibility(kind: str, rows: Rows) -> list[dict[str, Any]]:
    """Checks a teaching assistant would make by eye. They never change the data."""
    w: list[dict[str, Any]] = []

    if kind == "dc_resistance":
        # within one winding the three U/I values should agree (the armature's falls slowly
        # with current because of the brush drop — far less than a misread value)
        for start, stop in ((0, 3), (3, 6)):
            pts = [
                (i, _f(rows[i].get("U")), _f(rows[i].get("I")))
                for i in range(start, min(stop, len(rows)))
            ]
            rs = [(i, u / c) for i, u, c in pts if u is not None and c]
            if len(rs) < 3:
                continue
            med = sorted(x for _, x in rs)[1]
            for i, rv in rs:
                if abs(rv / med - 1) > 0.3:
                    tenfold = any(abs(rv / med / f - 1) < 0.2 for f in (10.0, 0.1))
                    w.append(
                        {
                            "code": "resistance_outlier",
                            "row": i,
                            "message": f"שורה {i + 1}: U/I = {rv:.3g} Ω מול ≈ {med:.3g} Ω בשאר "
                            "הנקודות של אותו ליפוף"
                            + (" — כנראה נקודה עשרונית שגויה בקריאה" if tenfold else ""),
                        }
                    )

    if kind == "shunt_load":
        pts = [(i, _f(r.get("If")), _f(r.get("Ia"))) for i, r in enumerate(rows)]
        good = [(i, a, b) for i, a, b in pts if a is not None and b is not None]
        for (_, f0, _), (i1, f1, _a1) in zip(good, good[1:], strict=False):
            if f1 > 1.2 * f0:
                w.append(
                    {
                        "code": "field_rises_with_load",
                        "row": i1,
                        "message": f"If עלה ל-{f1:g} A בעומס — במחולל מקבילי If יורד עם המתח. "
                        "ייתכן שעמודות If ו-Ia הוחלפו בשורה זו",
                    }
                )
    if kind in ("ext_separate", "shunt_load", "compound"):
        groups: dict[float, list[tuple[int, float, float]]] = {}
        for i, r in enumerate(rows):
            a, v = _f(r.get("Ia")), _f(r.get("U1"))
            if a is not None and v is not None:
                groups.setdefault(_f(r.get("pol")) or 0.0, []).append((i, a, v))
        if kind == "compound" and {1.0, -1.0} <= set(groups):
            cum = sorted(groups[1.0], key=lambda t: t[1])
            dif = sorted(groups[-1.0], key=lambda t: t[1])
            if cum and dif and cum[-1][1] > 0.3 and dif[-1][1] > 0.3:
                dv = cum[-1][2] - dif[-1][2]
                if abs(dv) < 0.02 * cum[-1][2]:
                    w.append(
                        {
                            "code": "series_effect_missing",
                            "message": f"שתי הקוטביות נותנות כמעט אותו מתח בעומס המרבי (הפרש "
                            f"{dv:+.3g} V). הליפוף הטורי אמור לשנות את המתח בכיוונים מנוגדים — "
                            "בדוק שהוא אכן היה במעגל ושהקוטביות הוחלפה",
                        }
                    )
                elif dv < 0:
                    w.append(
                        {
                            "code": "series_polarity",
                            "message": "המתח ב-S1-S2 נמוך מאשר ב-S2-S1: בחיבור זה S1-S2 הוא "
                            "המנוגד (התיוג הפוך לזה של המודל)",
                        }
                    )
    if kind == "occ":
        for i, r in enumerate(rows):
            up, dn = _f(r.get("E_up")), _f(r.get("E_down"))
            if up is not None and dn is not None and dn < up - max(2.0, 0.03 * up):
                w.append(
                    {
                        "code": "hysteresis_direction",
                        "row": i,
                        "message": "E בירידה נמוך מ-E בעלייה — בהיסטרזיס רגיל הוא גבוה ממנו",
                    }
                )
    if kind in ("load", "load_rext", "compound"):
        mpts = sorted(
            (float(r["M"]), float(r["n"]), i)
            for i, r in enumerate(rows)
            if _f(r.get("M")) is not None and _f(r.get("n")) is not None
        )
        for (m0, n0, _), (m1, n1, j1) in zip(mpts, mpts[1:], strict=False):
            if m1 > m0 and n1 > n0 + 30:
                w.append(
                    {
                        "code": "speed_rises_with_load",
                        "row": j1,
                        "message": f"המהירות עלתה ({n0:g} → {n1:g} סל״ד) כשהמומנט עלה — "
                        "במנוע מקבילי/מעורב מצטבר היא יורדת. בדוק את השורה",
                    }
                )
    return w


def analyse_motor(kind: str, rows: Rows, spec: DCSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "dc_resistance":
        r2, summary = _dc_resistance(rows)
        out.update(rows=r2, summary=summary)
    elif kind in ("load", "load_rext", "compound"):
        out["rows"] = [
            {
                **r,
                "P2": _f(r.get("M")) * _f(r.get("n")) * W  # type: ignore[operator]
                if _f(r.get("M")) is not None and _f(r.get("n")) is not None
                else None,
            }
            for r in rows
        ]
    out["warnings"] = plausibility(kind, rows)
    return out


def analyse_generator(kind: str, rows: Rows, spec: DCSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": rows, "parameters": [], "parameters_at": None, "warnings": []}
    if kind == "dc_resistance":
        r2, summary = _dc_resistance(rows)
        out.update(rows=r2, summary=summary)
    elif kind == "occ":
        out["rows"] = [
            {
                **r,
                "dE": _f(r.get("E_down")) - _f(r.get("E_up"))  # type: ignore[operator]
                if _f(r.get("E_down")) is not None and _f(r.get("E_up")) is not None
                else None,
            }
            for r in rows
        ]
    elif kind in ("ext_separate", "shunt_load"):
        out["rows"] = [
            {
                **r,
                "P_out": _f(r.get("U1")) * _f(r.get("Ia"))  # type: ignore[operator]
                if _f(r.get("U1")) is not None and _f(r.get("Ia")) is not None
                else None,
            }
            for r in rows
        ]
    out["warnings"] = plausibility(kind, rows)
    return out


# --------------------------------------------------------------------------- matching cases


def _vals(rows: Rows, key: str, lo: float = 0.0) -> list[float]:
    return [float(r[key]) for r in rows if _f(r.get(key)) is not None and float(r[key]) >= lo]


def _cond(conditions: dict[str, Any], key: str, default: float) -> float:
    try:
        v = float(conditions.get(key, ""))
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) and v >= 0 else default


def _need(xs: list[float], what: str) -> list[float]:
    if not xs:
        raise InputError("no_operating_points", f"no {what}")
    return xs


def _res_case(rows: Rows) -> dict[str, Any]:
    cur = [_f(rows[i].get("I")) for i in range(min(3, len(rows)))]
    t = [x for x in cur if x is not None and 0 < x <= 5]
    return {"I_targets": t or [0.7, 1.1, 1.6]}


def matching_motor(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: DCSpec
) -> dict[str, Any]:
    u = _cond(conditions, "U", studies.LAB_U)
    i_f = _cond(conditions, "If", 0.46) or 0.46
    if kind == "no_load_field":
        return {"U": u, "M_load": 0.0, "If_targets": _need(_vals(rows, "If", 1e-4), "If")}
    if kind == "field_speed":
        return {
            "U": u,
            "M_load": _cond(conditions, "M_load", round(0.6 * spec.M_n, 3)),
            "If_targets": _need(_vals(rows, "If", 1e-4), "If"),
        }
    if kind in ("load", "load_rext", "compound"):
        return {
            "U": u,
            "If": i_f,
            "R_x": _cond(conditions, "R_x", 30.0) if kind == "load_rext" else 0.0,
            "series": "cumulative" if kind == "compound" else "none",
            "M_targets": _need(_vals(rows, "M"), "torques"),
        }
    if kind == "rx_speed":
        return {
            "U": u,
            "If": i_f,
            "M_load": _cond(conditions, "M_load", round(0.6 * spec.M_n, 3)),
            "R_values": _need(_vals(rows, "R_x"), "resistances"),
        }
    if kind == "dc_resistance":
        return _res_case(rows)
    return {"U_test": 500.0}


def matching_generator(
    kind: str, conditions: dict[str, Any], rows: Rows, spec: DCSpec
) -> dict[str, Any]:
    n = _cond(conditions, "n", studies.GEN_N) or studies.GEN_N
    if kind == "occ":
        return {"n": n, "If_values": _need(_vals(rows, "If"), "If")}
    if kind in ("ext_separate", "shunt_load", "compound"):
        ia = _need(sorted(set(_vals(rows, "Ia"))), "Ia")
        u0 = next((float(r["U1"]) for r in rows if _f(r.get("Ia")) == 0 and _f(r.get("U1"))), 220.0)
        return {
            "n": n,
            "U0": u0,
            "excitation": "separate" if kind == "ext_separate" else "shunt",
            "connections": ["cumulative", "differential"] if kind == "compound" else ["none"],
            "I_targets": ia,
        }
    if kind == "regulation":
        return {
            "n": n,
            "Ia": _cond(conditions, "Ia", round(0.6 * spec.nameplate.I_n, 3)) or 1.5,
            "If_values": _need(_vals(rows, "If", 1e-4), "If"),
        }
    if kind == "grid":
        return {
            "U": _cond(conditions, "U", 220.0) or 220.0,
            "n": n,
            "If_values": _need(_vals(rows, "If", 1e-4), "If"),
        }
    if kind == "dc_resistance":
        return _res_case(rows)
    return {"U_test": 500.0}


# --------------------------------------------------------------------------- shared texts


def theory_values(spec: DCSpec) -> dict[str, float]:
    e = spec.ecm
    return {
        "R_a": e.R_a,
        "R_s": e.R_s,
        "R_f": e.R_f,
        "M_n": spec.M_n,
        "U_n": spec.nameplate.U_n,
        "E0": spec.occ.emf(spec.occ.F_res) * 2500.0 / spec.occ.n_ref,
    }


def row_extra(kind: str, i: int) -> dict[str, Any]:
    if kind == "dc_resistance":
        return {"winding": WINDINGS[min(i // 3, 2)][1]}
    return {}


def derived_spec(spec: DCSpec) -> dict[str, float]:
    return {
        "M_n": spec.M_n,
        "k_phi_n": spec.k_phi_n,
        "If_at_Un": spec.nameplate.U_n / spec.ecm.R_f,
        "M_fric": spec.ecm.P_rot_n / (spec.nameplate.n_n * W),
    }


def _spec_table(spec: DCSpec) -> list[tuple[str, float]]:
    n, e, o = spec.nameplate, spec.ecm, spec.occ
    return [
        ("P<sub>n</sub> [W]", n.P_n),
        ("U<sub>n</sub> [V]", n.U_n),
        ("I<sub>n</sub> [A]", n.I_n),
        ("n<sub>n</sub> [rpm]", n.n_n),
        ("I<sub>fn</sub> [A] (שלט)", n.If_n),
        ("R<sub>a</sub> [Ω]", e.R_a),
        ("R<sub>f</sub> [Ω]", e.R_f),
        ("R<sub>s</sub> [Ω]", e.R_s),
        ("ΔU<sub>brush</sub> [V]", e.U_brush),
        ("ρ<sub>s</sub> (טורי/מקבילי)", e.rho_s),
        ("k<sub>ar</sub> [A/A]", e.k_ar),
        ("P<sub>rot</sub>(n<sub>n</sub>) [W]", e.P_rot_n),
        ("OCC: a [V/A] @ n<sub>ref</sub>", o.a),
        ("OCC: I<sub>s</sub> [A]", o.I_s),
        ("OCC: m", o.m),
        ("F<sub>res</sub> [A]", o.F_res),
    ]


MODEL_HTML = (
    "מודל: עוגן = כא״מ E במקביל לנגד R<sub>a</sub> ולמפל מברשות כמעט קבוע; E = (n/n<sub>ref</sub>)"
    "·OCC(F), F = I<sub>f</sub> + ρ<sub>s</sub>·I<sub>s</sub> − k<sub>ar</sub>·|I<sub>a</sub>| + "
    "F<sub>res</sub> (עירור מקבילי, טורי, תגובת עוגן ושטף שיורי, ביחידות של זרם העירור "
    "המקבילי). מומנט M<sub>em</sub> = E·I<sub>a</sub>/ω; חיכוך כמומנט קבוע. מחולל מקבילי: "
    "נקודת העבודה היא זו שאליה מגיע תהליך הבנייה מהשטף השיורי."
)
NOT_MODELLED = (
    "היסטרזיס (עקומות עלייה/ירידה זהות), קומוטציה ומפל מברשות תלוי זרם, תלות טמפרטורה, "
    "תופעות מעבר (התנעה, בנייה), תלות ההפסדים בשטף."
)


# --------------------------------------------------------------------------- motor module

MOTOR_STEPS: list[tuple[str, str, str]] = [
    ("insulation", "בדיקת בידוד", "מגר 500 V בין כל ליפוף (עוגן, מקבילי, טורי) לגוף. טבלה 2.1."),
    (
        "dc_resistance",
        "התנגדות ליפופים",
        "אום-מטר לליפוף המקבילי; לעוגן ולטורי — מקור 0–25 V, שלוש נקודות עד 2 A (ציור 3.1). "
        "טבלה 2.2.",
    ),
    (
        "no_load_field",
        "מנוע מקבילי בריקם",
        "מעגל ציור 3.2. מקטינים את זרם העירור בהדרגה ומודדים If, I1, n — לא לעבור את המהירות "
        "המרבית. טבלה 2.3.",
    ),
    (
        "load",
        "מנוע מקבילי בעומס",
        "מעמיסים בבלם הסרוו, 6 נקודות I1, n, M ב-U1 ו-If קבועים. טבלה 2.4; עקומים n, M = f(I1).",
    ),
    (
        "load_rext",
        "עומס עם נגד נוסף",
        "מכוונים את R נוסף (בחוברת 10 Ω, במעבדה נמדד ב-30 Ω) וחוזרים על ההעמסה. טבלה 2.5.",
    ),
    (
        "rx_speed",
        "ויסות מהירות בנגד נוסף",
        "עומס 60% מהנומינלי; משנים R נוסף מאפס עד המרבי ומודדים n. טבלה 2.6.",
    ),
    (
        "field_speed",
        "ויסות מהירות בזרם העירור",
        "עומס 60%, R נוסף באפס; מקטינים את If — המנוע מאיץ. טבלה 2.7.",
    ),
    (
        "compound",
        "מנוע בעירור מעורב",
        "מוסיפים את הליפוף הטורי S1–S2 לענף העוגן (ציור 3.6) ומעמיסים. אם המהירות קופצת מיד — "
        "הטורי מחליש את השדה (מנוגד). טבלה 2.8.",
    ),
]


def guide_motor() -> list[Step]:
    return [
        Step(
            "safety",
            "ack",
            "הוראות בטיחות",
            SAFETY + " לעולם אין לנתק את מעגל העירור של מנוע מקבילי כשהוא מסתובב — הוא מתבדר.",
        ),
        Step("nameplate", "spec", "נתוני שלט המכונה", "רושמים את נתוני השלט ומזינים במפרט."),
        *study_steps(MOTOR_STEPS),
        Step("report", "report", "דו״ח מעבדה", "מפיקים דו״ח ועונים על שאלות החזרה."),
    ]


def report_motor(spec: DCSpec) -> dict[str, Any]:
    return {
        "goals": [
            "הכרת מבנה מכונת זרם ישר.",
            "מנוע בעירור מקבילי בריקם ובעומס.",
            "ויסות מהירות בנגד נוסף ובזרם העירור.",
            "מנוע בעירור מעורב.",
        ],
        "equipment_title": "המכונה והנחות המודל",
        "spec_table": _spec_table(spec),
        "model_html": MODEL_HTML,
        "not_modelled": NOT_MODELLED,
        "assumed_limitation": "הפרמטרים הותאמו לדוחות 2025 של ניסויים 5 ו-6; n_max מוערך.",
        "general_limitation": "חיכוך כמומנט קבוע; תלות ההפסדים בשטף ובמהירות מקורבת בלבד.",
    }


MOTOR_MODULE = ExperimentModule(
    id="dc_motor",
    version=1,
    title_he="ניסוי 5: מכונת זרם ישר כמנוע",
    summary_he="מנוע מקבילי בריקם ובעומס, ויסות מהירות בנגד נוסף ובעירור, עירור מעורב",
    manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 5",
    equipment_he="המכונה",
    spec_model=DCSpec,
    default_spec=fitted_lab_dc_machine,
    presets=PRESETS,
    model_version=studies.MODEL_VERSION,
    studies=studies.MOTOR_STUDIES,
    execute=studies.execute_motor,
    measure_defs=MOTOR_DEFS,
    derived_columns=MOTOR_DERIVED,
    analyse=analyse_motor,
    matching_case=matching_motor,
    theory_values=theory_values,
    row_extra=row_extra,
    guide_steps=guide_motor,
    derived_spec=derived_spec,
    report_info=report_motor,
)


# --------------------------------------------------------------------------- generator module

GEN_STEPS: list[tuple[str, str, str]] = [
    ("insulation", "בדיקת בידוד", "מגר 500 V בין כל ליפוף לגוף. טבלה 2.1."),
    (
        "dc_resistance",
        "התנגדות ליפופים",
        "אום-מטר למקבילי; עוגן וטורי במקור 0–25 V, שלוש נקודות (ציור 2.1). טבלה 2.2. למה לא "
        "אום-מטר רגיל? (מפל המברשות)",
    ),
    (
        "occ",
        "אופיין ריקם בעירור זר",
        "סרוו במהירות קבועה, S4 פתוח. רושמים E0 ב-If = 0, ואז E בעליית If ובירידתו. טבלה 2.3.",
    ),
    (
        "ext_separate",
        "אופיין חיצוני בעירור זר",
        "מכוונים If כך ש-V1 = 220 V בריקם, משאירים קבוע ומעמיסים עד In. טבלה 2.4.",
    ),
    (
        "regulation",
        "V1 = f(If) בזרם עומס קבוע",
        "Ia = 60% In; משנים If ומכוונים מחדש את העומס כך ש-Ia נשאר קבוע. טבלה 2.5.",
    ),
    (
        "shunt_load",
        "אופיין חיצוני בעירור מקבילי",
        "מעגל ציור 2.6: העירור מוזן מהדקי העוגן. מעלים לריקם 220 V ומעמיסים. טבלה 2.6.",
    ),
    (
        "compound",
        "אופיין חיצוני בעירור מעורב",
        "הליפוף הטורי בענף העומס (ציור 2.8). מעמיסים, הופכים את קוטביות הטורי וחוזרים. טבלה 2.7.",
    ),
    (
        "grid",
        "מחולל במקביל לרשת",
        "מחברים לרשת DC כשהמתחים שווים; מגדילים את If — הזרם לרשת עולה (מחולל); מקטינים — "
        "המכונה צורכת (מנוע).",
    ),
]


def guide_generator() -> list[Step]:
    return [
        Step("safety", "ack", "הוראות בטיחות", SAFETY + " התנעה רכה של מנוע הסרוו בלבד."),
        Step("nameplate", "spec", "נתוני שלט המכונה", "רושמים את נתוני השלט ומזינים במפרט."),
        *study_steps(GEN_STEPS),
        Step("report", "report", "דו״ח מעבדה", "מפיקים דו״ח ועונים על שאלות ההכנה."),
    ]


def report_generator(spec: DCSpec) -> dict[str, Any]:
    return {
        "goals": [
            "הכרת מבנה מכונת זרם ישר ושיטות העירור.",
            "אופיין ריקם ושטף שיורי.",
            "אופיינים חיצוניים בעירור זר, מקבילי ומעורב.",
            "פעולה במקביל לרשת.",
        ],
        "equipment_title": "המכונה והנחות המודל",
        "spec_table": _spec_table(spec),
        "model_html": MODEL_HTML,
        "not_modelled": NOT_MODELLED,
        "assumed_limitation": "מהירות הסרוו לא נרשמה בדוח 2025; ברירת המחדל 2800 סל״ד מוסקת "
        "מטבלה 2.6 (220 V ב-If ≈ 0.48 A), בעוד שאופיין הריקם (2.3) מתאים ל-≈ 2550 סל״ד.",
        "general_limitation": "אין היסטרזיס: עקומת הירידה של אופיין הריקם אינה מחושבת.",
    }


GEN_MODULE = ExperimentModule(
    id="dc_generator",
    version=1,
    title_he="ניסוי 6: מכונת זרם ישר כמחולל",
    summary_he="אופיין ריקם, אופיינים חיצוניים בעירור זר, מקבילי ומעורב, פעולה במקביל לרשת",
    manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 6",
    equipment_he="המכונה",
    spec_model=DCSpec,
    default_spec=fitted_lab_dc_machine,
    presets=PRESETS,
    model_version=studies.MODEL_VERSION,
    studies=studies.GEN_STUDIES,
    execute=studies.execute_generator,
    measure_defs=GEN_DEFS,
    derived_columns=GEN_DERIVED,
    analyse=analyse_generator,
    matching_case=matching_generator,
    theory_values=theory_values,
    row_extra=row_extra,
    guide_steps=guide_generator,
    derived_spec=derived_spec,
    report_info=report_generator,
)
