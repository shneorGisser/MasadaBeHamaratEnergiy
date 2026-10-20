"""Why does a measured table differ from the simulation? Explanations a lab instructor would
check first, found from the comparison itself.

Two levels:

* ``explain(pairs)`` — pattern detectors over the paired cells, cheap, part of every comparison:
  - a systematic factor per quantity, recognised when it is √3, 3, 1000, −1 (line vs phase,
    one-phase vs total power, mA vs A, reversed polarity) or reported as an unexplained scale;
  - a constant offset (instrument zero);
  - single-row outliers, recognised when they are a factor ≈ 10 off (a decimal point);
  - two quantities swapped within a row;
  - most rows without a simulated counterpart (the operating points are out of the model's reach).
* ``probe_presets(...)`` — re-simulates the measured operating points with every saved
  parameter set of the experiment and ranks them. That is how "this table was measured on a
  Δ-connected machine" or "these short circuits belong to the 2025 parameter set" shows up.

Every finding is a hypothesis with the evidence that triggered it; nothing changes the data.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from typing import Any

from vel.experiments import registry
from vel.experiments.common import InputError, MeasureDef
from vel.services import measurements as ms

Finding = dict[str, Any]

MIN_ROWS = 3  # rows needed before a pattern counts as systematic
SPREAD_TOL = 0.04  # relative scatter (median absolute deviation) of a "constant" factor
MIN_EFFECT = 0.06  # a factor or offset smaller than this is not worth explaining
FACTOR_TOL = 0.05  # how close a factor must be to a known one (relative)

S3 = math.sqrt(3)
KNOWN_FACTORS: list[tuple[float, str]] = [
    (S3, "√3"),
    (1 / S3, "1/√3"),
    (3.0, "3"),
    (1 / 3, "1/3"),
    (1000.0, "1000"),
    (1e-3, "1/1000"),
    (-1.0, "−1"),
    (2.0, "2"),
    (0.5, "1/2"),
]


def _why_factor(name: str, unit: str) -> str | None:
    """What a recognised factor usually means for a quantity of this unit."""
    if name in ("√3", "1/√3"):
        if unit == "V":
            return "נראה שנרשם מתח קווי במקום פאזי (או להפך)"
        if unit == "A":
            return "נראה שנמדד זרם קו במקום זרם ליפוף (חיבור משולש), או להפך"
        if unit == "W":
            return "נראה שההספק חושב עם מתח קווי במקום פאזי (או להפך)"
    if name in ("3", "1/3") and unit in ("W", "var", "VA"):
        return "נראה שנרשמה קריאת מד הספק של פאזה אחת במקום ההספק הכולל (או להפך)"
    if name in ("1000", "1/1000"):
        return "נראה שהיחידה שגויה (mA/A, mV/V, W/kW)"
    if name == "−1":
        return "סימן הפוך: כיוון חיבור המכשיר (סליל זרם/מתח) הפוך לזה שבסימולציה"
    if name in ("2", "1/2"):
        return "פי 2: שתי פאזות בטור / מדידה בין שני הדקים במקום ליפוף אחד?"
    return None


# quantities that scale with the speed of the machine that generates them
SPEED_SCALED: dict[tuple[str, str], str] = {
    ("dc_generator", "E_up"): "n",
    ("dc_generator", "E_down"): "n",
    ("dc_generator", "U1"): "n",
    ("synchronous", "Ef_up"): "n_drive",
    ("synchronous", "Ef_down"): "n_drive",
}


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs))


def _mad(xs: list[float], m: float) -> float:
    return _median([abs(x - m) for x in xs]) if xs else math.inf


def explain(
    pairs: list[dict[str, Any]],
    *,
    experiment_id: str = "",
    conditions: dict[str, Any] | None = None,
    quantities: list[str] | None = None,
) -> list[Finding]:
    """quantities: the measured columns to examine (derived columns would only repeat them)."""
    findings: list[Finding] = []
    matched = [p for p in pairs if p["simulated_row"] is not None]
    unmatched = [p for p in pairs if p["simulated_row"] is None]
    if pairs and len(unmatched) >= max(2, len(pairs) / 2):
        findings.append(
            {
                "code": "operating_points_unreachable",
                "severity": "warn",
                "rows": [p["measured_row"] for p in unmatched],
                "message": f"{len(unmatched)} מתוך {len(pairs)} שורות ללא נקודה מסומלצת: נקודות "
                "העבודה שנמדדו אינן ברות-השגה במודל בתנאים שהוגדרו. בדוק את תנאי הסט (מתח, "
                "מהירות, עירור) ואת ההגדרה של המכונה — או הרץ 'בדיקת הגדרות חלופיות'",
            }
        )

    # cells by quantity: (row, measured, simulated, unit)
    by_q: dict[str, list[tuple[int, float, float, str]]] = {}
    for p in matched:
        for c in p["cells"]:
            m, s = c["measured"], c["simulated"]
            if quantities is not None and c["quantity"] not in quantities:
                continue
            if isinstance(m, (int, float)) and isinstance(s, (int, float)):
                by_q.setdefault(c["quantity"], []).append((p["measured_row"], m, s, c["unit"]))

    explained: set[str] = set()
    for q, pts in by_q.items():
        unit = pts[0][3]
        scale = max(abs(s) for _, _, s, _ in pts) or 1.0
        ratios = [(r, m / s) for r, m, s, _ in pts if abs(s) > 1e-9 * scale and abs(m) > 0]
        if len(ratios) >= MIN_ROWS:
            vals = [x for _, x in ratios]
            k = _median(vals)
            spread = _mad(vals, k) / abs(k) if k else math.inf
            if spread <= SPREAD_TOL and abs(k - 1) > MIN_EFFECT and not _offset_fits_better(pts, k):
                explained.add(q)
                known = next(
                    (name for f, name in KNOWN_FACTORS if abs(k / f - 1) <= FACTOR_TOL), None
                )
                why = _why_factor(known, unit) if known else None
                msg = f"{q}: כל השורות שונות מהסימולציה באותו יחס — נמדד ≈ {k:.3g} × מסומלץ"
                if why:
                    msg += f" (= {known}). {why}"
                else:
                    msg += ". יחס קבוע מצביע על פרמטר במודל (או תנאי הניסוי) ולא על פיזור מדידה"
                    cond = SPEED_SCALED.get((experiment_id, q))
                    n0 = (conditions or {}).get(cond or "")
                    if cond:
                        try:
                            n_set = float(n0) if n0 not in (None, "") else None
                        except (TypeError, ValueError):
                            n_set = None
                        msg += (
                            f". הגודל פרופורציוני למהירות: אם היא לא נרשמה, המדידה מתאימה "
                            f"למהירות של ≈ {n_set * k:.0f} סל״ד"
                            if n_set
                            else ". הגודל פרופורציוני למהירות: אם המהירות שונה מזו של "
                            f"הסימולציה, היא גדולה פי ≈ {k:.3g}"
                        )
                findings.append(
                    {
                        "code": "systematic_factor",
                        "severity": "info" if known else "warn",
                        "quantity": q,
                        "factor": k,
                        "known": known,
                        "rows": [r for r, _ in ratios],
                        "message": msg,
                    }
                )
            # single-row outliers against the table's own typical ratio
            if len(ratios) >= MIN_ROWS + 1 and k:
                base_spread = max(spread, 0.02)
                for r, x in ratios:
                    dev = x / k
                    if abs(dev - 1) > max(0.15, 4 * base_spread):
                        decimal = any(abs(dev / f - 1) < 0.15 for f in (10.0, 0.1, 100.0, 0.01))
                        findings.append(
                            {
                                "code": "decimal_point" if decimal else "row_outlier",
                                "severity": "warn",
                                "quantity": q,
                                "rows": [r],
                                "factor": dev,
                                "message": (
                                    f"שורה {r + 1}, {q}: חורג פי {dev:.3g} משאר הטבלה — כנראה "
                                    "נקודה עשרונית במקום הלא נכון"
                                    if decimal
                                    else f"שורה {r + 1}, {q}: חורג פי {dev:.3g} מהיחס האופייני "
                                    "של שאר הטבלה — בדוק את הקריאה או את תנאי השורה"
                                ),
                            }
                        )
        # constant offset (instrument zero / a fixed drop not in the model)
        if q not in explained and len(pts) >= MIN_ROWS:
            diffs = [m - s for _, m, s, _ in pts]
            d0 = _median(diffs)
            typical = _median([abs(s) for _, _, s, _ in pts]) or 1.0
            if abs(d0) > MIN_EFFECT * typical and _mad(diffs, d0) < 0.15 * abs(d0):
                findings.append(
                    {
                        "code": "constant_offset",
                        "severity": "info",
                        "quantity": q,
                        "offset": d0,
                        "rows": [r for r, *_ in pts],
                        "message": f"{q}: הפרש כמעט קבוע של {d0:+.3g} {unit} בכל השורות — "
                        "איפוס מכשיר, או מפל/הפסד קבוע שאינו במודל",
                    }
                )

    _merge_common_factor(findings)

    # two quantities of the same unit swapped within a row
    for p in matched:
        cells = [
            c
            for c in p["cells"]
            if isinstance(c["measured"], (int, float))
            and isinstance(c["simulated"], (int, float))
            and (quantities is None or c["quantity"] in quantities)
        ]
        for i, a in enumerate(cells):
            for b in cells[i + 1 :]:
                if a["unit"] != b["unit"] or not a["simulated"] or not b["simulated"]:
                    continue
                err_a = abs(a["measured"] / a["simulated"] - 1)
                err_b = abs(b["measured"] / b["simulated"] - 1)
                sw_a = abs(a["measured"] / b["simulated"] - 1)
                sw_b = abs(b["measured"] / a["simulated"] - 1)
                if min(err_a, err_b) > 0.25 and max(sw_a, sw_b) < 0.12:
                    findings.append(
                        {
                            "code": "swapped_columns",
                            "severity": "warn",
                            "quantity": f"{a['quantity']},{b['quantity']}",
                            "rows": [p["measured_row"]],
                            "message": f"שורה {p['measured_row'] + 1}: הערכים של "
                            f"{a['quantity']} ו-{b['quantity']} מתאימים לסימולציה אם מחליפים "
                            "ביניהם — כנראה נרשמו בעמודות הפוכות",
                        }
                    )
    return findings


def _offset_fits_better(pts: list[tuple[int, float, float, str]], k: float) -> bool:
    """A constant difference also looks like a (drifting) factor over a short range: keep the
    explanation whose residual is smaller."""
    typical = _median([abs(s) for _, _, s, _ in pts]) or 1.0
    diffs = [m - s for _, m, s, _ in pts]
    d0 = _median(diffs)
    res_offset = _median([abs(d - d0) for d in diffs]) / typical
    res_factor = _median([abs(m - k * s) for _, m, s, _ in pts]) / typical
    return res_offset < 0.5 * res_factor


def _merge_common_factor(findings: list[Finding]) -> None:
    """Several quantities off by (nearly) the same factor point to one cause in the model —
    a single, shared parameter — rather than to separate reading errors. Merged in place."""
    sys_f = [f for f in findings if f["code"] == "systematic_factor"]
    if len(sys_f) < 2:
        return
    ks = [f["factor"] for f in sys_f]
    k = _median(ks)
    group = [f for f in sys_f if abs(f["factor"] / k - 1) <= 0.06]
    if len(group) < 2:
        return
    knowns = {f["known"] for f in group}
    if len(knowns) == 1 and None not in knowns:
        return  # every quantity shows the same recognised factor: keep the specific findings
    names = ", ".join(f["quantity"] for f in group)
    for f in group:
        findings.remove(f)
    findings.append(
        {
            "code": "common_factor",
            "severity": "warn",
            "quantity": names,
            "factor": k,
            "rows": sorted({r for f in group for r in f["rows"]}),
            "message": f"{names}: כולם שונים מהסימולציה באותו יחס ≈ {k:.3g}. יחס משותף לכמה "
            "גדלים מצביע על פרמטר אחד במודל (למשל היגב או התנגדות), או על מכונה/חיבור שונים "
            "— הרץ 'בדיקת הגדרות חלופיות'",
        }
    )


# --------------------------------------------------------------------------- preset probe


def _score(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    rels = [abs(c["rel_error"]) for p in pairs for c in p["cells"] if c["rel_error"] is not None]
    return {
        "rows": len(pairs),
        "unmatched_rows": sum(1 for p in pairs if p["simulated_row"] is None),
        "median_abs_rel_error": _median(rels) if rels else None,
        "max_abs_rel_error": max(rels) if rels else None,
    }


def probe_presets(
    experiment_id: str,
    kind: str,
    conditions: dict[str, Any],
    rows: list[dict[str, Any]],
    current_spec_doc: dict[str, Any],
    current_circuit: Any,
) -> list[dict[str, Any]]:
    """Simulate the measured points with the project's parameters and with every preset of the
    experiment; the template circuit of each preset is used (a preset may change Y ↔ Δ)."""
    module = registry.get(experiment_id)
    d: MeasureDef = module.measure_defs[kind]
    sd = module.studies[kind]
    candidates: list[tuple[str, str, Callable[[], Any], bool]] = [
        ("project", "ההגדרה הנוכחית של הפרויקט", lambda: module.spec(current_spec_doc), True)
    ]
    candidates += [(pid, label, fn, False) for pid, (label, fn) in module.presets.items()]
    out: list[dict[str, Any]] = []
    for pid, label, fn, is_current in candidates:
        spec = fn()
        entry: dict[str, Any] = {"id": pid, "label_he": label}
        try:
            case = module.matching_case(kind, conditions, rows, spec)
        except InputError as exc:
            out.append({**entry, "status": "invalid_input", "error": exc.message})
            continue
        if is_current or sd.default_circuit is None:
            circuit = current_circuit
        else:
            c = sd.default_circuit(spec, "")
            circuit = (
                {k: v.model_dump() for k, v in c.items()} if isinstance(c, dict) else c.model_dump()
            )
        outcome = module.execute(kind, spec, circuit, case)
        entry["status"] = outcome.status
        if outcome.result is None:
            entry["error"] = (outcome.error or {}).get("message")
            out.append(entry)
            continue
        measured = module.analyse(kind, rows, spec)
        pairs, _ = ms.pair_rows(
            module, d, kind, measured["rows"], outcome.result["tables"][0]["rows"]
        )
        entry.update(_score(pairs))
        out.append(entry)

    def key(e: dict[str, Any]) -> tuple[int, float]:
        med = e.get("median_abs_rel_error")
        return (
            e.get("unmatched_rows", 99) if med is not None else 999,
            med if med is not None else 9e9,
        )

    out.sort(key=key)
    return out
