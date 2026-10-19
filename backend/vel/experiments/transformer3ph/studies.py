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
from vel.experiments.transformer3ph import analysis, derive, templates
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


class LoadCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    load: str = "L"
    load_switch: str = "S2"
    load_kind: Literal["R", "L", "C"] = "R"
    U_line: float | None = Field(default=None, gt=0, description="None → rated U1n")
    I2_targets_pu: list[float] = Field(min_length=1, max_length=20)
    include_no_load: bool = True
    bindings: dict[str, str] = Field(
        default_factory=lambda: {
            "U1L": "V1.U",
            "I1": "A.I",
            "P1_W": "W.P",
            "pf1": "W.pf",
            "U2L": "V2.U",
            "U2ph": "V2ph.U",
            "I2": "A2.I",
            "P2_W": "W2.P",
            "pf2": "W2.pf",
        }
    )

    @field_validator("I2_targets_pu")
    @classmethod
    def _pos(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x > 2.0 for x in v):
            raise ValueError("targets must be in (0, 2.0] × I_2n")
        return v


class VectorGroupCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    U_line: float = Field(default=100.0, gt=0, le=1000)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {"U_aAB": "VaAB.U", "U_aAb": "VaAb.U", "U_Bb": "VBb.U"}
    )


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


def _with_param(circuit: CircuitModel, cid: str, key: str, value: Any) -> CircuitModel:
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
    # derived quantities + parameters: same code path as measured tables
    rows, params, at, dw = derive.no_load(rows, spec)
    warnings += [w for w in dw if w["code"] != "rated_point_missing"]
    if not params:
        raise StudyError("invalid_circuit", "חסרות קריאות בנקודה הנומינלית לחישוב הפרמטרים")
    if abs(rows[at["row"]]["U_set"] - U1n) > 1e-9 * U1n:
        warnings.append(
            {
                "code": "rated_point_missing",
                "message": f"Un = {U1n:g} V לא נכלל בסוויפ; הפרמטרים חושבו בנקודה הקרובה "
                f"({rows[at['row']]['U_set']:g} V)",
            }
        )
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
            "parameters_at": at,
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
    rows, params, at, dw = derive.short_circuit(rows, spec)
    warnings += dw
    if not params:
        raise StudyError("invalid_circuit", "חסרות קריאות לחישוב פרמטרי הקצר")
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
            "parameters_at": at,
            "curves": [
                {"id": "uk", "title_he": "Uk = f(Ik)", "x": "I1k", "y": "U_k"},
                {"id": "pk", "title_he": "הפסדי נחושת Pk = f(Ik)", "x": "I1k", "y": "P_k"},
            ],
        },
    )


def run_load(spec: TransformerSpec, circuit: CircuitModel, case: LoadCase) -> Outcome:
    """Figure 1.7 / table 1.6: constant rated primary voltage, adjust the load (as the student
    adjusts the bank) until the secondary current reaches each target."""
    U = case.U_line or spec.nameplate.U1n
    I2n = spec.I2n_line
    omega = 2 * math.pi * spec.nameplate.f_n
    base = _with_param(circuit, case.source, "U_line", U)
    base = _with_param(base, case.load, "kind", case.load_kind)
    i2_binding = case.bindings["I2"]
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def at(value: float, closed: bool = True) -> OperatingPoint:
        c = _with_param(base, case.load, "value", value)
        c = _with_param(c, case.load_switch, "closed", closed)
        return _solve(c, spec)

    def row_from(op: OperatingPoint, label: str, value: float | None) -> dict[str, Any]:
        r: dict[str, Any] = {"point": len(rows) + 1, "load_setting": label, "load_value": value}
        for col, b in case.bindings.items():
            r[col] = _read(op, b)
        return r

    if case.include_no_load:
        op0 = at(1.0, closed=False)
        rows.append(row_from(op0, "S2 פתוח", None))

    # Initial guess from the rated phase voltage, then secant iteration in log(value).
    U2ph = spec.U2_winding if spec.nameplate.secondary == "Y" else spec.nameplate.U2n / math.sqrt(3)
    for tpu in case.I2_targets_pu:
        target = tpu * I2n
        if case.load_kind == "R":
            guess = U2ph / target
        elif case.load_kind == "L":
            guess = U2ph / (omega * target)
        else:
            guess = target / (omega * U2ph)

        def err(logv: float, target: float = target) -> tuple[float, OperatingPoint]:
            op = at(math.exp(logv))
            val = _read(op, i2_binding)
            if val is None or val <= 0:
                raise StudyError("invalid_circuit", "אין זרם בעומס — המעגל המשני פתוח?")
            return math.log(val / target), op

        x0 = math.log(guess)
        f0, op = err(x0)
        x1 = x0 - f0 if case.load_kind != "C" else x0 + f0
        f1, op = err(x1)
        for _ in range(60):
            if abs(f1) < 1e-11:
                break
            denom = f1 - f0
            if denom == 0:
                break
            x0, f0, x1 = x1, f1, x1 - f1 * (x1 - x0) / denom
            f1, op = err(x1)
        else:
            raise StudyError("convergence_failure", "כיוון העומס לזרם המטרה לא התכנס")
        if abs(f1) > 1e-8:
            raise StudyError("convergence_failure", "כיוון העומס לזרם המטרה לא התכנס")
        unit = {"R": "Ω", "L": "H", "C": "F"}[case.load_kind]
        rows.append(row_from(op, f"{math.exp(x1):.4g} {unit}", math.exp(x1)))
        if tpu > 1.0:
            warnings.append(
                {
                    "code": "above_rated_current",
                    "row": len(rows) - 1,
                    "message": "זרם העומס מעל הנומינלי",
                }
            )
        i1 = rows[-1].get("I1")
        if i1 is not None and i1 > 1.05 * spec.I1n_line:
            warnings.append(
                {
                    "code": "above_rated_current",
                    "row": len(rows) - 1,
                    "message": "זרם הראשוני מעל הנומינלי",
                }
            )
    rows = derive.load(rows, spec)
    title = {"R": "התנגדותי", "L": "השראותי", "C": "קיבולי"}[case.load_kind]
    columns = [
        _col("point", "#", ""),
        _col("load_setting", "כיוון העומס", ""),
        _col("U1L", "U1 קווי", "V"),
        _col("I1", "I1", "A"),
        _col("P1", "P1 = 3·P", "W"),
        _col("pf1", "cos φ1", ""),
        _col("U2L", "U2 קווי", "V"),
        _col("I2", "I2", "A"),
        _col("P2", "P2 = 3·P", "W"),
        _col("pf2", "cos φ2", ""),
        _col("beta", "β = I2/I2n", ""),
        _col("eta", "η = P2/P1", ""),
        _col("dU_pct", "ΔU%", "%"),
    ]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"טבלה 1.6 — עומס {title}",
                    "columns": columns,
                    "rows": rows,
                }
            ],
            "parameters": [],
            "curves": [
                {"id": "external", "title_he": "אופיין חיצוני U2 = f(I2)", "x": "I2", "y": "U2L"},
                {"id": "efficiency", "title_he": "נצילות η = f(β)", "x": "beta", "y": "eta"},
            ],
        },
    )


def clock_from_angles(theta_deg: float) -> list[int]:
    """Cosine law gives the interior angle θ ∈ [0°, 180°]; the clock number is θ/30 or
    (360° − θ)/30 — the measurement alone cannot tell which (the manual asks the student to
    decide from the phasor drawing)."""
    a = round(theta_deg / 30) % 12
    b = round((360 - theta_deg) / 30) % 12
    return sorted({a, b})


def run_vector_group(
    spec: TransformerSpec, circuit: CircuitModel, case: VectorGroupCase
) -> Outcome:
    op = _solve(_with_param(circuit, case.source, "U_line", case.U_line), spec)
    vals = {col: _read(op, b) for col, b in case.bindings.items()}
    warnings = _undefined_warnings(op, 0, case.bindings)
    if any(v is None for v in vals.values()):
        raise StudyError(
            "invalid_circuit",
            "אחד המתחים אינו מוגדר — האם A1 מגושר לנקודה המייצגת את a1?",
            {k: v for k, v in vals.items()},
        )
    aAB, aAb, Bb = vals["U_aAB"], vals["U_aAb"], vals["U_Bb"]
    assert aAB is not None and aAb is not None and Bb is not None
    params = derive.vector_group([vals])
    # simulation-only: true phase displacement from the phasors (not measurable with voltmeters)
    inst_ab, _, _ = case.bindings["U_aAB"].partition(".")
    inst_ab2, _, _ = case.bindings["U_aAb"].partition(".")
    ang_hv = op.readings[inst_ab].get("angle_deg")
    ang_lv = op.readings[inst_ab2].get("angle_deg")
    if ang_hv is not None and ang_lv is not None:
        lag = (ang_hv - ang_lv) % 360
        clock = round(lag / 30) % 12
        params.append(
            analysis.Param(
                "clock_true",
                "מספר השעון (מהפאזורים — סימולציה בלבד)",
                clock,
                "",
                "(∠U_AB − ∠U_ab) / 30°",
                "analytic",
                note=f"פיגור המשני אחרי הראשוני: {lag:.2f}°. לא ניתן למדידה במדי מתח בלבד",
            )
        )
    rows = [{"point": 1, **vals}]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "קבוצת חיבורים — מדידות לשיטת השעון",
                    "columns": [
                        _col("point", "#", ""),
                        _col("U_aAB", "U aA–B1", "V"),
                        _col("U_aAb", "U aA–b1", "V"),
                        _col("U_Bb", "U B1–b1", "V"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [],
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
        StudyDef(
            "load",
            "ניסוי עומס",
            "סעיף 5, ציור 1.7, טבלה 1.6",
            LoadCase,
            lambda spec: {
                "load_kind": "R",
                "I2_targets_pu": [0.25, 0.5, 0.75, 1.0],
                "include_no_load": True,
                "U_line": None,
            },
            lambda spec, variant: templates.load_test(spec.nameplate.U1n, spec.nameplate.f_n),
        ),
        StudyDef(
            "vector_group",
            "קבוצות חיבורים (שיטת השעון)",
            "סעיף 6",
            VectorGroupCase,
            lambda spec: {"U_line": 100.0},
            lambda spec, variant: templates.vector_group(100.0, spec.nameplate.f_n, variant),
            variants=tuple(templates.VG_VARIANTS),
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
        if kind == "load":
            assert isinstance(case, LoadCase)
            return run_load(spec, circuit, case)
        if kind == "vector_group":
            assert isinstance(case, VectorGroupCase)
            return run_vector_group(spec, circuit, case)
    except StudyError as f:
        return Outcome(status=f.status, error={"message": f.message, "details": f.details})
    return Outcome(status="unsupported", error={"message": f"study {kind} has no executor"})
