"""Simulation-run orchestration: snapshot → execute → persist (immutable)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from vel.engine.circuit import CircuitModel
from vel.engine.netlist import validate_structure
from vel.errors import ApiError
from vel.experiments import registry
from vel.experiments.common import Outcome, StudyDef
from vel.orm import Project, SimulationRun


def canonical_json(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def module_of(p: Project) -> registry.ExperimentModule:
    try:
        return registry.get(p.experiment_id)
    except KeyError as exc:
        raise ApiError(422, "unknown_experiment", str(exc)) from exc


def study_def(p: Project, kind: str) -> StudyDef:
    sd = module_of(p).studies.get(kind)
    if sd is None:
        raise ApiError(404, "unknown_study", f"study {kind} does not exist in {p.experiment_id}")
    return sd


def project_spec(p: Project) -> Any:
    return module_of(p).spec(p.spec_json)


def snapshot_spec(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Equipment spec stored in a run snapshot. Runs created before the multi-experiment
    refactor stored it under "transformer"; their stored snapshot (and hash) is never rewritten."""
    doc = snapshot.get("spec", snapshot.get("transformer"))
    assert isinstance(doc, dict)
    return doc


def template_circuit(p: Project, kind: str, variant: str = "") -> Any:
    sd = study_def(p, kind)
    if sd.default_circuit is None:
        return None
    spec = project_spec(p)
    c = sd.default_circuit(spec, variant or (sd.variants[0] if sd.variants else ""))
    if isinstance(c, dict):
        return {k: v.model_dump(mode="json") for k, v in c.items()}
    return c.model_dump(mode="json")


def current_circuit(session: Session, p: Project, kind: str) -> Any:
    """The project's stored circuit for a study; materialized from the template on first use."""
    sd = study_def(p, kind)
    if sd.default_circuit is None:
        return None
    if not sd.editable_circuit:
        return template_circuit(p, kind)
    stored = (p.circuits_json or {}).get(kind)
    if stored is None:
        stored = template_circuit(p, kind)
        p.circuits_json = {**(p.circuits_json or {}), kind: stored}
        session.commit()
    return stored


def save_circuit(session: Session, p: Project, kind: str, doc: dict[str, Any]) -> dict[str, Any]:
    sd = study_def(p, kind)
    if not sd.editable_circuit:
        raise ApiError(409, "not_editable", f"the {kind} circuit is fixed by the procedure")
    try:
        model = CircuitModel.model_validate(doc)
    except Exception as exc:
        raise ApiError(
            422, "invalid_circuit_document", "circuit document is invalid", str(exc)
        ) from exc
    issues = validate_structure(model)
    if issues:
        raise ApiError(422, "invalid_circuit", "circuit has structural errors", issues)
    stored = model.model_dump(mode="json")
    p.circuits_json = {**(p.circuits_json or {}), kind: stored}
    session.commit()
    return stored


def build_snapshot(session: Session, p: Project, kind: str, case: dict[str, Any]) -> dict[str, Any]:
    return {
        "experiment_id": p.experiment_id,
        "experiment_version": p.experiment_version,
        "study_kind": kind,
        "model_version": module_of(p).model_version,
        "spec": p.spec_json,
        "circuit": current_circuit(session, p, kind),
        "case": case,
    }


def execute_snapshot(snapshot: dict[str, Any]) -> Outcome:
    module = registry.get(snapshot.get("experiment_id", "transformer3ph"))
    spec = module.spec(snapshot_spec(snapshot))
    return module.execute(snapshot["study_kind"], spec, snapshot["circuit"], snapshot["case"])


def create_run(
    session: Session, p: Project, kind: str, case: dict[str, Any], label: str
) -> SimulationRun:
    study_def(p, kind)
    snapshot = build_snapshot(session, p, kind, case)
    outcome = execute_snapshot(snapshot)
    run = SimulationRun(
        project_id=p.id,
        study_kind=kind,
        label=label,
        input_snapshot=snapshot,
        input_hash=sha256(snapshot),
        model_version=snapshot["model_version"],
        status=outcome.status,
        warnings=outcome.warnings,
        error=outcome.error,
        result=outcome.result,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def reproduce(run: SimulationRun) -> dict[str, Any]:
    outcome = execute_snapshot(run.input_snapshot)
    original = {"status": run.status, "result": run.result, "warnings": run.warnings}
    now = {"status": outcome.status, "result": outcome.result, "warnings": outcome.warnings}
    # Round-trip through JSON so stored and fresh values are compared in the same form.
    now = json.loads(canonical_json(now))
    return {
        "identical": canonical_json(original) == canonical_json(now),
        "input_hash_matches": sha256(run.input_snapshot) == run.input_hash,
        "model_version_then": run.model_version,
        "model_version_now": registry.get(
            run.input_snapshot.get("experiment_id", "transformer3ph")
        ).model_version,
        "result_hash_then": sha256(original),
        "result_hash_now": sha256(now),
    }


LIVE_OVERRIDABLE = {
    "source3": {"U_line"},
    "source_dc": {"U"},
    "switch3": {"closed"},
    "load3": {"value", "kind"},
    "motor3": {"M_load", "locked"},
    "syncmachine3": {"I_f", "n_drive", "P_shaft"},
    "woundmotor3": {"M_load", "locked", "angle", "speed_mode", "n_set"},
    "dcmachine": {"M_load", "speed_mode", "n_set"},
    "resistor": {"R"},  # rheostats: field, extra armature resistance, load
}


def live_point(
    session: Session, p: Project, kind: str, overrides: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    from vel.engine.mna import ConvergenceError, SingularCircuitError
    from vel.engine.netlist import CircuitValidationError
    from vel.engine.simulate import MechanicalError, operating_point

    sd = study_def(p, kind)
    if not sd.editable_circuit:
        raise ApiError(409, "not_editable", "live operating point needs an editable circuit")
    doc = current_circuit(session, p, kind)
    circuit = CircuitModel.model_validate(doc)
    for cid, params in overrides.items():
        try:
            comp = circuit.component(cid)
        except KeyError as exc:
            raise ApiError(422, "unknown_component", f"no component {cid}") from exc
        allowed = LIVE_OVERRIDABLE.get(comp.type, set())
        bad = set(params) - allowed
        if bad:
            raise ApiError(422, "not_overridable", f"{cid}: cannot override {sorted(bad)}")
        comp.params.update(params)
    spec = project_spec(p)
    base = {
        "source": "simulation",
        "persisted": False,
        "model_version": module_of(p).model_version,
        "overrides": overrides,
    }
    try:
        types = {c.type for c in circuit.components}
        dc = "source3" not in types and bool(types & {"source_dc", "dcmachine"})
        op = operating_point(circuit, spec, dc=dc, on_stall="stall")
    except CircuitValidationError as exc:
        return {
            **base,
            "status": "invalid_circuit",
            "error": {"message": str(exc), "details": exc.issues},
        }
    except SingularCircuitError as exc:
        return {**base, "status": "solver_failure", "error": {"message": str(exc)}}
    except ConvergenceError as exc:
        return {**base, "status": "convergence_failure", "error": {"message": str(exc)}}
    except MechanicalError as exc:
        return {**base, "status": exc.status, "error": {"message": exc.message}}
    warnings = [
        {"code": "undefined_reading", "message": f"{k}: {v}"} for k, v in op.undefined.items()
    ] + op.warnings
    return {
        **base,
        "status": "success_with_warnings" if warnings else "success",
        "readings": op.readings,
        "warnings": warnings,
        "internals": {k: v for k, v in op.internals.items() if not k.startswith("_")},
        "iterations": op.iterations,
    }
