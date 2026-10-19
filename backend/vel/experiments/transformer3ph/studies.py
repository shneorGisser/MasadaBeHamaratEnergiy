"""Study definitions for experiment 1 and their executors.

A study = (circuit, case) → result. The circuit comes from the project (editable), the case
holds the operating conditions and the sweep. Table columns are bound to instrument readings
by `bindings` ("column" → "instrument.quantity"), so the study works on any circuit that
contains the bound instruments, not only on the template.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine.circuit import CircuitModel
from vel.engine.mna import ConvergenceError, SingularCircuitError
from vel.engine.netlist import CircuitValidationError
from vel.engine.simulate import OperatingPoint, operating_point
from vel.experiments.transformer3ph import analysis, templates
from vel.experiments.transformer3ph.spec import TransformerSpec

MODEL_VERSION = "mna-phasor-1.0+xfmr-T-sat-1.0"

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


# --------------------------------------------------------------------------- cases


class NoLoadCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    U_line_values: list[float] = Field(min_length=1, max_length=50)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {
            "U1L": "V1.U",
            "U1ph": "V1ph.U",
            "U2L": "V2.U",
            "U2ph": "V2ph.U",
            "I0": "A.I",
            "P_W": "W.P",
            "pf": "W.pf",
        }
    )

    @field_validator("U_line_values")
    @classmethod
    def _pos(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 for x in v):
            raise ValueError("all voltages must be positive and finite")
        return v


class ShortCircuitCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    I_targets_pu: list[float] = Field(min_length=1, max_length=30)
    max_U_pu: float = Field(default=0.3, gt=0, le=1.0)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {
            "U_k": "V1.U",
            "I1k": "A.I",
            "I2k": "A2.I",
            "P_W": "W.P",
            "pf": "W.pf",
        }
    )

    @field_validator("I_targets_pu")
    @classmethod
    def _pos(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x > 1.5 for x in v):
            raise ValueError("targets must be in (0, 1.5] × I_1n")
        return v


class DcResistanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_targets: list[float] = Field(min_length=1, max_length=10)

    @field_validator("I_targets")
    @classmethod
    def _pos(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x > 50 for x in v):
            raise ValueError("currents must be in (0, 50] A")
        return v


class InsulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_test: float = Field(default=500.0, gt=0, le=5000)


# --------------------------------------------------------------------------- helpers


def _read(op: OperatingPoint, binding: str) -> float | None:
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


def _with_param(circuit: CircuitModel, cid: str, key: str, value: float) -> CircuitModel:
    c = copy.deepcopy(circuit)
    try:
        comp = c.component(cid)
    except KeyError as exc:
        raise StudyError("invalid_circuit", f"רכיב המקור {cid} אינו קיים במעגל") from exc
    comp.params[key] = value
    return c


def _solve(circuit: CircuitModel, spec: TransformerSpec, dc: bool = False) -> OperatingPoint:
    try:
        return operating_point(circuit, spec, dc=dc)
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


def _undefined_warnings(
    op: OperatingPoint, row: int, bindings: dict[str, str]
) -> list[dict[str, Any]]:
    out = []
    for col, b in bindings.items():
        if b in op.undefined:
            out.append(
                {"code": "undefined_reading", "row": row, "column": col, "message": op.undefined[b]}
            )
    return out


def _col(key: str, label: str, unit: str) -> dict[str, str]:
    return {"key": key, "label_he": label, "unit": unit}


# --------------------------------------------------------------------------- studies


def run_no_load(spec: TransformerSpec, circuit: CircuitModel, case: NoLoadCase) -> Outcome:
    U1n = spec.nameplate.U1n
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for i, u in enumerate(case.U_line_values):
        op = _solve(_with_param(circuit, case.source, "U_line", u), spec)
        row: dict[str, Any] = {"point": i + 1, "U_set": u}
        for col, b in case.bindings.items():
            row[col] = _read(op, b)
        row["P0"] = 3 * row["P_W"] if row.get("P_W") is not None else None
        row["iterations"] = op.iterations
        rows.append(row)
        warnings += _undefined_warnings(op, i, case.bindings)
        if u > 1.1 * U1n:
            warnings.append(
                {
                    "code": "saturation_extrapolation",
                    "row": i,
                    "message": "מעל 1.1·Un: עקומת הרוויה היא קירוב פרמטרי; הרמוניות של זרם "
                    "המגנוט וקריאת מכשיר true-RMS אינן ממודלות",
                }
            )
    # parameters at rated voltage
    idx = min(range(len(rows)), key=lambda k: abs(rows[k]["U_set"] - U1n))
    r = rows[idx]
    if abs(r["U_set"] - U1n) > 1e-9 * U1n:
        warnings.append(
            {
                "code": "rated_point_missing",
                "message": f"Un = {U1n:g} V לא נכלל בסוויפ; הפרמטרים חושבו בנקודה הקרובה "
                f"({r['U_set']:g} V)",
            }
        )
    needed = ("U1L", "I0", "P0", "U1ph", "U2ph", "U2L")
    if any(r.get(k) is None for k in needed):
        raise StudyError(
            "invalid_circuit",
            "חסרות קריאות בנקודה הנומינלית לחישוב הפרמטרים",
            {"missing": [k for k in needed if r.get(k) is None]},
        )
    params = analysis.no_load_parameters(r["U1L"], r["I0"], r["P0"], r["U1ph"], r["U2ph"], r["U2L"])
    columns = [
        _col("point", "#", ""),
        _col("U1L", "U1 קווי", "V"),
        _col("U1ph", "U1 פאזי", "V"),
        _col("U2L", "U2 קווי", "V"),
        _col("U2ph", "U2 פאזי", "V"),
        _col("I0", "I0", "A"),
        _col("P_W", "קריאת מד ההספק", "W"),
        _col("P0", "P0 = 3·P", "W"),
        _col("pf", "cos φ0", ""),
    ]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {"id": "readings", "title_he": "טבלה 1.3 — ריקם", "columns": columns, "rows": rows}
            ],
            "parameters": [p.to_json() for p in params],
            "parameters_at": {"row": idx, "U1L": r["U1L"]},
            "curves": [
                {
                    "id": "magnetization",
                    "title_he": "עקומת המגנוט U1 = f(I0)",
                    "x": "I0",
                    "y": "U1L",
                },
                {"id": "p0", "title_he": "הפסדי ריקם P0 = f(U1)", "x": "U1L", "y": "P0"},
            ],
        },
    )


def run_short_circuit(
    spec: TransformerSpec, circuit: CircuitModel, case: ShortCircuitCase
) -> Outcome:
    U1n, I1n = spec.nameplate.U1n, spec.I1n_line
    i_binding = case.bindings["I1k"]
    u_max = case.max_U_pu * U1n
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def current_at(u: float) -> tuple[float, OperatingPoint]:
        op = _solve(_with_param(circuit, case.source, "U_line", u), spec)
        val = _read(op, i_binding)
        if val is None:
            raise StudyError("invalid_circuit", "זרם הקצר אינו מוגדר במעגל")
        return val, op

    for k, tpu in enumerate(case.I_targets_pu):
        target = tpu * I1n
        # Operate the variac: secant iteration on U_line until the primary ammeter reads target.
        u0 = 0.01 * U1n
        i0, op = current_at(u0)
        if i0 <= 0:
            raise StudyError("invalid_circuit", "אין זרם בראשוני — המעגל פתוח?")
        u1 = min(u0 * target / i0, u_max)
        i1, op = current_at(u1)
        for _ in range(40):
            if abs(i1 - target) <= 1e-10 * target:
                break
            if u1 >= u_max and i1 < target:
                raise StudyError(
                    "constraint_violation",
                    f"לא ניתן להגיע ל-{tpu:g}·In במתח עד {case.max_U_pu:g}·Un. "
                    "האם המשני באמת מקוצר?",
                    {"U_max": u_max, "I_reached": i1, "I_target": target},
                )
            slope = (i1 - i0) / (u1 - u0) if u1 != u0 else i1 / u1
            u0, i0 = u1, i1
            u1 = min(max(u1 + (target - i1) / slope, 1e-6), u_max)
            i1, op = current_at(u1)
        else:
            raise StudyError("convergence_failure", "כיוון הווריאק לזרם המטרה לא התכנס")
        row: dict[str, Any] = {"point": k + 1, "I_target_pu": tpu, "U_set": u1}
        for col, b in case.bindings.items():
            row[col] = _read(op, b)
        row["P_k"] = 3 * row["P_W"] if row.get("P_W") is not None else None
        rows.append(row)
        warnings += _undefined_warnings(op, k, case.bindings)
        if tpu > 1.0:
            warnings.append(
                {
                    "code": "above_rated_current",
                    "row": k,
                    "message": "זרם מעל הנומינלי — אסור במעבדה",
                }
            )
    idx = min(range(len(rows)), key=lambda j: abs(rows[j]["I_target_pu"] - 1.0))
    r = rows[idx]
    if r.get("P_k") is None or r.get("U_k") is None:
        raise StudyError("invalid_circuit", "חסרות קריאות לחישוב פרמטרי הקצר")
    params = analysis.short_circuit_parameters(r["U_k"], r["I1k"], r["P_k"], U1n, I1n)
    columns = [
        _col("point", "#", ""),
        _col("U_k", "Uk קווי", "V"),
        _col("I1k", "I1k", "A"),
        _col("I2k", "I2k", "A"),
        _col("P_W", "קריאת מד ההספק", "W"),
        _col("P_k", "Pk = 3·P", "W"),
        _col("pf", "cos φk", ""),
    ]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {"id": "readings", "title_he": "טבלה 1.5 — קצר", "columns": columns, "rows": rows}
            ],
            "parameters": [p.to_json() for p in params],
            "parameters_at": {"row": idx, "I1k": r["I1k"]},
            "curves": [
                {"id": "uk", "title_he": "Uk = f(Ik)", "x": "I1k", "y": "U_k"},
                {"id": "pk", "title_he": "הפסדי נחושת Pk = f(Ik)", "x": "I1k", "y": "P_k"},
            ],
        },
    )


WINDINGS = (
    ("A", "ראשוני A1–A2"),
    ("B", "ראשוני B1–B2"),
    ("C", "ראשוני C1–C2"),
    ("a", "משני a1–a2"),
    ("b", "משני b1–b2"),
    ("c", "משני c1–c2"),
)


def run_dc_resistance(
    spec: TransformerSpec, circuits: dict[str, CircuitModel], case: DcResistanceCase
) -> Outcome:
    rows: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for w, label in WINDINGS:
        circuit = circuits[w]
        r_values = []
        for target in case.I_targets:
            op1 = _solve(_with_param(circuit, "G", "U", 1.0), spec, dc=True)
            i1 = _read(op1, "A.I")
            if not i1:
                raise StudyError("invalid_circuit", f"אין זרם בליפוף {label}")
            u = target / i1  # linear DC circuit: I ∝ U
            op = _solve(_with_param(circuit, "G", "U", u), spec, dc=True)
            i_m, u_m = _read(op, "A.I"), _read(op, "V.U")
            assert i_m is not None and u_m is not None
            r_values.append(u_m / i_m)
            rows.append({"winding": label, "I": i_m, "U": u_m, "R": u_m / i_m})
        summary.append({"winding": label, "R_avg": sum(r_values) / len(r_values)})
    return Outcome(
        status="success",
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 1.2 — התנגדות ליפופים בזרם ישר",
                    "columns": [
                        _col("winding", "ליפוף", ""),
                        _col("I", "I", "A"),
                        _col("U", "U", "V"),
                        _col("R", "R = U/I", "Ω"),
                    ],
                    "rows": rows,
                },
                {
                    "id": "summary",
                    "title_he": "התנגדות ממוצעת לליפוף",
                    "columns": [_col("winding", "ליפוף", ""), _col("R_avg", "R ממוצע", "Ω")],
                    "rows": summary,
                },
            ],
            "parameters": [],
            "curves": [],
        },
        warnings=[
            {
                "code": "no_temperature_model",
                "message": "ההתנגדות אינה תלויה בטמפרטורה במודל (אין תיקון ל-75°C)",
            }
        ],
    )


def run_insulation(spec: TransformerSpec, case: InsulationCase) -> Outcome:
    ins = spec.insulation
    pairs = (
        ("ראשוני – גרעין", ins.primary_core_Mohm),
        ("משני – גרעין", ins.secondary_core_Mohm),
        ("ראשוני – משני", ins.primary_secondary_Mohm),
    )
    rows = [
        {"pair": p, "U_test": case.U_test, "R_ins": r, "I_leak_uA": case.U_test / (r * 1e6) * 1e6}
        for p, r in pairs
    ]
    return Outcome(
        status="success_with_warnings",
        warnings=[
            {
                "code": "parameter_readout",
                "message": "זו אינה סימולציה פיזיקלית: מד הבידוד מציג את פרמטר הבידוד שהוגדר "
                "במודל. לחוברת אין סף קבלה, ולכן לא מוצג עבר/נכשל.",
            }
        ],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 1.1 — התנגדות בידוד",
                    "columns": [
                        _col("pair", "בין", ""),
                        _col("U_test", "מתח בדיקה", "V"),
                        _col("R_ins", "התנגדות בידוד", "MΩ"),
                        _col("I_leak_uA", "זרם זליגה", "µA"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [],
            "curves": [],
        },
    )


# --------------------------------------------------------------------------- registry


@dataclass(frozen=True)
class StudyDef:
    kind: str
    title_he: str
    manual_ref: str
    case_model: type[BaseModel]
    default_case: Callable[[TransformerSpec], dict[str, Any]]
    default_circuit: Callable[[TransformerSpec, str], Any] | None
    variants: tuple[str, ...] = ()
    editable_circuit: bool = True


def _no_load_default(spec: TransformerSpec) -> dict[str, Any]:
    U = spec.nameplate.U1n
    return {"U_line_values": [round(k * U, 6) for k in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2)]}


STUDIES: dict[str, StudyDef] = {
    s.kind: s
    for s in [
        StudyDef(
            "insulation",
            "בדיקת בידוד (מגר)",
            "סעיף 2א, טבלה 1.1",
            InsulationCase,
            lambda spec: {"U_test": 500.0},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "dc_resistance",
            "התנגדות ליפופים בזרם ישר",
            "סעיף 2ב, ציור 1.2, טבלה 1.2",
            DcResistanceCase,
            lambda spec: {"I_targets": [1.0, 2.0, 3.0]},
            lambda spec, variant: {w: templates.dc_winding(w) for w, _ in WINDINGS},
            editable_circuit=False,
        ),
        StudyDef(
            "no_load",
            "ניסוי ריקם",
            "סעיף 3, ציורים 1.3–1.4, טבלה 1.3",
            NoLoadCase,
            _no_load_default,
            lambda spec, variant: templates.no_load(
                spec.nameplate.U1n, spec.nameplate.f_n, "D" if variant == "YD" else "Y"
            ),
            variants=("YY", "YD"),
        ),
        StudyDef(
            "short_circuit",
            "ניסוי קצר",
            "סעיף 4, ציור 1.5, טבלה 1.5",
            ShortCircuitCase,
            lambda spec: {"I_targets_pu": [0.2, 0.4, 0.6, 0.8, 1.0]},
            lambda spec, variant: templates.short_circuit(
                0.05 * spec.nameplate.U1n, spec.nameplate.f_n
            ),
        ),
    ]
}


def execute(
    kind: str, spec: TransformerSpec, circuit_doc: Any, case_doc: dict[str, Any]
) -> Outcome:
    """Run a study. Never raises for engineering failures: they become explicit statuses."""
    sd = STUDIES.get(kind)
    if sd is None:
        return Outcome(status="unsupported", error={"message": f"unknown study {kind}"})
    try:
        case = sd.case_model.model_validate(case_doc)
    except Exception as exc:  # pydantic ValidationError
        return Outcome(
            status="invalid_input", error={"message": "פרמטרי הניסוי שגויים", "details": str(exc)}
        )
    try:
        if kind == "insulation":
            assert isinstance(case, InsulationCase)
            return run_insulation(spec, case)
        if kind == "dc_resistance":
            assert isinstance(case, DcResistanceCase)
            circuits = {k: CircuitModel.model_validate(v) for k, v in circuit_doc.items()}
            return run_dc_resistance(spec, circuits, case)
        circuit = CircuitModel.model_validate(circuit_doc)
        if kind == "no_load":
            assert isinstance(case, NoLoadCase)
            return run_no_load(spec, circuit, case)
        if kind == "short_circuit":
            assert isinstance(case, ShortCircuitCase)
            return run_short_circuit(spec, circuit, case)
    except StudyError as f:
        return Outcome(status=f.status, error={"message": f.message, "details": f.details})
    return Outcome(status="unsupported", error={"message": f"study {kind} has no executor"})
