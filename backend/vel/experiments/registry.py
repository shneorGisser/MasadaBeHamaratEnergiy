"""Registry of experiment modules.

An experiment module is everything that is specific to one lab experiment: the equipment
specification, study definitions and their executors, the derivation formulas (shared by
simulated and measured tables), the measurement tables, the guide and the report texts.
The services (runs, measurements, comparison, guide, reports, backup) only talk to this
interface, so adding an experiment means registering a module — not editing the services.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from vel.experiments.common import MeasureDef, Outcome, Step, StudyDef

Rows = list[dict[str, Any]]


@dataclass(frozen=True)
class ExperimentModule:
    id: str
    version: int
    title_he: str
    summary_he: str
    manual_ref: str
    equipment_he: str  # "השנאי", "המנוע" — used in generic UI/report texts
    spec_model: type[BaseModel]
    default_spec: Callable[[], BaseModel]
    presets: Mapping[str, tuple[str, Callable[[], BaseModel]]]
    model_version: str
    studies: Mapping[str, StudyDef]
    execute: Callable[[str, Any, Any, dict[str, Any]], Outcome]
    measure_defs: Mapping[str, MeasureDef]
    derived_columns: Mapping[str, list[dict[str, str]]]
    # measured/simulated table → {"rows", "parameters", "parameters_at", "warnings", ...}
    analyse: Callable[[str, Rows, Any], dict[str, Any]]
    # measured table → study case that simulates exactly those operating points
    matching_case: Callable[[str, dict[str, Any], Rows, Any], dict[str, Any]]
    # model (equivalent-circuit) values of the extracted parameters, by parameter key
    theory_values: Callable[[Any], dict[str, float]]
    # extra, read-only columns for a measurement row (e.g. which winding a row belongs to)
    row_extra: Callable[[str, int], dict[str, Any]]
    guide_steps: Callable[[], list[Step]]
    # derived nameplate quantities shown in the UI (rated currents, ratios, speeds)
    derived_spec: Callable[[Any], dict[str, float]]
    # texts and spec table for the report's opening sections
    report_info: Callable[[Any], dict[str, Any]]

    def spec(self, doc: dict[str, Any]) -> Any:
        return self.spec_model.model_validate(doc)


_REGISTRY: dict[str, ExperimentModule] = {}


def register(module: ExperimentModule) -> None:
    if module.id in _REGISTRY:
        raise ValueError(f"experiment {module.id!r} already registered")
    _REGISTRY[module.id] = module


def get(experiment_id: str) -> ExperimentModule:
    try:
        return _REGISTRY[experiment_id]
    except KeyError as exc:
        raise KeyError(f"unknown experiment {experiment_id!r}") from exc


def all_modules() -> list[ExperimentModule]:
    return list(_REGISTRY.values())


def _register_builtin() -> None:
    from vel.experiments.dc_machine import modules as dc
    from vel.experiments.induction_motor import module as motor
    from vel.experiments.installation import module as installation
    from vel.experiments.synchronous import module as synchronous
    from vel.experiments.transformer3ph import module as transformer
    from vel.experiments.wound_rotor import module as wound

    register(transformer.MODULE)
    register(motor.MODULE)
    register(synchronous.MODULE)
    register(wound.MODULE)
    register(dc.MOTOR_MODULE)
    register(dc.GEN_MODULE)
    register(installation.MODULE)


_register_builtin()
