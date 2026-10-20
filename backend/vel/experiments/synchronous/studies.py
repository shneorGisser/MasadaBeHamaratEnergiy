"""Study definitions for experiment 3 (synchronous machine) and their executors."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine.circuit import CircuitModel
from vel.engine.simulate import OperatingPoint
from vel.experiments.common import (
    Outcome,
    StudyDef,
    StudyError,
    col,
    read,
    solve,
    undefined_warnings,
    with_param,
)
from vel.experiments.synchronous import derive, templates
from vel.experiments.synchronous.spec import SyncSpec
from vel.experiments.synchronous.templates import FAULTS, WINDINGS
from vel.experiments.synchronous.transient import (
    TD01,
    TD02,
    TQ02,
    SuddenScCase,
    SynchronizeCase,
    run_sudden_sc,
    run_synchronize,
)

MODEL_VERSION = "mna-phasor-1.1+sm-mmf-seq-1.0"
MACHINE = "G"
IF_MAX = 50.0


def _status(w: list[dict[str, Any]]) -> Literal["success", "success_with_warnings"]:
    return "success_with_warnings" if w else "success"


def _nonneg_list(v: list[float], hi: float, what: str) -> list[float]:
    if any((not math.isfinite(x)) or x < 0 or x > hi for x in v):
        raise ValueError(f"{what} must be in [0, {hi:g}]")
    return v


# --------------------------------------------------------------------------- cases


class InsulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_test: float = Field(default=500.0, gt=0, le=5000)


class DcResistanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_values: list[float] = Field(min_length=1, max_length=10, description="supply settings [V]")

    @field_validator("U_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x > 25 for x in v):
            raise ValueError("the DC supply of fig. 6-2 is 0–25 V")
        return v


class OpenCircuitCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    If_values: list[float] = Field(min_length=1, max_length=40)
    n_drive: float | None = Field(default=None, gt=0, le=1e5, description="None → n_sync")
    bindings: dict[str, str] = Field(default_factory=lambda: {"Ef": "V1.U", "f": "G.f"})

    @field_validator("If_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _nonneg_list(v, IF_MAX, "field currents")


class ShortCircuitCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    If_values: list[float] = Field(min_length=1, max_length=20)
    n_drive: float | None = Field(default=None, gt=0, le=1e5)

    @field_validator("If_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _nonneg_list(v, IF_MAX, "field currents")


class LoadCharCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    load_kind: Literal["R", "L", "C"] = "R"
    U0: float = Field(gt=0, le=1e5, description="no-load line voltage set by I_f [V]")
    I_targets: list[float] = Field(min_length=1, max_length=20, description="load current [A]")
    include_no_load: bool = True
    n_drive: float | None = Field(default=None, gt=0, le=1e5)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {"U1": "V1.U", "I1": "A.I", "P_W": "W.P", "pf": "W.pf"}
    )

    @field_validator("I_targets")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x > 1e4 for x in v):
            raise ValueError("load currents must be positive")
        return v


class RegulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_ref: float = Field(gt=0, le=1e5, description="terminal line voltage held constant [V]")
    I_targets: list[float] = Field(min_length=1, max_length=20)
    n_drive: float | None = Field(default=None, gt=0, le=1e5)
    bindings: dict[str, str] = Field(default_factory=lambda: {"U1": "V1.U", "I1": "A.I"})

    @field_validator("I_targets")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _nonneg_list(v, 1e4, "currents")


class ZpfCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_const: float | None = Field(default=None, gt=0, le=1e4, description="None → I_n")
    If_values: list[float] = Field(min_length=1, max_length=20)
    n_drive: float | None = Field(default=None, gt=0, le=1e5)
    bindings: dict[str, str] = Field(default_factory=lambda: {"U1": "V1.U", "I1": "A.I"})

    @field_validator("If_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _nonneg_list(v, IF_MAX, "field currents")


class VPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    P: float = Field(ge=-1e7, le=1e7, description="shaft power, + motor [W]")
    If: float = Field(ge=0, le=IF_MAX)


class VCurveCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5, description="None → U_n")
    points: list[VPoint] = Field(min_length=1, max_length=60)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {"U": "V1.U", "Ia": "A.I", "P_W": "W.P", "Q_W": "W.Q", "pf": "W.pf"}
    )


# --------------------------------------------------------------------------- helpers


def _n(spec: SyncSpec, n: float | None) -> float:
    return n if n is not None else spec.nameplate.n_sync


def _gen_base(spec: SyncSpec, circuit: CircuitModel, n: float | None) -> CircuitModel:
    return with_param(circuit, MACHINE, "n_drive", _n(spec, n))


def _at(c: CircuitModel, spec: SyncSpec, **params: Any) -> OperatingPoint:
    for k, v in params.items():
        cid, _, key = k.partition("__")
        c = with_param(c, cid, key, v)
    return solve(c, spec)


def _secant(
    fn: Any, x0: float, x1: float, target: float, lo: float, hi: float, what: str
) -> tuple[float, OperatingPoint]:
    """x in [lo, hi] with fn(x)[0] = target (fn monotone near the root): clamped secant."""
    tol = 1e-10 * max(1.0, abs(target))
    f0 = fn(x0)[0] - target
    v1, op = fn(x1)
    f1 = v1 - target
    for _ in range(100):
        if abs(f1) <= tol:
            return x1, op
        if f1 == f0:
            break
        x2 = min(max(x1 - f1 * (x1 - x0) / (f1 - f0), lo), hi)
        if x2 == x1:
            break
        x0, f0 = x1, f1
        x1 = x2
        v1, op = fn(x1)
        f1 = v1 - target
    raise StudyError(
        "constraint_violation",
        f"לא ניתן להגיע ל{what} בתחום המותר",
        {"target": target, "reached": f1 + target},
    )


# --------------------------------------------------------------------------- studies


def run_insulation(spec: SyncSpec, case: InsulationCase) -> Outcome:
    ins = spec.insulation
    pairs = (
        ("סטטור U – מארז", ins.U_frame_Mohm),
        ("סטטור V – מארז", ins.V_frame_Mohm),
        ("סטטור W – מארז", ins.W_frame_Mohm),
        ("רוטור F1–F2 – מארז", ins.F_frame_Mohm),
        ("סטטור – רוטור (U1–F1)", ins.stator_rotor_Mohm),
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
                "message": "זו אינה סימולציה פיזיקלית: מד הבידוד מציג את פרמטר הבידוד "
                "שהוגדר במודל.",
            }
        ],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 6.1 — התנגדות בידוד",
                    "columns": [
                        col("pair", "בין", ""),
                        col("U_test", "מתח בדיקה", "V"),
                        col("R_ins", "התנגדות בידוד", "MΩ"),
                        col("I_leak_uA", "זרם זליגה", "µA"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [],
            "curves": [],
        },
    )


def run_dc_resistance(
    spec: SyncSpec, circuits: dict[str, CircuitModel], case: DcResistanceCase
) -> Outcome:
    rows, summary = [], []
    for w, label in WINDINGS:
        vals = []
        for u in case.U_values:
            op = solve(with_param(circuits[w], "P", "U", u), spec, dc=True)
            i_m, u_m = read(op, "A.I"), read(op, "V.U")
            assert i_m is not None and u_m is not None
            vals.append(u_m / i_m)
            rows.append({"winding": label, "U": u_m, "I": i_m, "R": u_m / i_m})
        summary.append({"winding": label, "R_avg": sum(vals) / len(vals)})
    return Outcome(
        status="success_with_warnings",
        warnings=[
            {"code": "no_temperature_model", "message": "ההתנגדות אינה תלויה בטמפרטורה במודל"}
        ],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 6.2 — התנגדות ליפופים בזרם ישר",
                    "columns": [
                        col("winding", "ליפוף", ""),
                        col("U", "U", "V"),
                        col("I", "I", "A"),
                        col("R", "R = U/I", "Ω"),
                    ],
                    "rows": rows,
                },
                {
                    "id": "summary",
                    "title_he": "התנגדות ממוצעת",
                    "columns": [col("winding", "ליפוף", ""), col("R_avg", "R ממוצע", "Ω")],
                    "rows": summary,
                },
            ],
            "parameters": [],
            "curves": [],
        },
    )


HYST = (
    "עקומת הריקם במודל חד-ערכית (F_h = 0): ההיסטרזיס אינו ממודל, ולכן בסימולציה Ef↑ = Ef↓. "
    "במדידות 2025 ו-2026 ההפרש בין הענפים (±2–6 V, בשני הכיוונים) אינו גדול מפיזור הקריאה, "
    "ולכן לא הותאם לו פרמטר. השטף השיורי ממודל כהיסט קבוע בזרם העירור."
)


def run_open_circuit(spec: SyncSpec, circuit: CircuitModel, case: OpenCircuitCase) -> Outcome:
    base = with_param(_gen_base(spec, circuit, case.n_drive), "S", "closed", False)
    rows: list[dict[str, Any]] = []
    hyst = spec.occ.F_h > 0
    warnings: list[dict[str, Any]] = [] if hyst else [{"code": "no_hysteresis", "message": HYST}]
    i_max = max(case.If_values) if case.If_values else 0.0
    for k, i_f in enumerate(case.If_values):
        op = _at(base, spec, G__I_f=i_f)
        ef = read(op, case.bindings["Ef"])
        ef_down = ef
        if hyst:
            d = spec.occ.descending_shift(max(i_f, 0.0), i_max)
            down = spec.model_copy(
                update={"occ": spec.occ.model_copy(update={"F_res": spec.occ.F_res + d})}
            )
            ef_down = read(_at(base, down, G__I_f=i_f), case.bindings["Ef"])
        rows.append(
            {
                "point": k + 1,
                "If": i_f,
                "Ef": ef,
                "Ef_up": ef,
                "Ef_down": ef_down,
                "f": read(op, case.bindings["f"]),
            }
        )
        warnings += undefined_warnings(op, k, case.bindings)
    rows, params, w = derive.open_circuit(rows, spec)
    warnings += w
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 6.3 — אופיין ריקם Ef = f(If)",
                    "columns": [
                        col("point", "#", ""),
                        col("If", "If", "A"),
                        col("Ef", "Ef (U1 קווי)", "V"),
                        col("f", "f", "Hz"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [{"id": "occ", "title_he": "אופיין ריקם Ef = f(If)", "x": "If", "y": "Ef"}],
        },
    )


def run_short_circuit(
    spec: SyncSpec, circuits: dict[str, CircuitModel], case: ShortCircuitCase
) -> Outcome:
    rows: list[dict[str, Any]] = []
    for k, i_f in enumerate(case.If_values):
        row: dict[str, Any] = {"point": k + 1, "If": i_f}
        for fault, _ in FAULTS:
            op = _at(_gen_base(spec, circuits[fault], case.n_drive), spec, G__I_f=i_f)
            row[f"Ik{fault}"] = read(op, "A.I")
        rows.append(row)
    rows, params, warnings = derive.short_circuit(rows, spec)
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 6.4 — אופייני קצר Ik = f(If)",
                    "columns": [
                        col("point", "#", ""),
                        col("If", "If", "A"),
                        col("Ik3", "Ik(3)", "A"),
                        col("Ik2", "Ik(2)", "A"),
                        col("Ik1", "Ik(1)", "A"),
                        col("r2", "Ik(2)/Ik(3)", ""),
                        col("r1", "Ik(1)/Ik(3)", ""),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "sc",
                    "title_he": "אופייני קצר: Ik(3), Ik(2), Ik(1)",
                    "x": "If",
                    "y": "Ik3",
                    "y2": "Ik2",
                    "y3": "Ik1",
                }
            ],
        },
    )


def _if_for_noload(spec: SyncSpec, base: CircuitModel, u0: float, bind: str) -> float:
    open_c = with_param(base, "S", "closed", False)

    def u_of(i_f: float) -> tuple[float, OperatingPoint]:
        op = _at(open_c, spec, G__I_f=i_f)
        v = read(op, bind)
        return float(v or 0.0), op

    i_f, _ = _secant(u_of, 0.5, 1.0, u0, 0.0, IF_MAX, f"מתח ריקם {u0:g} V")
    return i_f


def run_load_characteristic(spec: SyncSpec, circuit: CircuitModel, case: LoadCharCase) -> Outcome:
    base = with_param(_gen_base(spec, circuit, case.n_drive), "L", "kind", case.load_kind)
    i_f = _if_for_noload(spec, base, case.U0, case.bindings["U1"])
    base = with_param(base, MACHINE, "I_f", i_f)
    omega = 2 * math.pi * spec.nameplate.f_n * _n(spec, case.n_drive) / spec.nameplate.n_sync
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def row_of(op: OperatingPoint, label: str) -> dict[str, Any]:
        r: dict[str, Any] = {"point": len(rows) + 1, "load_setting": label, "If": i_f}
        for c_, b_ in case.bindings.items():
            r[c_] = read(op, b_)
        return r

    if case.include_no_load:
        rows.append(row_of(_at(base, spec, S__closed=False), "S3 פתוח"))
    uph = case.U0 / math.sqrt(3)
    for target in case.I_targets:
        guess = {"R": uph / target, "L": uph / (omega * target), "C": target / (omega * uph)}[
            case.load_kind
        ]

        def i_of(logv: float, target: float = target) -> tuple[float, OperatingPoint]:
            op = _at(base, spec, L__value=math.exp(logv))
            v = read(op, case.bindings["I1"]) or 0.0
            sign = 1.0 if case.load_kind == "C" else -1.0  # C: larger value → more current
            return sign * math.log(max(v, 1e-30) / target), op

        try:
            x, op = _secant(
                i_of,
                math.log(guess),
                math.log(guess) + 0.1,
                0.0,
                math.log(1e-9),
                math.log(1e8),
                f"זרם עומס {target:g} A",
            )
        except StudyError as exc:
            warnings.append(
                {
                    "code": "unreachable",
                    "row": len(rows),
                    "message": f"{target:g} A: {exc.message} — בעירור הזה המחולל אינו יכול לספק "
                    "זרם כזה לעומס (מוגבל בעיקר ע״י Xs)",
                }
            )
            continue
        unit = {"R": "Ω", "L": "H", "C": "F"}[case.load_kind]
        rows.append(row_of(op, f"{math.exp(x):.4g} {unit}"))
        warnings += undefined_warnings(op, len(rows) - 1, case.bindings)
        if target > 1.05 * spec.nameplate.I_n:
            warnings.append(
                {"code": "above_rated_current", "row": len(rows) - 1, "message": "זרם מעל הנומינלי"}
            )
        if case.load_kind == "C" and (rows[-1].get("U1") or 0) > 1.3 * case.U0:
            warnings.append(
                {
                    "code": "self_excitation",
                    "row": len(rows) - 1,
                    "message": "עלייה חדה במתח בעומס קיבולי (קרוב לעירור עצמי) — "
                    "החוברת אוסרת לעבור 300 V",
                }
            )
    rows = derive.load(rows, spec)
    title = {"R": "התנגדותי (φ = 0)", "L": "השראותי (φ = +90°)", "C": "קיבולי (φ = −90°)"}
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"טבלה 6.5 — אופיין עומס, {title[case.load_kind]}",
                    "columns": [
                        col("point", "#", ""),
                        col("load_setting", "עומס", ""),
                        col("I1", "I1", "A"),
                        col("U1", "U1", "V"),
                        col("P", "P = 3·P_W", "W"),
                        col("pf", "cos φ", ""),
                        col("If", "If (קבוע)", "A"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [
                {
                    "key": "If_set",
                    "label_he": "If שכוון לריקם",
                    "value": i_f,
                    "unit": "A",
                    "formula": f"Ef(If) = {case.U0:g} V",
                    "method": "consistent",
                    "undefined_reason": None,
                    "note": "",
                }
            ],
            "curves": [{"id": "ext", "title_he": "אופיין עומס U1 = f(I1)", "x": "I1", "y": "U1"}],
        },
    )


def run_regulation(spec: SyncSpec, circuit: CircuitModel, case: RegulationCase) -> Outcome:
    base = with_param(_gen_base(spec, circuit, case.n_drive), "L", "kind", "R")
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    uph = case.U_ref / math.sqrt(3)
    for target in case.I_targets:
        c = base if target > 0 else with_param(base, "S", "closed", False)
        if target > 0:
            c = with_param(c, "L", "value", uph / target)

        def u_of(i_f: float, c: CircuitModel = c) -> tuple[float, OperatingPoint]:
            op = _at(c, spec, G__I_f=i_f)
            return float(read(op, case.bindings["U1"]) or 0.0), op

        try:
            i_f, op = _secant(u_of, 0.8, 1.2, case.U_ref, 0.0, IF_MAX, f"מתח {case.U_ref:g} V")
        except StudyError as exc:
            warnings.append({"code": "unreachable", "row": len(rows), "message": exc.message})
            continue
        rows.append(
            {
                "point": len(rows) + 1,
                "I1": read(op, case.bindings["I1"]),
                "If": i_f,
                "U1": read(op, case.bindings["U1"]),
            }
        )
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"טבלה 6.6 — אופיין ויסות (U1 = {case.U_ref:g} V, עומס התנגדותי)",
                    "columns": [
                        col("point", "#", ""),
                        col("I1", "Ia", "A"),
                        col("If", "If", "A"),
                        col("U1", "U1", "V"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [],
            "curves": [{"id": "reg", "title_he": "אופיין ויסות If = f(Ia)", "x": "I1", "y": "If"}],
        },
    )


def run_zpf(spec: SyncSpec, circuit: CircuitModel, case: ZpfCase) -> Outcome:
    i_c = case.I_const or spec.nameplate.I_n
    base = with_param(_gen_base(spec, circuit, case.n_drive), "L", "kind", "L")
    omega = 2 * math.pi * spec.nameplate.f_n * _n(spec, case.n_drive) / spec.nameplate.n_sync
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for i_f in case.If_values:
        c = with_param(base, MACHINE, "I_f", i_f)
        # current with the terminals shorted is the most this I_f can drive into any inductor
        guess_l = max(spec.U_winding / (omega * i_c), 1e-6)

        def i_of(logl: float, c: CircuitModel = c) -> tuple[float, OperatingPoint]:
            op = _at(c, spec, L__value=math.exp(logl))
            return -math.log(max(read(op, case.bindings["I1"]) or 0.0, 1e-30) / i_c), op

        try:
            _, op = _secant(
                i_of, math.log(guess_l), math.log(guess_l) + 0.1, 0.0, -40, 20, f"זרם {i_c:g} A"
            )
        except StudyError:
            warnings.append(
                {
                    "code": "unreachable",
                    "row": len(rows),
                    "message": f"If = {i_f:g} A: אי אפשר להזרים {i_c:g} A גם בקצר — "
                    "נקודת הסיום של האופיין",
                }
            )
            continue
        rows.append(
            {
                "point": len(rows) + 1,
                "If": i_f,
                "U1": read(op, case.bindings["U1"]),
                "I1": read(op, case.bindings["I1"]),
                "Ef_noload": op.readings[MACHINE]["Ef_noload"],
            }
        )
    rows, params = derive.zpf(rows, spec, i_c)
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"אופיין הגבי (I1 = {i_c:g} A קבוע)",
                    "columns": [
                        col("point", "#", ""),
                        col("If", "If", "A"),
                        col("U1", "U1", "V"),
                        col("I1", "I1", "A"),
                        col("Ef_noload", "Ef בריקם באותו If", "V"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "zpf",
                    "title_he": "אופיין הגבי מול אופיין ריקם",
                    "x": "If",
                    "y": "U1",
                    "y2": "Ef_noload",
                }
            ],
        },
    )


def run_v_curves(spec: SyncSpec, circuit: CircuitModel, case: VCurveCase) -> Outcome:
    u = case.U_line or spec.nameplate.U_n
    base = with_param(circuit, "N", "U_line", u)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for k, pt in enumerate(case.points):
        try:
            op = _at(base, spec, G__I_f=pt.If, G__P_shaft=pt.P)
        except StudyError as exc:
            if exc.status != "constraint_violation":
                raise
            rows.append({"point": k + 1, "P_set": pt.P, "If": pt.If, "state": "יצא מסנכרון"})
            warnings.append(
                {
                    "code": "out_of_step",
                    "row": k,
                    "message": f"P = {pt.P:g} W, If = {pt.If:g} A: {exc.message}",
                }
            )
            continue
        r: dict[str, Any] = {"point": k + 1, "P_set": pt.P, "If": pt.If, "state": "סינכרוני"}
        for c_, b_ in case.bindings.items():
            r[c_] = read(op, b_)
        q = r.get("Q_W")
        r["char"] = "—" if q is None or abs(q) < 1e-9 else ("השראי" if q > 0 else "קיבולי")
        r["delta_deg"] = op.readings[MACHINE].get("delta_deg")
        rows.append(r)
    rows, params = derive.v_curves(rows)
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 6.7 — אופייני V (מנוע סינכרוני)",
                    "columns": [
                        col("point", "#", ""),
                        col("P_set", "P בציר", "W"),
                        col("If", "If", "A"),
                        col("Ia", "Ia", "A"),
                        col("pf", "cos φ", ""),
                        col("char", "אופי", ""),
                        col("P1", "P1 = 3·P_W", "W"),
                        col("delta_deg", "זווית עומס δ", "°"),
                        col("state", "מצב", ""),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "v",
                    "title_he": "אופייני V: Ia = f(If)",
                    "x": "If",
                    "y": "Ia",
                    "group": "P_set",
                },
                {"id": "pf", "title_he": "cos φ = f(If)", "x": "If", "y": "pf", "group": "P_set"},
            ],
        },
    )


# --------------------------------------------------------------------------- registry


def _c(spec: SyncSpec) -> Literal["Y", "D"]:
    return spec.nameplate.connection


def _gen(spec: SyncSpec, **kw: Any) -> CircuitModel:
    return templates.generator(1.0, spec.nameplate.n_sync, _c(spec), **kw)


STUDIES: dict[str, StudyDef] = {
    s.kind: s
    for s in [
        StudyDef(
            "insulation",
            "בדיקת בידוד (מגר)",
            "ציור 6-1, טבלה 6.1",
            InsulationCase,
            lambda spec: {"U_test": 500.0},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "dc_resistance",
            "התנגדות ליפופים בזרם ישר",
            "ציור 6-2, טבלה 6.2",
            DcResistanceCase,
            lambda spec: {"U_values": [8.0, 16.0, 20.0]},
            lambda spec, v: {w: templates.dc_winding(w) for w, _ in WINDINGS},
            editable_circuit=False,
        ),
        StudyDef(
            "open_circuit",
            "אופיין ריקם",
            "ציור 6-3, טבלה 6.3",
            OpenCircuitCase,
            lambda spec: {
                "If_values": [0, 0.25, 0.5, 0.7, 0.97, 1.22, 1.47, 1.73, 1.96, 2.25, 2.5],
                "n_drive": None,
            },
            lambda spec, v: _gen(spec, closed=False),
        ),
        StudyDef(
            "short_circuit",
            "אופייני קצר (תלת, דו, חד-פזי)",
            "טבלה 6.4",
            ShortCircuitCase,
            lambda spec: {"If_values": [0, 0.4, 0.6, 0.8, 1.0, 1.3], "n_drive": None},
            lambda spec, v: {
                f: templates.short_circuit(f, 0.0, spec.nameplate.n_sync, _c(spec))
                for f, _ in FAULTS
            },
            editable_circuit=False,
        ),
        StudyDef(
            "load_characteristic",
            "אופייני עומס (R, L, C)",
            "טבלה 6.5, ציור 6-7",
            LoadCharCase,
            lambda spec: {
                "load_kind": "R",
                "U0": 240.0,
                "I_targets": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                "include_no_load": True,
                "n_drive": None,
            },
            lambda spec, v: _gen(spec),
        ),
        StudyDef(
            "regulation",
            "אופיין ויסות",
            "טבלה 6.6, ציור 6-8",
            RegulationCase,
            lambda spec: {"U_ref": 240.0, "I_targets": [0, 0.1, 0.2, 0.3, 0.4], "n_drive": None},
            lambda spec, v: _gen(spec),
        ),
        StudyDef(
            "zpf",
            "אופיין הגבי בזרם קבוע",
            "טבלה 6.6ב, ציור 6-9",
            ZpfCase,
            lambda spec: {
                "I_const": round(0.5 * spec.nameplate.I_n, 3),
                "If_values": [4.0, 3.6, 3.2, 2.8, 2.4, 2.0],
                "n_drive": None,
            },
            lambda spec, v: _gen(spec, load_kind="L", load_value=1.0),
        ),
        StudyDef(
            "v_curves",
            "אופייני V (מנוע)",
            "טבלה 6.7",
            VCurveCase,
            lambda spec: {
                "U_line": None,
                "points": [
                    {"P": p, "If": i}
                    for p in (0.0, round(0.5 * spec.nameplate.P_n, 1))
                    for i in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0)
                ],
            },
            lambda spec, v: templates.motor_on_grid(
                spec.nameplate.U_n, spec.nameplate.f_n, _c(spec), 2.0, 0.0
            ),
        ),
    ]
}


STUDIES["sudden_sc"] = StudyDef(
    "sudden_sc",
    "קצר פתאומי (סימולציה בזמן)",
    "הרחבה: זרמים תת-מעבריים ומעבריים",
    SuddenScCase,
    lambda spec: {
        "I_f": 0.4,
        "Xd2": None,
        "Xd1": None,
        "Td01": TD01,
        "Td02": TD02,
        "Tq02": TQ02,
        "angle_deg": 0.0,
        "t_end": 1.0,
    },
    None,
    editable_circuit=False,
)

STUDIES["synchronize"] = StudyDef(
    "synchronize",
    "סנכרון לרשת (סימולציה בזמן)",
    "הרחבה: סגירת המפסק בהפרשי זווית ותדר",
    SynchronizeCase,
    lambda spec: {
        "U_line": None,
        "I_f": None,
        "angle_deg": 10.0,
        "df": 0.1,
        "P_drive": 0.0,
        "J": None,
        "Xd2": None,
        "Xd1": None,
        "Td01": TD01,
        "Td02": TD02,
        "Tq02": TQ02,
        "t_end": 10.0,
    },
    None,
    editable_circuit=False,
)


def execute(kind: str, spec: SyncSpec, circuit_doc: Any, case_doc: dict[str, Any]) -> Outcome:
    sd = STUDIES.get(kind)
    if sd is None:
        return Outcome(status="unsupported", error={"message": f"unknown study {kind}"})
    try:
        case = sd.case_model.model_validate(case_doc)
    except Exception as exc:
        return Outcome(
            status="invalid_input", error={"message": "פרמטרי הניסוי שגויים", "details": str(exc)}
        )
    try:
        if isinstance(case, InsulationCase):
            return run_insulation(spec, case)
        if isinstance(case, SuddenScCase):
            return run_sudden_sc(spec, case)
        if isinstance(case, SynchronizeCase):
            return run_synchronize(spec, case)
        if isinstance(case, (DcResistanceCase, ShortCircuitCase)):
            circuits = {k: CircuitModel.model_validate(v) for k, v in circuit_doc.items()}
            if isinstance(case, DcResistanceCase):
                return run_dc_resistance(spec, circuits, case)
            return run_short_circuit(spec, circuits, case)
        circuit = CircuitModel.model_validate(circuit_doc)
        runners: dict[type, Any] = {
            OpenCircuitCase: run_open_circuit,
            LoadCharCase: run_load_characteristic,
            RegulationCase: run_regulation,
            ZpfCase: run_zpf,
            VCurveCase: run_v_curves,
        }
        fn = runners.get(type(case))
        if fn is not None:
            out: Outcome = fn(spec, circuit, case)
            return out
    except StudyError as f:
        return Outcome(status=f.status, error={"message": f.message, "details": f.details})
    return Outcome(status="unsupported", error={"message": f"study {kind} has no executor"})
