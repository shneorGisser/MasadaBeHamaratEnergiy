"""Real-measurement sets (append-only entries), derived analysis, and comparison with runs."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from vel.errors import ApiError
from vel.experiments import registry
from vel.experiments.common import InputError, MeasureDef
from vel.orm import MeasurementEntry, MeasurementSet, Project, SimulationRun
from vel.units import UnitError, convert, units_for

MATCH_TOL = 0.02  # relative tolerance for pairing a measured operating point with a simulated one


def module_for(experiment_id: str) -> registry.ExperimentModule:
    try:
        return registry.get(experiment_id)
    except KeyError as exc:
        raise ApiError(422, "unknown_experiment", str(exc)) from exc


def mdef(experiment_id: str, kind: str) -> MeasureDef:
    d = module_for(experiment_id).measure_defs.get(kind)
    if d is None:
        raise ApiError(404, "unknown_study", f"no measurement definition for {kind}")
    return d


def set_module(session: Session, s: MeasurementSet) -> registry.ExperimentModule:
    return module_for(project_of(session, s).experiment_id)


def definition_json(d: MeasureDef) -> dict[str, Any]:
    return {
        "kind": d.kind,
        "rows": d.rows,
        "match": d.match,
        "row_labels": list(d.row_labels),
        "condition_keys": list(d.condition_keys),
        "columns": [
            {"key": c.key, "label_he": c.label_he, "unit": c.unit, "units": units_for(c.unit)}
            for c in d.columns
        ],
    }


def current_entries(
    session: Session, s: MeasurementSet
) -> tuple[dict[tuple[int, str], MeasurementEntry], list[MeasurementEntry]]:
    all_entries = list(
        session.scalars(
            select(MeasurementEntry)
            .where(MeasurementEntry.set_id == s.id)
            .order_by(MeasurementEntry.created_at, MeasurementEntry.id)
        )
    )
    superseded = {e.supersedes_id for e in all_entries if e.supersedes_id}
    current: dict[tuple[int, str], MeasurementEntry] = {}
    for e in all_entries:
        if e.id not in superseded:
            current[(e.row_index, e.quantity)] = e
    return current, all_entries


def add_entry(
    session: Session,
    s: MeasurementSet,
    *,
    row_index: int,
    quantity: str,
    value: float,
    unit: str,
    instrument_range: str,
    note: str,
) -> MeasurementEntry:
    d = mdef(project_of(session, s).experiment_id, s.study_kind)
    col = next((c for c in d.columns if c.key == quantity), None)
    if col is None:
        raise ApiError(422, "unknown_quantity", f"{quantity} is not recorded in {s.study_kind}")
    if row_index < 0 or row_index >= s.n_rows:
        raise ApiError(422, "row_out_of_range", f"row {row_index} outside 0..{s.n_rows - 1}")
    try:
        value_si = convert(value, unit, col.unit)
    except UnitError as exc:
        raise ApiError(422, "invalid_unit", str(exc)) from exc
    current, _ = current_entries(session, s)
    prev = current.get((row_index, quantity))
    e = MeasurementEntry(
        set_id=s.id,
        row_index=row_index,
        quantity=quantity,
        value_si=value_si,
        entered_value=value,
        entered_unit=unit,
        instrument_range=instrument_range,
        note=note,
        supersedes_id=prev.id if prev else None,
    )
    session.add(e)
    session.commit()
    session.refresh(e)
    return e


def raw_rows(
    session: Session, s: MeasurementSet
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    module = set_module(session, s)
    d = mdef(module.id, s.study_kind)
    current, _ = current_entries(session, s)
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for i in range(s.n_rows):
        r: dict[str, Any] = {"point": i + 1}
        if d.row_labels:
            r["row_label"] = d.row_labels[i] if i < len(d.row_labels) else f"#{i + 1}"
        r.update(module.row_extra(s.study_kind, i))
        for c in d.columns:
            e = current.get((i, c.key))
            r[c.key] = e.value_si if e else None
            if e is None:
                missing.append({"row": i, "quantity": c.key})
        rows.append(r)
    return rows, missing


def set_view(session: Session, s: MeasurementSet) -> dict[str, Any]:
    module = set_module(session, s)
    spec = module.spec(project_of(session, s).spec_json)
    d = mdef(module.id, s.study_kind)
    current, history = current_entries(session, s)
    rows, missing = raw_rows(session, s)
    versions: dict[str, int] = {}
    for e in history:
        k = f"{e.row_index}:{e.quantity}"
        versions[k] = versions.get(k, 0) + 1
    cells = {
        f"{k[0]}:{k[1]}": {
            "entry_id": e.id,
            "value": e.value_si,
            "entered_value": e.entered_value,
            "entered_unit": e.entered_unit,
            "instrument_range": e.instrument_range,
            "note": e.note,
            "versions": versions.get(f"{k[0]}:{k[1]}", 1),
        }
        for k, e in current.items()
    }
    return {
        "set": set_json(s),
        "definition": definition_json(d),
        "derived_columns": module.derived_columns.get(s.study_kind, []),
        "cells": cells,
        "missing": missing,
        "analysis": module.analyse(s.study_kind, rows, spec),
        "history": [
            {
                "id": e.id,
                "row": e.row_index,
                "quantity": e.quantity,
                "entered_value": e.entered_value,
                "entered_unit": e.entered_unit,
                "value": e.value_si,
                "supersedes_id": e.supersedes_id,
                "note": e.note,
                "created_at": e.created_at.isoformat(),
            }
            for e in history
        ],
    }


def set_json(s: MeasurementSet) -> dict[str, Any]:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "study_kind": s.study_kind,
        "label": s.label,
        "lab_date": s.lab_date,
        "instruments": s.instruments,
        "notes": s.notes,
        "conditions": s.conditions or {},
        "n_rows": s.n_rows,
        "created_at": s.created_at.isoformat(),
    }


def matching_case(
    session: Session, s: MeasurementSet, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Study case that simulates exactly the operating points that were measured."""
    module = set_module(session, s)
    spec = module.spec(project_of(session, s).spec_json)
    try:
        return module.matching_case(s.study_kind, s.conditions or {}, rows, spec)
    except InputError as exc:
        raise ApiError(422, exc.code, exc.message) from exc


# --------------------------------------------------------------------------- comparison


def _rel(
    meas: float | None, sim: float | None, reference: str
) -> tuple[float | None, float | None, str | None]:
    if meas is None:
        return None, None, "חסרה מדידה"
    if sim is None:
        return None, None, "אין ערך מסומלץ"
    abs_err = meas - sim
    ref = sim if reference == "simulation" else meas
    scale = max(abs(meas), abs(sim))
    if abs(ref) <= 1e-12 * max(scale, 1.0):
        return abs_err, None, "ערך הייחוס הוא אפס — שגיאה יחסית אינה מוגדרת"
    return abs_err, abs_err / abs(ref), None


def compare(
    session: Session,
    run: SimulationRun,
    s: MeasurementSet,
    meas_rows: list[dict[str, Any]],
    reference: str,
) -> dict[str, Any]:
    if run.study_kind != s.study_kind:
        raise ApiError(422, "kind_mismatch", "run and measurement set belong to different studies")
    if run.result is None:
        raise ApiError(422, "failed_run", f"run status is {run.status}; nothing to compare")
    module = set_module(session, s)
    if run.input_snapshot.get("experiment_id", "transformer3ph") != module.id:
        raise ApiError(
            422, "kind_mismatch", "run and measurement set belong to different experiments"
        )
    from vel.services.runs import snapshot_spec

    spec = module.spec(snapshot_spec(run.input_snapshot))
    d = mdef(module.id, s.study_kind)
    measured = module.analyse(s.study_kind, meas_rows, spec)
    sim_table = run.result["tables"][0]
    sim_rows: list[dict[str, Any]] = sim_table["rows"]
    pairs, empty_rows = pair_rows(module, d, s.study_kind, measured["rows"], sim_rows, reference)

    # parameter triad: theory (model) · simulation-extracted · measurement-extracted
    sim_params = {p["key"]: p for p in run.result.get("parameters", [])}
    meas_params = {p["key"]: p for p in measured.get("parameters", [])}
    theory = module.theory_values(spec)
    params = []
    for key in list(dict.fromkeys([*sim_params, *meas_params])):
        sp, mp = sim_params.get(key), meas_params.get(key)
        base = sp or mp
        assert base is not None
        sv = sp["value"] if sp else None
        mv = mp["value"] if mp else None
        a, r, why = _rel(mv, sv, reference)
        params.append(
            {
                "key": key,
                "label_he": base["label_he"],
                "unit": base["unit"],
                "method": base["method"],
                "theory": theory.get(key),
                "simulated": sv,
                "measured": mv,
                "abs_error": a,
                "rel_error": r,
                "undefined_reason": why
                or (mp or {}).get("undefined_reason")
                or (sp or {}).get("undefined_reason"),
            }
        )

    n_cells = sum(len(p["cells"]) for p in pairs)
    n_missing = sum(1 for p in pairs for c in p["cells"] if c["measured"] is None)
    rels = [abs(c["rel_error"]) for p in pairs for c in p["cells"] if c["rel_error"] is not None]
    return {
        "run_id": run.id,
        "set_id": s.id,
        "study_kind": s.study_kind,
        "reference": reference,
        "match_key": d.match,
        "match_tolerance": MATCH_TOL,
        "pairs": pairs,
        "parameters": params,
        "measured_analysis": measured,
        "summary": {
            "rows": len(pairs),
            "empty_rows_skipped": empty_rows,
            "unmatched_rows": sum(1 for p in pairs if p["simulated_row"] is None),
            "cells": n_cells,
            "missing_measurements": n_missing,
            "max_abs_rel_error": max(rels) if rels else None,
            "median_abs_rel_error": sorted(rels)[len(rels) // 2] if rels else None,
        },
        "curves": run.result.get("curves", []),
        "simulated_rows": sim_rows,
        # a per-row table of independent windings has no common pattern to look for
        "diagnosis": []
        if d.match == "row"
        else _explain(pairs, module.id, s.conditions or {}, [c.key for c in d.columns]),
        "notes": [
            "שגיאה = נמדד − מסומלץ; שגיאה יחסית מחושבת ביחס ל-"
            + ("ערך הסימולציה" if reference == "simulation" else "ערך המדידה"),
            "ההפרש כולל יחד שגיאת מודל (פרמטרים מוערכים, הנחות המודל) ושגיאת מדידה; "
            "אין מספיק מידע להפריד ביניהן ללא נתוני דיוק המכשירים",
        ],
    }


def _explain(
    pairs: list[dict[str, Any]],
    experiment_id: str,
    conditions: dict[str, Any],
    quantities: list[str],
) -> list[dict[str, Any]]:
    from vel.services.diagnose import explain

    return explain(pairs, experiment_id=experiment_id, conditions=conditions, quantities=quantities)


def pair_rows(
    module: registry.ExperimentModule,
    d: MeasureDef,
    kind: str,
    measured_rows: list[dict[str, Any]],
    sim_rows: list[dict[str, Any]],
    reference: str = "simulation",
) -> tuple[list[dict[str, Any]], int]:
    """Measured rows (already analysed) paired with simulated rows at the same operating point,
    cell by cell. Returns (pairs, number of empty measured rows skipped)."""
    derived_cols = module.derived_columns.get(kind, [])
    # the operating-point key(s) are equal by construction of the pairing — not compared
    match_keys = set() if d.match == "row" else set(d.match.split(","))
    quantities = [c.key for c in d.columns if c.key not in match_keys] + [
        c["key"] for c in derived_cols
    ]
    units = {c.key: c.unit for c in d.columns} | {c["key"]: c["unit"] for c in derived_cols}
    pairs: list[dict[str, Any]] = []
    raw_keys = [c.key for c in d.columns]
    empty_rows = 0
    for i, mr in enumerate(measured_rows):
        if all(not isinstance(mr.get(k), (int, float)) for k in raw_keys):
            empty_rows += 1  # nothing measured in this row; not a comparison failure
            continue
        if d.match == "row":
            j: int | None = i if i < len(sim_rows) else None
            reason = None if j is not None else "אין שורה מקבילה בסימולציה"
        else:
            j, reason = _match_row(mr, sim_rows, d.match.split(","))
        sr = sim_rows[j] if j is not None else None
        cells = []
        for q in quantities:
            mval = mr.get(q) if isinstance(mr.get(q), (int, float)) else None
            sval = sr.get(q) if (sr is not None and isinstance(sr.get(q), (int, float))) else None
            a, r, why = _rel(mval, sval, reference) if sr is not None else (None, None, reason)
            cells.append(
                {
                    "quantity": q,
                    "unit": units.get(q, ""),
                    "measured": mval,
                    "simulated": sval,
                    "abs_error": a,
                    "rel_error": r,
                    "undefined_reason": why,
                }
            )
        pairs.append(
            {
                "measured_row": i,
                "simulated_row": j,
                "unmatched_reason": reason,
                "match_value": (
                    None
                    if d.match == "row"
                    else ", ".join(f"{k}={_short(mr.get(k))}" for k in d.match.split(","))
                ),
                "cells": cells,
            }
        )
    return pairs, empty_rows


def _short(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, (int, float)) else "—"


def _close(meas: float, sim: float) -> bool:
    if abs(meas) < 1e-6:
        return abs(sim - meas) < 1e-6
    return abs(sim - meas) <= MATCH_TOL * abs(meas)


def _match_row(
    mr: dict[str, Any], sim_rows: list[dict[str, Any]], keys: list[str]
) -> tuple[int | None, str | None]:
    """Simulated row at the same operating point: every key within ±MATCH_TOL (relative)."""
    missing = [k for k in keys if not isinstance(mr.get(k), (int, float))]
    if missing:
        return None, f"חסרה מדידת {', '.join(missing)} — לא ניתן לזהות את נקודת העבודה"
    best: tuple[float, int] | None = None
    for jj, sr in enumerate(sim_rows):
        if not all(isinstance(sr.get(k), (int, float)) for k in keys):
            continue
        if not all(_close(float(mr[k]), float(sr[k])) for k in keys):
            continue
        dist = sum(abs(float(sr[k]) - float(mr[k])) / max(abs(float(mr[k])), 1e-9) for k in keys)
        if best is None or dist < best[0]:
            best = (dist, jj)
    if best is None:
        return None, (
            f"אין נקודה מסומלצת בטווח ±{MATCH_TOL:.0%} מנקודת העבודה הנמדדת "
            "— הרץ 'סימולציה בנקודות המדידה'"
        )
    return best[1], None


def is_finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def load_set(session: Session, set_id: str) -> MeasurementSet:
    s = session.get(MeasurementSet, set_id)
    if s is None:
        raise ApiError(404, "not_found", f"measurement set {set_id} not found")
    return s


def project_of(session: Session, s: MeasurementSet) -> Project:
    p = session.get(Project, s.project_id)
    assert p is not None
    return p
