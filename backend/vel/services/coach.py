"""Measurement coach: while a table is being filled in at the bench, say which readings look
wrong — before the circuit is taken apart.

Why: a reading taken on the wrong range, the wrong pair of terminals or in mA instead of A is
usually found at home, when the report is being written and the bench is gone. The comparison
(services/diagnose.py) explains whole tables after the fact; the coach looks at each row as it
is typed.

How: the set's operating points are simulated with the project's current parameters (the same
study and circuit a run would use, but NOT saved: nothing here is a result), each measured
cell is compared with its simulated counterpart, and three things are reported:

* a known factor (√3, 3, 1000, 10, −1, 2 and inverses): a question with the likely cause and
  the value it would be if that were the case;
* a row that breaks the trend of the others in the same column (robust: median and MAD of the
  column's ratios), when the table has at least 3 rows;
* a large deviation (> 45 %) when there are too few rows for a trend.

Every hint is phrased as a question. The model can be the one that is wrong (an assumed
nameplate, a machine that does not meet its plate), so the coach never changes a value; the
student may enter the suggested one, which is recorded as a correction like any other.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from vel.errors import ApiError
from vel.experiments.common import InputError
from vel.orm import MeasurementSet
from vel.services import measurements as ms
from vel.services.diagnose import KNOWN_FACTORS, _why_factor
from vel.services.runs import build_snapshot, execute_snapshot

FACTORS = [*KNOWN_FACTORS, (10.0, "10"), (0.1, "1/10")]
FACTOR_TOL = 0.05
TREND_MIN = 0.15  # a row must be at least this far (relative) from the column's median ratio
TREND_K = 4.0  # … and this many robust standard deviations
LONE_TOL = 0.45  # deviation that is worth a question when there is no trend to compare with


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def _why_decimal(name: str) -> str | None:
    return (
        "נקודה עשרונית במקום הלא נכון, או תחום מדידה אחר במכשיר" if name in ("10", "1/10") else None
    )


def coach(session: Session, s: MeasurementSet) -> dict[str, Any]:
    p = ms.project_of(session, s)
    module = ms.set_module(session, s)
    d = module.measure_defs[s.study_kind]
    rows, _ = ms.raw_rows(session, s)
    measured_keys = [c.key for c in d.columns]
    base: dict[str, Any] = {"set_id": s.id, "hints": [], "status": "ok"}
    filled = [r for r in rows if any(isinstance(r.get(k), (int, float)) for k in measured_keys)]
    if not filled:
        return {**base, "status": "empty"}
    spec = module.spec(p.spec_json)
    try:
        case = module.matching_case(s.study_kind, s.conditions or {}, rows, spec)
    except InputError as exc:
        return {**base, "status": "no_operating_points", "message": exc.message}
    try:
        outcome = execute_snapshot(build_snapshot(session, p, s.study_kind, case))
    except ApiError as exc:
        return {**base, "status": "no_simulation", "message": exc.message}
    if outcome.result is None:
        return {
            **base,
            "status": "no_simulation",
            "message": (outcome.error or {}).get("message", "הסימולציה בנקודות האלה נכשלה"),
        }
    analysed = module.analyse(s.study_kind, rows, spec)["rows"]
    pairs, _ = ms.pair_rows(module, d, s.study_kind, analysed, outcome.result["tables"][0]["rows"])

    # ratio measured / simulated per measured column
    by_q: dict[str, list[tuple[int, float, float, float, str]]] = {}
    for pr in pairs:
        if pr["simulated_row"] is None:
            continue
        for c in pr["cells"]:
            q, m, sim = c["quantity"], c["measured"], c["simulated"]
            if q not in measured_keys or not isinstance(m, (int, float)):
                continue
            if not isinstance(sim, (int, float)) or abs(sim) < 1e-12 or m == 0:
                continue
            by_q.setdefault(q, []).append((pr["measured_row"], m, sim, m / sim, c["unit"]))

    labels = {c.key: c.label_he for c in d.columns}
    hints: list[dict[str, Any]] = []
    for q, pts in by_q.items():
        ratios = [r for *_, r, _ in pts]
        med = _median(ratios)
        mad = _median([abs(r - med) for r in ratios]) * 1.4826
        column_factor = None
        for f, name in FACTORS:
            if len(pts) >= 3 and abs(med / f - 1) <= FACTOR_TOL and abs(f - 1) > 0.06:
                column_factor = (f, name)
        for row, m, sim, ratio, unit in pts:
            label = labels.get(q, q)
            known = next(
                (
                    (f, n)
                    for f, n in FACTORS
                    if abs(f - 1) > 0.06 and abs(ratio / f - 1) <= FACTOR_TOL
                ),
                None,
            )
            if known:
                f, name = known
                why = _why_factor(name, unit) or _why_decimal(name) or "גורם קבוע מוכר"
                whole = column_factor is not None and column_factor[1] == name
                hints.append(
                    {
                        "row": row,
                        "quantity": q,
                        "kind": "factor",
                        "severity": "warn",
                        "factor": name,
                        "whole_column": whole,
                        "measured": m,
                        "expected": sim,
                        "suggested": m / f,
                        "message": (
                            f"{label} בשורה {row + 1}: {m:.4g} {unit} הוא בערך פי {name} מהצפוי "
                            f"({sim:.4g} {unit}). {why}?" + (" (כך בכל העמודה)" if whole else "")
                        ),
                    }
                )
                continue
            if len(pts) >= 3:
                spread = max(TREND_MIN * abs(med), TREND_K * mad)
                if abs(ratio - med) > spread:
                    hints.append(
                        {
                            "row": row,
                            "quantity": q,
                            "kind": "trend",
                            "severity": "info",
                            "measured": m,
                            "expected": sim * med,
                            "message": (
                                f"{label} בשורה {row + 1} ({m:.4g} {unit}) שובר את המגמה של שאר "
                                f"השורות: לפיהן היה צפוי בערך {sim * med:.4g} {unit}. האם תחום "
                                "המדידה או נקודת העבודה השתנו? כדאי למדוד שוב לפני "
                                "שמפרקים את המעגל."
                            ),
                        }
                    )
            elif abs(ratio - 1) > LONE_TOL:
                hints.append(
                    {
                        "row": row,
                        "quantity": q,
                        "kind": "deviation",
                        "severity": "info",
                        "measured": m,
                        "expected": sim,
                        "message": (
                            f"{label} בשורה {row + 1}: {m:.4g} {unit} רחוק ב-"
                            f"{abs(ratio - 1):.0%} מהצפוי ({sim:.4g} {unit}). האם המכשיר על התחום "
                            "הנכון? (ייתכן גם שהמודל רחוק מהמכונה, למשל ערכים מוערכים.)"
                        ),
                    }
                )
    hints.sort(key=lambda h: (h["row"], h["quantity"]))
    return {
        **base,
        "hints": hints,
        "provenance": p.spec_json.get("provenance"),
        "note": "הסימולציה בנקודות האלה לא נשמרה; היא רק לבדיקת הקריאות",
    }
