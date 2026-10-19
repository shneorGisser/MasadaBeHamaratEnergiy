"""Simulation-run orchestration: snapshot → execute → persist (immutable)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from vel.engine.circuit import CircuitModel
from vel.engine.netlist import validate_structure
from vel.errors import ApiError
from vel.experiments.transformer3ph import studies
from vel.experiments.transformer3ph.spec import TransformerSpec
from vel.orm import Project, SimulationRun


def canonical_json(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def study_def(kind: str) -> studies.StudyDef:
    sd = studies.STUDIES.get(kind)
    if sd is None:
        raise ApiError(404, "unknown_study", f"study {kind} does not exist")
    return sd


def project_spec(p: Project) -> TransformerSpec:
    return TransformerSpec.model_validate(p.transformer_json)


def template_circuit(p: Project, kind: str, variant: str = "") -> Any:
    sd = study_def(kind)
    if sd.default_circuit is None:
        return None
    spec = project_spec(p)
    c = sd.default_circuit(spec, variant or (sd.variants[0] if sd.variants else ""))
    if isinstance(c, dict):
        return {k: v.model_dump(mode="json") for k, v in c.items()}
    return c.model_dump(mode="json")


def current_circuit(session: Session, p: Project, kind: str) -> Any:
    """The project's stored circuit for a study; materialized from the template on first use."""
    sd = study_def(kind)
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
    sd = study_def(kind)
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
        "model_version": studies.MODEL_VERSION,
        "transformer": p.transformer_json,
        "circuit": current_circuit(session, p, kind),
        "case": case,
    }


def execute_snapshot(snapshot: dict[str, Any]) -> studies.Outcome:
    spec = TransformerSpec.model_validate(snapshot["transformer"])
    return studies.execute(snapshot["study_kind"], spec, snapshot["circuit"], snapshot["case"])


def create_run(
    session: Session, p: Project, kind: str, case: dict[str, Any], label: str
) -> SimulationRun:
    study_def(kind)
    snapshot = build_snapshot(session, p, kind, case)
    outcome = execute_snapshot(snapshot)
    run = SimulationRun(
        project_id=p.id,
        study_kind=kind,
        label=label,
        input_snapshot=snapshot,
        input_hash=sha256(snapshot),
        model_version=studies.MODEL_VERSION,
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
        "model_version_now": studies.MODEL_VERSION,
        "result_hash_then": sha256(original),
        "result_hash_now": sha256(now),
    }
