"""Types and helpers shared by every experiment module.

An experiment module (transformer, induction motor, …) supplies its own equipment spec,
studies, derivation formulas, measurement tables and guide steps; everything here is the
contract between those modules and the experiment-agnostic services (runs, measurements,
comparison, guide, reports).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from vel.engine.circuit import CircuitModel
from vel.engine.mna import ConvergenceError, SingularCircuitError
from vel.engine.netlist import CircuitValidationError
from vel.engine.simulate import MechanicalError, OperatingPoint, operating_point

Status = Literal[
    "success",
    "success_with_warnings",
    "invalid_input",
    "invalid_circuit",
    "solver_failure",
    "convergence_failure",
    "unsupported",
    "constraint_violation",
]


class StudyError(Exception):
    def __init__(self, status: Status, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


@dataclass
class Outcome:
    status: Status
    result: dict[str, Any] | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, Any] | None = None


@dataclass
class Param:
    key: str
    label_he: str
    value: float | None
    unit: str
    formula: str
    method: str  # consistent | manual | analytic
    undefined_reason: str | None = None
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StudyDef:
    kind: str
    title_he: str
    manual_ref: str
    case_model: type[BaseModel]
    default_case: Callable[[Any], dict[str, Any]]
    default_circuit: Callable[[Any, str], Any] | None
    variants: tuple[str, ...] = ()
    editable_circuit: bool = True


@dataclass(frozen=True)
class MCol:
    key: str
    label_he: str
    unit: str  # canonical unit of the column


@dataclass(frozen=True)
class MeasureDef:
    kind: str
    columns: tuple[MCol, ...]
    rows: Literal["free", "fixed"]
    match: str  # column used to pair with simulated points, or "row"
    row_labels: tuple[str, ...] = ()
    condition_keys: tuple[str, ...] = field(default_factory=tuple)


StepKind = Literal["ack", "spec", "simulate", "measure", "compare", "report"]


@dataclass(frozen=True)
class Step:
    id: str
    kind: StepKind
    title_he: str
    body_he: str
    study: str | None = None


def study_steps(items: list[tuple[str, str, str]]) -> list[Step]:
    """prepare → simulate → measure → compare, for each (kind, title, instructions)."""
    out: list[Step] = []
    for kind, title, body in items:
        out += [
            Step(f"{kind}.prepare", "ack", f"{title}: הכנה", body, kind),
            Step(
                f"{kind}.simulate",
                "simulate",
                f"{title}: סימולציה מקדימה",
                "מריצים את הסימולציה כדי לדעת אילו ערכים לצפות לראות.",
                kind,
            ),
            Step(
                f"{kind}.measure",
                "measure",
                f"{title}: הזנת מדידות",
                "מזינים את הערכים שנמדדו במעבדה, כולל יחידות.",
                kind,
            ),
            Step(
                f"{kind}.compare",
                "compare",
                f"{title}: השוואה",
                "משווים את המדידה לסימולציה, בנקודות המדידה עצמן.",
                kind,
            ),
        ]
    return out


SAFETY = (
    "אין לגעת בציוד פגום · עובדים במתחים מסוכנים ובמערכות נעות · מרכיבים את המעגל רק כשמתגי "
    "האספקה מנותקים והווריאקים במינימום · לא משתמשים בחוטים דקים או פגומים · בודקים שתקע "
    "הבננה יושב היטב · אחרי כל הרכבה או שינוי מבקשים בדיקת מדריך ולא מפעילים לפני אישורו · "
    "לא עוברים ערכים נומינליים (מקור: הוראות הבטיחות של המעבדה להמרת אנרגיה)."
)


# --------------------------------------------------------------------------- study helpers


def read(op: OperatingPoint, binding: str) -> float | None:
    inst, _, qty = binding.partition(".")
    if inst not in op.readings:
        raise StudyError(
            "invalid_circuit",
            f"המכשיר {inst} שנדרש לעמודה אינו קיים במעגל",
            {"binding": binding},
        )
    if qty not in op.readings[inst]:
        raise StudyError("invalid_input", f"למכשיר {inst} אין גודל {qty}", {"binding": binding})
    return op.readings[inst][qty]


def with_param(circuit: CircuitModel, cid: str, key: str, value: Any) -> CircuitModel:
    c = copy.deepcopy(circuit)
    try:
        comp = c.component(cid)
    except KeyError as exc:
        raise StudyError("invalid_circuit", f"הרכיב {cid} אינו קיים במעגל") from exc
    comp.params[key] = value
    return c


def solve(circuit: CircuitModel, equipment: BaseModel | None, dc: bool = False) -> OperatingPoint:
    try:
        return operating_point(circuit, equipment, dc=dc)
    except CircuitValidationError as exc:
        raise StudyError("invalid_circuit", str(exc), exc.issues) from exc
    except SingularCircuitError as exc:
        raise StudyError(
            "solver_failure",
            "למעגל אין פתרון יחיד (מטריצה סינגולרית). בדוק קצר על מקור או חלק מעגל ללא הזנה.",
            str(exc),
        ) from exc
    except ConvergenceError as exc:
        raise StudyError(
            "convergence_failure",
            "האיטרציה הלא-ליניארית של ענף המגנוט לא התכנסה",
            {"iterations": exc.iterations, "residual": exc.residual},
        ) from exc
    except MechanicalError as exc:
        raise StudyError(exc.status, exc.message, exc.details) from exc


def undefined_warnings(
    op: OperatingPoint, row: int, bindings: dict[str, str]
) -> list[dict[str, Any]]:
    out = []
    for col, b in bindings.items():
        if b in op.undefined:
            out.append(
                {"code": "undefined_reading", "row": row, "column": col, "message": op.undefined[b]}
            )
    return out


def col(key: str, label: str, unit: str) -> dict[str, str]:
    return {"key": key, "label_he": label, "unit": unit}


def num(v: Any) -> float | None:
    import math

    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


class InputError(Exception):
    """A request that cannot be served from the given data (mapped to HTTP 422 by services)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
