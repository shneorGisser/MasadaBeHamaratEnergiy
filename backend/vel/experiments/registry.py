"""Registry of experiment modules.

An experiment module provides: metadata, a default equipment specification, and (from S1)
study templates + analysis. New experiments register here without touching core code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from vel.experiments.transformer3ph.spec import TransformerSpec, assumed_lab_transformer


@dataclass(frozen=True)
class ExperimentModule:
    id: str
    version: int
    title_he: str
    summary_he: str
    manual_ref: str
    spec_model: type[BaseModel]
    default_spec: Callable[[], BaseModel]
    studies: list[dict[str, Any]] = field(default_factory=list)


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


register(
    ExperimentModule(
        id="transformer3ph",
        version=1,
        title_he="ניסוי 1: בדיקת שנאי תלת-פזי",
        summary_he=("בידוד, התנגדות ליפופים, ריקם, קצר, עומס R/L/C וקבוצות חיבורים (שיטת השעון)"),
        manual_ref="חוברת המעבדה בהמרת אנרגיה, ניסוי 1",
        spec_model=TransformerSpec,
        default_spec=assumed_lab_transformer,
    )
)
