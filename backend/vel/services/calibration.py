"""Calibrate the model to a measurement set: adjust a few spec parameters so the simulation at
the measured operating points reproduces the measurements (least squares).

Why a service and not the old one-off fit scripts: the residual IS the comparison the student
already sees — the same matching case (the measured operating points), the same row pairing,
the same quantities — so "calibrated" means exactly "the comparison table gets smaller", and
it works for any measurement set of any machine, not only the 2025 reports.

* Knobs: each knob scales one or more spec fields by one factor (several fields when only
  their sum is identifiable, e.g. X1 and X2' from a locked-rotor test). The search is over
  ln(factor), bounded to ×0.1…×10, from the current spec.
* Residuals: the relative error (measured − simulated)/measured of every cell compared in the
  initial comparison; a cell that loses its partner (failed run, unmatched row) costs 1.
* The fitted values are those of the spec as stored (at T_ref); the runs apply the winding
  temperature as usual.
* Honesty: the result reports the error before and after, the factor of each knob with a
  standard uncertainty from the Jacobian, the correlation between knobs (|ρ| > 0.95 = the data
  cannot separate them), and knobs that ended on a bound. It proposes a spec; nothing is
  saved until the student applies it, and the applied spec is marked "fitted" with the set
  named in its provenance note.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import least_squares
from sqlalchemy.orm import Session

from vel.errors import ApiError
from vel.experiments.thermal import at_operating_temperature
from vel.orm import MeasurementSet
from vel.services import measurements as ms
from vel.services.runs import current_circuit

BOUND = math.log(10.0)

# knobs whose effect the study's measurements determine, per experiment and study
DEFAULT_KNOBS: dict[str, dict[str, list[list[str]]]] = {
    "transformer3ph": {
        "no_load": [["ecm.Xm_unsat"], ["ecm.R_fe"], ["ecm.sat_c"]],
        "short_circuit": [["ecm.R1", "ecm.R2"], ["ecm.X1", "ecm.X2"]],
        "load": [["ecm.R1", "ecm.R2"], ["ecm.X1", "ecm.X2"]],
    },
    "induction_motor": {
        "no_load": [["ecm.Xm"], ["ecm.R_fe"], ["ecm.P_fw_n"]],
        "locked_rotor": [["ecm.R2p"], ["ecm.X1", "ecm.X2p"]],
        "load": [["ecm.R2p"], ["ecm.P_fw_n"]],
        "inverter": [["ecm.R2p"], ["ecm.P_fw_n"]],
    },
    "wound_rotor": {
        "no_load": [["ecm.Xm"], ["ecm.R_fe"], ["ecm.P_fw_n"]],
        "locked_rotor": [["ecm.R2"], ["ecm.X1", "ecm.X2"]],
        "ratio": [["ecm.k"]],
        "load": [["ecm.R2"], ["ecm.P_fw_n"]],
        "load_rext": [["ecm.R2"], ["ecm.P_fw_n"]],
    },
    "synchronous": {
        "open_circuit": [["occ.a"], ["occ.I_s"], ["occ.m"]],
        "short_circuit": [["ecm.k_a"]],
        "zpf": [["ecm.Xl"]],
        "load_characteristic": [["ecm.k_a"], ["ecm.Xl"]],
        "regulation": [["ecm.k_a"], ["ecm.Xl"]],
        "v_curves": [["ecm.k_a"], ["ecm.P_fw"]],
    },
    "dc_motor": {
        "no_load_field": [["occ.a"], ["occ.I_s"], ["ecm.P_rot_n"]],
        "load": [["ecm.k_ar"], ["ecm.P_rot_n"]],
        "load_rext": [["ecm.k_ar"], ["ecm.P_rot_n"]],
        "rx_speed": [["occ.a"], ["ecm.k_ar"]],
        "field_speed": [["occ.a"], ["occ.I_s"]],
        "compound": [["ecm.rho_s"]],
    },
    "dc_generator": {
        "occ": [["occ.a"], ["occ.I_s"], ["occ.m"]],
        "regulation": [["ecm.k_ar"]],
        "grid": [["ecm.k_ar"]],
    },
}


def _get(doc: dict[str, Any], path: str) -> Any:
    sec, key = path.split(".", 1)
    return (doc.get(sec) or {}).get(key)


def _scaled(doc: dict[str, Any], knobs: list[list[str]], x: np.ndarray) -> dict[str, Any]:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in doc.items()}
    for paths, xi in zip(knobs, x, strict=True):
        for p in paths:
            sec, key = p.split(".", 1)
            out[sec][key] = float(doc[sec][key]) * math.exp(float(xi))
    return out


def calibrate(
    session: Session, s: MeasurementSet, knobs: list[list[str]] | None = None
) -> dict[str, Any]:
    module = ms.set_module(session, s)
    p = ms.project_of(session, s)
    kind = s.study_kind
    knobs = knobs or DEFAULT_KNOBS.get(module.id, {}).get(kind)
    if not knobs:
        raise ApiError(422, "not_calibratable", f"no calibration is defined for {module.id}/{kind}")
    base_doc: dict[str, Any] = dict(p.spec_json)
    for paths in knobs:
        for path in paths:
            v = _get(base_doc, path)
            if not isinstance(v, (int, float)) or not v > 0:
                raise ApiError(422, "bad_knob", f"{path}: not a positive spec value")
    rows, _ = ms.raw_rows(session, s)
    case = ms.matching_case(session, s, rows)
    circuit = current_circuit(session, p, kind)
    d = ms.mdef(module.id, kind)
    base_spec = module.spec(base_doc)
    measured = module.analyse(kind, rows, base_spec)["rows"]

    def compare_at(x: np.ndarray) -> tuple[dict[tuple[int, str], float], str | None]:
        try:
            spec = module.spec(_scaled(base_doc, knobs, x))
        except Exception as exc:  # noqa: BLE001 — an invalid spec is a failed evaluation
            return {}, str(exc)
        spec, _ = at_operating_temperature(module.id, spec, kind)
        out = module.execute(kind, spec, circuit, case)
        if out.result is None:
            return {}, (out.error or {}).get("message", out.status)
        pairs, _ = ms.pair_rows(
            module, d, kind, measured, out.result["tables"][0]["rows"], "measurement"
        )
        cells = {
            (pr["measured_row"], c["quantity"]): float(c["rel_error"])
            for pr in pairs
            for c in pr["cells"]
            if c["rel_error"] is not None
            # the model gives exactly 0 (a feature it does not model, e.g. hysteresis width):
            # no knob can move that cell, it would only inflate the error
            and c["simulated"] != 0
        }
        return cells, None

    x0 = np.zeros(len(knobs))
    start, err = compare_at(x0)
    probe = module.execute(
        kind, at_operating_temperature(module.id, base_spec, kind)[0], circuit, case
    )
    excluded: list[str] = []
    if probe.result is not None:
        pairs0, _ = ms.pair_rows(
            module, d, kind, measured, probe.result["tables"][0]["rows"], "measurement"
        )
        excluded = sorted(
            {
                c["quantity"]
                for pr in pairs0
                for c in pr["cells"]
                if c["measured"] is not None and c["simulated"] == 0
            }
        )
    if not start:
        raise ApiError(422, "no_comparison", f"no measured cell can be compared ({err or 'empty'})")
    keys = sorted(start)
    if len(keys) < len(knobs):
        raise ApiError(
            422, "underdetermined", f"{len(keys)} measured values for {len(knobs)} knobs"
        )
    n_eval = 0

    def resid(x: np.ndarray) -> np.ndarray:
        nonlocal n_eval
        n_eval += 1
        cells, _ = compare_at(x)
        return np.array([cells.get(k, 1.0) for k in keys])

    sol = least_squares(
        resid,
        x0,
        bounds=(-BOUND, BOUND),
        diff_step=1e-3,
        x_scale=1.0,
        max_nfev=80 * (len(knobs) + 1),
    )
    r0 = resid(x0)
    r1 = sol.fun
    m, n = len(keys), len(knobs)
    J = sol.jac
    std: list[float | None] = [None] * n
    corr: list[list[float | None]] = [[None] * n for _ in range(n)]
    warnings: list[dict[str, Any]] = []
    if excluded:
        warnings.append(
            {
                "code": "not_modelled",
                "message": f"לא נכללו בכיול: {', '.join(excluded)} — המודל נותן להם 0 (תופעה שאינה "
                "ממודלת), ושום פרמטר לא ישנה זאת",
            }
        )
    try:
        jtj_inv = np.linalg.inv(J.T @ J)
        s2 = float(r1 @ r1) / max(m - n, 1)
        cov = s2 * jtj_inv
        sd = np.sqrt(np.clip(np.diag(cov), 0, None))
        std = [float(v) for v in sd]
        for i in range(n):
            for j in range(n):
                corr[i][j] = float(cov[i, j] / (sd[i] * sd[j])) if sd[i] > 0 and sd[j] > 0 else None
    except np.linalg.LinAlgError:
        warnings.append(
            {
                "code": "not_identifiable",
                "message": "המדידות אינן קובעות את הפרמטרים (מטריצה סינגולרית)",
            }
        )
    for i in range(n):
        for j in range(i + 1, n):
            c = corr[i][j]
            if c is not None and abs(c) > 0.95:
                warnings.append(
                    {
                        "code": "correlated",
                        "message": f"{'+'.join(knobs[i])} ו-{'+'.join(knobs[j])} מתואמים "
                        f"(ρ = {c:.2f}): המדידות לא מפרידות ביניהם — רק השילוב שלהם נקבע",
                    }
                )
    proposed = _scaled(base_doc, knobs, sol.x)
    results: list[dict[str, Any]] = []
    for i, paths in enumerate(knobs):
        f = math.exp(float(sol.x[i]))
        on_bound = abs(abs(float(sol.x[i])) - BOUND) < 1e-3
        if on_bound:
            warnings.append(
                {
                    "code": "on_bound",
                    "message": f"{'+'.join(paths)} הגיע לגבול החיפוש (×{f:.3g}): המדידות אינן "
                    "קובעות אותו (למשל אין רוויה בתחום שנמדד) או שיש טעות במדידה — "
                    "לא להחיל בלי בדיקה",
                }
            )
        if not on_bound and std[i] is not None and std[i] > 0.5:  # type: ignore[operator]
            warnings.append(
                {
                    "code": "poorly_determined",
                    "message": f"{'+'.join(paths)} נקבע ברע (אי-ודאות יחסית ≈ {std[i]:.0%}): "
                    "המדידות כמעט אינן רגישות אליו",
                }
            )
        results.append(
            {
                "paths": paths,
                "factor": f,
                "rel_std": std[i],  # of ln(factor) ≈ relative standard uncertainty
                "before": {p_: _get(base_doc, p_) for p_ in paths},
                "after": {p_: _get(proposed, p_) for p_ in paths},
                "on_bound": on_bound,
            }
        )

    def summary(r: np.ndarray) -> dict[str, float]:
        return {
            "rms_rel": float(np.sqrt(np.mean(r**2))),
            "max_abs_rel": float(np.max(np.abs(r))),
        }

    proposed["provenance"] = "fitted"
    note = (
        f"כויל לסט המדידות '{s.label or s.id[:8]}' ({kind}): "
        + ", ".join(
            f"{'+'.join(k_)} ×{math.exp(float(x_)):.4g}"
            for k_, x_ in zip(knobs, sol.x, strict=True)
        )
        + f"; שגיאה RMS {summary(r0)['rms_rel']:.1%} → {summary(r1)['rms_rel']:.1%}"
    )
    prev = str(base_doc.get("provenance_note") or "")
    proposed["provenance_note"] = (prev + " | " if prev else "") + note
    return {
        "set_id": s.id,
        "study_kind": kind,
        "knobs": results,
        "correlation": corr,
        "cells": [
            {"row": k[0], "quantity": k[1], "before": float(a), "after": float(b)}
            for k, a, b in zip(keys, r0, r1, strict=True)
        ],
        "before": summary(r0),
        "after": summary(r1),
        "evaluations": n_eval,
        "converged": bool(sol.success),
        "warnings": warnings,
        "proposed_spec": proposed,
        "note": note,
    }
