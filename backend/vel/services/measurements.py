"""Real-measurement sets (append-only entries), derived analysis, and comparison with runs."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from vel.errors import ApiError
from vel.experiments.transformer3ph import derive
from vel.experiments.transformer3ph.measure_defs import MEASURE_DEFS, MeasureDef
from vel.experiments.transformer3ph.spec import TransformerSpec
from vel.experiments.transformer3ph.studies import WINDINGS
from vel.orm import MeasurementEntry, MeasurementSet, Project, SimulationRun
from vel.units import UnitError, convert, units_for

MATCH_TOL = 0.02  # relative tolerance for pairing a measured operating point with a simulated one


def mdef(kind: str) -> MeasureDef:
    d = MEASURE_DEFS.get(kind)
    if d is None:
        raise ApiError(404, "unknown_study", f"no measurement definition for {kind}")
    return d


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
    d = mdef(s.study_kind)
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
    d = mdef(s.study_kind)
    current, _ = current_entries(session, s)
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for i in range(s.n_rows):
        r: dict[str, Any] = {"point": i + 1}
        if d.row_labels:
            r["row_label"] = d.row_labels[i] if i < len(d.row_labels) else f"#{i + 1}"
        if s.study_kind == "dc_resistance":
            r["winding"] = WINDINGS[i // 3][1] if i // 3 < len(WINDINGS) else "?"
        for c in d.columns:
            e = current.get((i, c.key))
            r[c.key] = e.value_si if e else None
            if e is None:
                missing.append({"row": i, "quantity": c.key})
        rows.append(r)
    return rows, missing


def analyse(kind: str, rows: list[dict[str, Any]], spec: TransformerSpec) -> dict[str, Any]:
    """Derived table + parameters for a measured table (same functions as for simulation)."""
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


def set_view(session: Session, s: MeasurementSet, spec: TransformerSpec) -> dict[str, Any]:
    d = mdef(s.study_kind)
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
        "derived_columns": DERIVED_COLUMNS.get(s.study_kind, []),
        "cells": cells,
        "missing": missing,
        "analysis": analyse(s.study_kind, rows, spec),
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
    s: MeasurementSet, rows: list[dict[str, Any]], spec: TransformerSpec
) -> dict[str, Any]:
    """Study case that simulates exactly the operating points that were measured."""
    k = s.study_kind

    def vals(key: str) -> list[float]:
        return [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]

    if k == "no_load":
        u = vals("U1L")
        if not u:
            raise ApiError(422, "no_operating_points", "no measured U1 values")
        return {"U_line_values": u}
    if k == "short_circuit":
        i = [x / spec.I1n_line for x in vals("I1k") if x > 0]
        if not i:
            raise ApiError(422, "no_operating_points", "no measured I1k values")
        return {"I_targets_pu": i}
    if k == "load":
        i2 = vals("I2")
        loaded = [x / spec.I2n_line for x in i2 if x > 1e-6]
        if not loaded:
            raise ApiError(422, "no_operating_points", "no measured load currents")
        u1 = vals("U1L")
        return {
            "load_kind": (s.conditions or {}).get("load_kind", "R"),
            "I2_targets_pu": loaded,
            "include_no_load": any(abs(x) <= 1e-6 for x in i2),
            "U_line": (sum(u1) / len(u1)) if u1 else None,
        }
    if k == "vector_group":
        u = vals("U_aAB")
        return {"U_line": u[0] if u else 100.0}
    if k == "dc_resistance":
        cur = [rows[i].get("I") for i in range(min(3, len(rows)))]
        targets = [float(x) for x in cur if isinstance(x, (int, float)) and x > 0]
        return {"I_targets": targets or [1.0, 2.0, 3.0]}
    return {"U_test": 500.0}


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


def theory_values(spec: TransformerSpec) -> dict[str, float]:
    """Model (equivalent-circuit) values of the extracted parameters, per-phase star-equivalent,
    referred to the primary. Exact only within the approximations of the extraction formulas."""
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


def compare(
    run: SimulationRun, s: MeasurementSet, meas_rows: list[dict[str, Any]], reference: str
) -> dict[str, Any]:
    if run.study_kind != s.study_kind:
        raise ApiError(422, "kind_mismatch", "run and measurement set belong to different studies")
    if run.result is None:
        raise ApiError(422, "failed_run", f"run status is {run.status}; nothing to compare")
    spec = TransformerSpec.model_validate(run.input_snapshot["transformer"])
    d = mdef(s.study_kind)
    measured = analyse(s.study_kind, meas_rows, spec)
    sim_table = run.result["tables"][0]
    sim_rows: list[dict[str, Any]] = sim_table["rows"]
    quantities = [c.key for c in d.columns] + [
        c["key"] for c in DERIVED_COLUMNS.get(s.study_kind, [])
    ]
    units = {c.key: c.unit for c in d.columns} | {
        c["key"]: c["unit"] for c in DERIVED_COLUMNS.get(s.study_kind, [])
    }
    pairs: list[dict[str, Any]] = []
    raw_keys = [c.key for c in d.columns]
    empty_rows = 0
    for i, mr in enumerate(measured["rows"]):
        if all(not isinstance(mr.get(k), (int, float)) for k in raw_keys):
            empty_rows += 1  # nothing measured in this row; not a comparison failure
            continue
        if d.match == "row":
            j: int | None = i if i < len(sim_rows) else None
            reason = None if j is not None else "אין שורה מקבילה בסימולציה"
        else:
            mv = mr.get(d.match)
            j, reason = None, None
            if not isinstance(mv, (int, float)):
                reason = f"חסרה מדידת {d.match} — לא ניתן לזהות את נקודת העבודה"
            else:
                cands = [
                    (abs(float(sr[d.match]) - mv), jj)
                    for jj, sr in enumerate(sim_rows)
                    if isinstance(sr.get(d.match), (int, float))
                ]
                if cands:
                    dist, jj = min(cands)
                    if dist <= MATCH_TOL * max(abs(mv), 1e-9) or (abs(mv) < 1e-6 and dist < 1e-6):
                        j = jj
                if j is None:
                    reason = (
                        f"אין נקודה מסומלצת בטווח ±{MATCH_TOL:.0%} מנקודת העבודה הנמדדת "
                        "— הרץ 'סימולציה בנקודות המדידה'"
                    )
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
                "match_value": mr.get(d.match) if d.match != "row" else None,
                "cells": cells,
            }
        )

    # parameter triad: theory (model) · simulation-extracted · measurement-extracted
    sim_params = {p["key"]: p for p in run.result.get("parameters", [])}
    meas_params = {p["key"]: p for p in measured.get("parameters", [])}
    theory = theory_values(spec)
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
        "notes": [
            "שגיאה = נמדד − מסומלץ; שגיאה יחסית מחושבת ביחס ל-"
            + ("ערך הסימולציה" if reference == "simulation" else "ערך המדידה"),
            "ההפרש כולל יחד שגיאת מודל (פרמטרים מוערכים, הנחות המודל) ושגיאת מדידה; "
            "אין מספיק מידע להפריד ביניהן ללא נתוני דיוק המכשירים",
        ],
    }


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
