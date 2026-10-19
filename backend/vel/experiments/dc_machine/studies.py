"""Study definitions for experiments 5 (DC motor) and 6 (DC generator).

Both experiments use the same machine model and the same component ids (see templates.py).
The independent variables are the ones the student sets in the lab: the brake torque M for a
motor, the field current If (by turning the field rheostat until the ammeter A2 reads it) and
the load current Ia (by turning the load rheostat). Rheostat settings are found by solving for
the reading — the simulation never uses the model's R_f to "know" the setting in advance.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine.circuit import CircuitModel
from vel.engine.simulate import OperatingPoint
from vel.experiments.common import (
    Outcome,
    Param,
    StudyDef,
    StudyError,
    col,
    read,
    solve,
    with_param,
)
from vel.experiments.dc_machine import templates
from vel.experiments.dc_machine.spec import DCSpec
from vel.experiments.dc_machine.templates import WINDINGS, Series

MODEL_VERSION = "mna-dc-1.0+dcm-occ-1.0"
MACH = "M"
R_OPEN = 1e9  # Ω: a rheostat "at infinity" (circuit open)
FIELD_CLAMP = 0.05  # accept field-current targets up to 5 % above the rheostat-at-zero value
LOAD_SCAN = 60  # log-spaced load settings scanned from open circuit down to 0.5 Ω
W = 2 * math.pi / 60  # rpm → rad/s


def _status(w: list[dict[str, Any]]) -> Literal["success", "success_with_warnings"]:
    return "success_with_warnings" if w else "success"


def _finite_list(v: list[float], lo: float, hi: float, what: str) -> list[float]:
    if any((not math.isfinite(x)) or x < lo or x > hi for x in v):
        raise ValueError(f"{what} must be within [{lo}, {hi}]")
    return v


# --------------------------------------------------------------------------- cases


class InsulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_test: float = Field(default=500.0, gt=0, le=5000)


class DcResistanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_targets: list[float] = Field(min_length=1, max_length=10)

    @field_validator("I_targets")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 1e-3, 5.0, "currents")


class FieldSpeedCase(BaseModel):
    """Tables 5/2.3 (no load) and 5/2.7 (constant load): n as the field current is reduced."""

    model_config = ConfigDict(extra="forbid")
    U: float = Field(gt=0, le=1000)
    M_load: float = Field(default=0.0, ge=0, le=100)
    If_targets: list[float] = Field(min_length=1, max_length=20)

    @field_validator("If_targets")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 1e-4, 10.0, "field currents")


class MotorLoadCase(BaseModel):
    """Tables 5/2.4, 2.5 (with R_x) and 2.8 (compound)."""

    model_config = ConfigDict(extra="forbid")
    U: float = Field(gt=0, le=1000)
    If: float = Field(gt=0, le=10, description="shunt field current set at no load [A]")
    R_x: float = Field(default=0.0, ge=0, le=1e4)
    series: Series = "none"
    M_targets: list[float] = Field(min_length=1, max_length=20)

    @field_validator("M_targets")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 0.0, 100.0, "torques")


class RxSpeedCase(BaseModel):
    """Table 5/2.6: speed as the extra armature resistance grows, at constant brake torque."""

    model_config = ConfigDict(extra="forbid")
    U: float = Field(gt=0, le=1000)
    If: float = Field(gt=0, le=10)
    M_load: float = Field(ge=0, le=100)
    R_values: list[float] = Field(min_length=1, max_length=20)

    @field_validator("R_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 0.0, 1e4, "resistances")


class OccCase(BaseModel):
    """Table 6/2.3: separately excited, no load, E as a function of If at constant speed."""

    model_config = ConfigDict(extra="forbid")
    n: float = Field(gt=0, le=1e4)
    If_values: list[float] = Field(min_length=1, max_length=30)

    @field_validator("If_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 0.0, 10.0, "field currents")


class GenLoadCase(BaseModel):
    """Tables 6/2.4 (separate), 2.6 (shunt) and 2.7 (compound): V1 = f(Ia). The field rheostat
    is set once, at no load, so that U1 = U0; it is then left alone while the load grows."""

    model_config = ConfigDict(extra="forbid")
    n: float = Field(gt=0, le=1e4)
    U0: float = Field(gt=0, le=1000, description="no-load terminal voltage to set [V]")
    excitation: Literal["separate", "shunt"] = "separate"
    connections: list[Series] = Field(default=["none"], min_length=1, max_length=2)
    I_targets: list[float] = Field(min_length=1, max_length=20)

    @field_validator("I_targets")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 0.0, 100.0, "load currents")


class RegulationCase(BaseModel):
    """Table 6/2.5: field current needed to hold the load current while the field changes —
    in the lab: change If, re-adjust the load until Ia is back at its value, read V1."""

    model_config = ConfigDict(extra="forbid")
    n: float = Field(gt=0, le=1e4)
    Ia: float = Field(gt=0, le=100)
    If_values: list[float] = Field(min_length=1, max_length=20)

    @field_validator("If_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 1e-4, 10.0, "field currents")


class GridCase(BaseModel):
    """Generator in parallel with a DC network: the field decides generating vs. motoring."""

    model_config = ConfigDict(extra="forbid")
    U: float = Field(gt=0, le=1000)
    n: float = Field(gt=0, le=1e4)
    If_values: list[float] = Field(min_length=1, max_length=20)

    @field_validator("If_values")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        return _finite_list(v, 1e-4, 10.0, "field currents")


# --------------------------------------------------------------------------- helpers


def _monotone_solve(
    f: Callable[[float], float], target: float, lo: float, hi: float, what: str
) -> float:
    """Find x in [lo, hi] (log scale, both > 0) with f(x) = target for a monotone f."""
    flo, fhi = f(lo) - target, f(hi) - target
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if (flo > 0) == (fhi > 0):
        raise StudyError(
            "constraint_violation",
            f"לא ניתן להגיע ל{what} = {target:.4g} בטווח הכיוון של הריאוסטט",
            {"target": target, "at_min": flo + target, "at_max": fhi + target},
        )
    a, b = math.log(lo), math.log(hi)
    fa = flo
    for _ in range(80):
        m = 0.5 * (a + b)
        fm = f(math.exp(m)) - target
        if abs(fm) <= 1e-9 * max(1.0, abs(target)):
            return math.exp(m)
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return math.exp(0.5 * (a + b))


def _field_rheostat(
    circuit: CircuitModel,
    spec: DCSpec,
    i_f: float,
    notes: list[dict[str, Any]] | None = None,
) -> float:
    """Rheostat setting at which the field ammeter reads i_f, for a field fed from a fixed
    voltage. The field circuit is linear, I = U/(R + r): two solves (r = 0 and r = 100 Ω) give
    U and R from the readings themselves — the spec's R_f is never used directly."""
    i0 = read(solve(with_param(circuit, "Rf", "R", 0.0), spec, dc=True), "Af.I")
    if i0 is None or i0 <= 0:
        raise StudyError("invalid_circuit", "אין זרם במעגל העירור")
    if notes is not None and i0 < i_f <= i0 * (1 + FIELD_CLAMP):
        # a lab reading a few % above what the model's field resistance allows: the rheostat
        # is at zero — say so instead of failing (cold vs. warm winding, ammeter class)
        notes.append(
            {
                "code": "field_at_maximum",
                "message": f"If = {i_f:.4g} A מעל המרבי במודל ({i0:.4g} A): הריאוסטט באפס. "
                "ההפרש נובע מהתנגדות העירור (חמה/קרה) או מדיוק מד הזרם",
            }
        )
        return 0.0
    if i_f > i0 * (1 + 1e-9):
        raise StudyError(
            "constraint_violation",
            f"זרם עירור {i_f:.4g} A גבוה מהמרבי {i0:.4g} A (ריאוסטט העירור באפס)",
            {"If_max": i0},
        )
    i1 = read(solve(with_param(circuit, "Rf", "R", 100.0), spec, dc=True), "Af.I")
    if i1 is None or i1 <= 0 or i1 >= i0:
        raise StudyError("invalid_circuit", "מעגל העירור אינו מוזן ממתח קבוע")
    u = 100.0 / (1 / i1 - 1 / i0)
    return max(0.0, u / i_f - u / i0)


def _mech(op: OperatingPoint) -> dict[str, float]:
    return op.internals.get(f"{MACH}.mech", {})


def _motor_row(op: OperatingPoint, u_set: float) -> dict[str, Any]:
    ia = read(op, "Aa.I")
    i_f = read(op, "Af.I")
    u1 = read(op, "U1.U")
    n = op.readings[MACH]["n"]
    m = op.readings[MACH]["M"]
    assert ia is not None and i_f is not None and u1 is not None and n is not None
    assert m is not None
    p1 = u1 * ia
    p2 = m * n * W
    mech = _mech(op)
    return {
        "U1": u1,
        "If": i_f,
        "I1": ia,
        "I_line": ia + i_f,
        "n": n,
        "M": m,
        "P1": p1,
        "P2": p2,
        "eta": p2 / (p1 + u1 * i_f) if p1 > 0 else None,
        "E": mech.get("E_int"),
        "state": "עומד" if mech.get("stalled") else "",
    }


MOTOR_COLUMNS = [
    col("U1", "U1", "V"),
    col("If", "If", "A"),
    col("I1", "I1 (עוגן)", "A"),
    col("n", "n", "rpm"),
    col("M", "M", "N·m"),
    col("P1", "P1 = U1·I1", "W"),
    col("P2", "P2 = M·ω", "W"),
    col("eta", "η = P2/(U1·(I1+If))", ""),
    col("E", "E (כא״מ, מודל)", "V"),
]


def _params_motor(spec: DCSpec, rows: list[dict[str, Any]]) -> list[Param]:
    """C_m·Φ from the first (lightest) point: E/ω, i.e. the manual's 9.55·Ce·Φ."""
    out: list[Param] = []
    r0 = next((r for r in rows if r.get("n") and r.get("E") is not None), None)
    if r0 is not None:
        out.append(
            Param(
                "Cm_phi",
                "Cm·Φ = E/ω (נקודה ראשונה)",
                float(r0["E"]) / (float(r0["n"]) * W),
                "V·s",
                "(U1 − I1·Ra − ΔUb)/ω",
                "consistent",
            )
        )
    out.append(Param("M_n", "מומנט נקוב (שלט)", spec.M_n, "N·m", "9.55·Pn/nn", "consistent"))
    return out


def _over_rated(rows: list[dict[str, Any]], key: str, rated: float) -> list[dict[str, Any]]:
    return [
        {"code": "above_rated_current", "row": k, "message": "זרם העוגן מעל הנומינלי"}
        for k, r in enumerate(rows)
        if isinstance(r.get(key), (int, float)) and abs(r[key]) > 1.05 * rated
    ]


# --------------------------------------------------------------------------- shared runners


def run_insulation(spec: DCSpec, case: InsulationCase, table: str) -> Outcome:
    ins = spec.insulation
    pairs = (
        ("עוגן – גוף", ins.armature_Mohm),
        ("עירור מקבילי – גוף", ins.shunt_Mohm),
        ("עירור טורי – גוף", ins.series_Mohm),
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
                    "title_he": f"טבלה {table} — התנגדות בידוד (500 V)",
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
    spec: DCSpec, circuits: dict[str, CircuitModel], case: DcResistanceCase, table: str
) -> Outcome:
    rows: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for w, label in WINDINGS:
        targets = case.I_targets if w != "shunt" else [min(case.I_targets[0], 0.05)]
        vals: list[float] = []
        for target in targets:
            op1 = solve(with_param(circuits[w], "P", "U", 1.0), spec, dc=True)
            i1 = read(op1, "A.I")
            if not i1:
                raise StudyError("invalid_circuit", f"אין זרם ב{label}")
            # the brush drop makes the armature non-linear: iterate the supply to the target
            u = target / i1
            for _ in range(30):
                op = solve(with_param(circuits[w], "P", "U", u), spec, dc=True)
                i_m = read(op, "A.I")
                assert i_m is not None
                if abs(i_m - target) <= 1e-9 * target:
                    break
                u *= target / i_m if i_m > 0 else 2.0
            i_m, u_m = read(op, "A.I"), read(op, "V.U")
            assert i_m is not None and u_m is not None
            vals.append(u_m / i_m)
            rows.append({"winding": label, "I": i_m, "U": u_m, "R": u_m / i_m})
        summary.append({"winding": label, "R_avg": sum(vals) / len(vals)})
    params = [
        Param(
            "R_a",
            "התנגדות עוגן (ממוצע U/I, כולל מפל מברשות)",
            float(summary[0]["R_avg"]),
            "Ω",
            "ממוצע U/I",
            "consistent",
            note="R = U/I יורד עם הזרם: מפל המברשות כמעט קבוע (≈ 2 V)",
        ),
        Param("R_s", "התנגדות עירור טורי", float(summary[1]["R_avg"]), "Ω", "U/I", "consistent"),
        Param("R_f", "התנגדות עירור מקבילי", float(summary[2]["R_avg"]), "Ω", "U/I", "consistent"),
    ]
    return Outcome(
        status="success_with_warnings",
        warnings=[{"code": "no_temperature_model", "message": "אין תלות טמפרטורה במודל"}],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"טבלה {table} — התנגדות ליפופים (מקור 0–25 V)",
                    "columns": [
                        col("winding", "ליפוף", ""),
                        col("I", "I", "A"),
                        col("U", "U", "V"),
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
            "parameters": [p.to_json() for p in params],
            "curves": [],
        },
    )


# --------------------------------------------------------------------------- motor (exp. 5)


def _motor_base(circuit: CircuitModel, u: float) -> CircuitModel:
    c = with_param(circuit, "P", "U", u)
    return with_param(c, MACH, "speed_mode", "torque")


def run_field_speed(
    spec: DCSpec, circuit: CircuitModel, case: FieldSpeedCase, title: str
) -> Outcome:
    base = with_param(_motor_base(circuit, case.U), MACH, "M_load", case.M_load)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for k, i_f in enumerate(case.If_targets):
        try:
            r = _field_rheostat(base, spec, i_f, warnings)
            op = solve(with_param(base, "Rf", "R", r), spec, dc=True)
        except StudyError as e:
            rows.append({"If": i_f, "note": e.message})
            warnings.append({"code": e.status, "row": k, "message": e.message})
            continue
        rows.append({**_motor_row(op, case.U), "R_rheo": r, "note": ""})
    ok = [r for r in rows if r.get("n") is not None]
    if not ok:
        raise StudyError("constraint_violation", rows[0].get("note") or "אין נקודות פעולה")
    warnings += _over_rated(rows, "I1", spec.nameplate.I_n)
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": title,
                    "columns": [
                        col("If", "If", "A"),
                        col("I1", "I1 (עוגן)", "A"),
                        col("n", "n", "rpm"),
                        col("M", "M", "N·m"),
                        col("U1", "U1", "V"),
                        col("R_rheo", "ריאוסטט עירור", "Ω"),
                        col("note", "הערה", ""),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in _params_motor(spec, ok)],
            "curves": [
                {"id": "n_if", "title_he": "n = f(If)", "x": "If", "y": "n"},
                {"id": "i_if", "title_he": "I1 = f(If)", "x": "If", "y": "I1"},
            ],
        },
    )


def run_motor_load(spec: DCSpec, circuit: CircuitModel, case: MotorLoadCase, title: str) -> Outcome:
    base = with_param(_motor_base(circuit, case.U), "Rx", "R", case.R_x)
    # the field rheostat is set with the motor unloaded, as in the lab, then left alone
    warnings: list[dict[str, Any]] = []
    r = _field_rheostat(with_param(base, MACH, "M_load", 0.0), spec, case.If, warnings)
    base = with_param(base, "Rf", "R", r)
    rows: list[dict[str, Any]] = []
    for k, m in enumerate(case.M_targets):
        try:
            op = solve(with_param(base, MACH, "M_load", m), spec, dc=True)
        except StudyError as e:
            if not rows:
                raise
            rows.append({"M": m, "note": e.message})
            warnings.append({"code": e.status, "row": k, "message": e.message})
            continue
        rows.append({**_motor_row(op, case.U), "note": ""})
        warnings += [{**w, "row": k} for w in op.warnings]
    ok = [r for r in rows if r.get("n") is not None]
    warnings += _over_rated(rows, "I1", spec.nameplate.I_n)
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": title,
                    "columns": [*MOTOR_COLUMNS, col("note", "הערה", "")],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in _params_motor(spec, ok)],
            "curves": [
                {"id": "n", "title_he": "n = f(I1)", "x": "I1", "y": "n"},
                {"id": "m", "title_he": "M = f(I1)", "x": "I1", "y": "M"},
                {"id": "eta", "title_he": "η = f(P2)", "x": "P2", "y": "eta"},
                {"id": "nm", "title_he": "אופיין מכני n = f(M)", "x": "M", "y": "n"},
            ],
        },
    )


def run_rx_speed(spec: DCSpec, circuit: CircuitModel, case: RxSpeedCase) -> Outcome:
    base = _motor_base(circuit, case.U)
    warnings: list[dict[str, Any]] = []
    r = _field_rheostat(with_param(base, MACH, "M_load", 0.0), spec, case.If, warnings)
    base = with_param(with_param(base, "Rf", "R", r), MACH, "M_load", case.M_load)
    rows: list[dict[str, Any]] = []
    for rx in case.R_values:
        op = solve(with_param(base, "Rx", "R", rx), spec, dc=True)
        rows.append({"R_x": rx, **_motor_row(op, case.U)})
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"טבלה 2.6 — ויסות מהירות בנגד נוסף (M = {case.M_load:g} N·m)",
                    "columns": [col("R_x", "R נוסף", "Ω"), *MOTOR_COLUMNS],
                    "rows": rows,
                }
            ],
            "parameters": [
                Param(
                    "dn_dR",
                    "שיפוע dn/dR",
                    (rows[-1]["n"] - rows[0]["n"]) / (rows[-1]["R_x"] - rows[0]["R_x"])
                    if len(rows) > 1 and rows[-1]["R_x"] != rows[0]["R_x"]
                    else None,
                    "rpm/Ω",
                    "Δn/ΔR",
                    "consistent",
                    undefined_reason=None if len(rows) > 1 else "נדרשות לפחות שתי נקודות",
                ).to_json()
            ],
            "curves": [{"id": "n_r", "title_he": "n = f(R נוסף)", "x": "R_x", "y": "n"}],
        },
    )


# --------------------------------------------------------------------------- generator (exp. 6)


def _gen(circuit: CircuitModel, n: float) -> CircuitModel:
    return with_param(with_param(circuit, MACH, "speed_mode", "speed"), MACH, "n_set", n)


def _gen_row(op: OperatingPoint) -> dict[str, Any]:
    u1 = read(op, "U1.U")
    ia = read(op, "Aa.I")
    i_f = read(op, "Af.I")
    mech = _mech(op)
    n = op.readings[MACH]["n"]
    m = op.readings[MACH]["M"]
    assert u1 is not None and ia is not None and n is not None and m is not None
    p_out = u1 * ia
    p_in = m * n * W
    return {
        "n": n,
        "If": i_f,
        "Ia": ia,
        "U1": u1,
        "E": mech.get("E_int"),
        "P_out": p_out,
        "M": m,
        "P_in": p_in,
        "eta": p_out / p_in if p_in > 0 and p_out > 0 else None,
    }


GEN_COLUMNS = [
    col("If", "If", "A"),
    col("Ia", "Ia (עומס)", "A"),
    col("U1", "V1", "V"),
    col("E", "E (כא״מ, מודל)", "V"),
    col("P_out", "P = V1·Ia", "W"),
    col("M", "M בציר (סרוו)", "N·m"),
    col("eta", "η = P/(M·ω)", ""),
]


def run_occ(spec: DCSpec, circuit: CircuitModel, case: OccCase) -> Outcome:
    base = with_param(_gen(circuit, case.n), "S4", "closed", False)
    rows = []
    for i_f in case.If_values:
        if i_f <= 0:
            op = solve(with_param(base, "Rf", "R", R_OPEN), spec, dc=True)
        else:
            op = solve(with_param(base, "Rf", "R", _field_rheostat(base, spec, i_f)), spec, dc=True)
        row = _gen_row(op)
        rows.append({"If": row["If"] if i_f > 0 else 0.0, "E_up": row["U1"], "n": case.n})
    e0 = rows[0]["E_up"] if case.If_values and case.If_values[0] <= 0 else None
    params = [
        Param(
            "E0",
            "מתח שיורי E0 (If = 0)",
            e0,
            "V",
            "E(If = 0)",
            "consistent",
            undefined_reason=None if e0 is not None else "אין נקודה ב-If = 0",
        ),
        Param("U_n", "מתח נקוב (שלט)", spec.nameplate.U_n, "V", "שלט", "consistent"),
    ]
    return Outcome(
        status="success_with_warnings",
        warnings=[
            {
                "code": "no_hysteresis",
                "message": "במודל אין היסטרזיס: עקומת הירידה זהה לעקומת העלייה. במעבדה עקומת "
                "הירידה גבוהה במעט (מגנטיות שיורית)",
            }
        ],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"טבלה 2.3 — אופיין ריקם בעירור זר (n = {case.n:g} סל״ד)",
                    "columns": [
                        col("If", "If", "A"),
                        col("E_up", "E (מודל ללא היסטרזיס)", "V"),
                        col("n", "n", "rpm"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [{"id": "occ", "title_he": "E = f(If)", "x": "If", "y": "E_up"}],
        },
    )


def _set_no_load_voltage(base: CircuitModel, spec: DCSpec, u0: float) -> tuple[CircuitModel, float]:
    """Turn the field rheostat (S4 open) until V1 = u0. Returns the circuit and the setting."""
    open_ = with_param(base, "S4", "closed", False)

    def v(r: float) -> float:
        u = read(solve(with_param(open_, "Rf", "R", r), spec, dc=True), "U1.U")
        assert u is not None
        return u

    r = _monotone_solve(v, u0, 1e-3, 1e5, "מתח ריקם V1")
    return with_param(base, "Rf", "R", r), r


def _load_for_current(base: CircuitModel, spec: DCSpec, target: float) -> OperatingPoint:
    """Turn the load rheostat down from "open" until the load ammeter reads target. A shunt
    generator's Ia(R_L) is not monotone (beyond its maximum current the voltage collapses), so
    the first crossing coming from no load is taken — the branch the lab follows."""
    if target <= 0:
        return solve(with_param(base, "S4", "closed", False), spec, dc=True)
    closed = with_param(base, "S4", "closed", True)

    def ia(r: float) -> float:
        i = read(solve(with_param(closed, "RL", "R", r), spec, dc=True), "Aa.I")
        assert i is not None
        return i

    grid = [1e6 * (0.5 / 1e6) ** (k / LOAD_SCAN) for k in range(LOAD_SCAN + 1)]
    prev_r, prev_i = grid[0], ia(grid[0])
    i_max = prev_i
    for r in grid[1:]:
        i = ia(r)
        i_max = max(i_max, i)
        if (prev_i - target) * (i - target) <= 0:
            lo, hi = math.log(r), math.log(prev_r)  # Ia(lo) ≥ target ≥ Ia(hi)
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                im = ia(math.exp(mid))
                if abs(im - target) <= 1e-9 * target:
                    break
                if im > target:
                    lo = mid
                else:
                    hi = mid
            return solve(with_param(closed, "RL", "R", math.exp(0.5 * (lo + hi))), spec, dc=True)
        if i < prev_i and i < target:
            break  # past the maximum: the voltage has collapsed
        prev_r, prev_i = r, i
    raise StudyError(
        "constraint_violation",
        f"המחולל אינו מסוגל לספק Ia = {target:.4g} A (מרבי ≈ {i_max:.3g} A בענף היציב)",
        {"target": target, "I_max": i_max},
    )


_POL = {"none": 0, "cumulative": 1, "differential": -1}
_POL_HE = {"none": "", "cumulative": "S1-S2 (מצטבר)", "differential": "S2-S1 (מנוגד)"}


def run_gen_load(
    spec: DCSpec,
    circuits: dict[str, CircuitModel],
    case: GenLoadCase,
    title: str,
) -> Outcome:
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    params: list[Param] = []
    for ser in case.connections:
        base = _gen(circuits[ser], case.n)
        base, r_f = _set_no_load_voltage(base, spec, case.U0)
        for i_t in case.I_targets:
            try:
                op = _load_for_current(base, spec, i_t)
            except StudyError as e:
                rows.append({"pol": _POL[ser], "conn": _POL_HE[ser], "Ia": i_t, "note": e.message})
                warnings.append({"code": e.status, "row": len(rows) - 1, "message": e.message})
                continue
            rows.append({"pol": _POL[ser], "conn": _POL_HE[ser], **_gen_row(op), "note": ""})
        pts = [r for r in rows if r.get("pol") == _POL[ser] and r.get("U1") is not None]
        if len(pts) > 1:
            v0, vn = pts[0]["U1"], pts[-1]["U1"]
            params.append(
                Param(
                    f"dV{('_' + ser) if ser != 'none' else ''}",
                    f"מפל מתח {_POL_HE[ser]} 100·(V0 − V)/V".strip(),
                    100 * (v0 - vn) / vn if vn else None,
                    "%",
                    "V% = 100·(Vo − Vn)/Vn",
                    "consistent",
                    note=f"בין Ia = {pts[0]['Ia']:.3g} A ל-Ia = {pts[-1]['Ia']:.3g} A",
                )
            )
        params.append(
            Param(
                f"R_rheo{('_' + ser) if ser != 'none' else ''}",
                "ריאוסטט העירור שנקבע בריקם",
                r_f,
                "Ω",
                f"V1 = {case.U0:g} V בריקם",
                "consistent",
            )
        )
    warnings += _over_rated(rows, "Ia", spec.nameplate.I_n)
    cols = [*GEN_COLUMNS, col("note", "הערה", "")]
    if case.connections != ["none"]:
        cols = [col("conn", "חיבור הטורי", ""), col("pol", "קוטביות (+1/−1)", ""), *cols]
    curves: list[dict[str, Any]] = [
        {"id": "v", "title_he": "V1 = f(Ia)", "x": "Ia", "y": "U1"}
        | ({"group": "pol"} if case.connections != ["none"] else {})
    ]
    if case.excitation == "shunt":
        curves.append({"id": "if", "title_he": "If = f(Ia)", "x": "Ia", "y": "If"})
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [{"id": "readings", "title_he": title, "columns": cols, "rows": rows}],
            "parameters": [p.to_json() for p in params],
            "curves": curves,
        },
    )


def run_regulation(spec: DCSpec, circuit: CircuitModel, case: RegulationCase) -> Outcome:
    base = _gen(circuit, case.n)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for k, i_f in enumerate(case.If_values):
        try:
            c = with_param(base, "Rf", "R", _field_rheostat(base, spec, i_f))
            op = _load_for_current(c, spec, case.Ia)
        except StudyError as e:
            rows.append({"If": i_f, "note": e.message})
            warnings.append({"code": e.status, "row": k, "message": e.message})
            continue
        rows.append({**_gen_row(op), "note": ""})
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"טבלה 2.5 — V1 = f(If) בזרם עומס קבוע Ia = {case.Ia:g} A",
                    "columns": [*GEN_COLUMNS, col("note", "הערה", "")],
                    "rows": rows,
                }
            ],
            "parameters": [],
            "curves": [{"id": "v_if", "title_he": "V1 = f(If), Ia קבוע", "x": "If", "y": "U1"}],
        },
    )


def run_grid(spec: DCSpec, circuit: CircuitModel, case: GridCase) -> Outcome:
    base = with_param(_gen(circuit, case.n), "P", "U", case.U)
    rows: list[dict[str, Any]] = []
    for i_f in case.If_values:
        op = solve(with_param(base, "Rf", "R", _field_rheostat(base, spec, i_f)), spec, dc=True)
        g = _gen_row(op)
        g["Ia"] = -g["Ia"]  # the ammeter reads network → machine
        g["P_out"] = g["U1"] * g["Ia"]
        g["eta"] = g["P_out"] / g["P_in"] if g["P_in"] > 0 and g["P_out"] > 0 else None
        g["mode"] = "מחולל (מספק לרשת)" if g["Ia"] > 0 else "מנוע (צורך מהרשת)"
        rows.append(g)
    return Outcome(
        status="success_with_warnings",
        warnings=[
            {
                "code": "sign_convention",
                "message": "Ia חיובי = המכונה מספקת זרם לרשת; שלילי = צורכת ממנה (פועלת כמנוע "
                "והסרוו בולם). M שלילי = הסרוו נדרש לבלום",
            }
        ],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": f"מחולל במקביל לרשת DC ({case.U:g} V, n = {case.n:g} סל״ד)",
                    "columns": [*GEN_COLUMNS, col("mode", "אופן", "")],
                    "rows": rows,
                }
            ],
            "parameters": [],
            "curves": [
                {"id": "ia_if", "title_he": "Ia = f(If)", "x": "If", "y": "Ia"},
                {"id": "m_if", "title_he": "M = f(If)", "x": "If", "y": "M"},
            ],
        },
    )


# --------------------------------------------------------------------------- registry


def _m(spec: DCSpec, k: float) -> float:
    return round(k * spec.M_n, 3)


LAB_U = 174.0  # V: supply voltage the 2025 motor tables were measured at
# rpm: the 2025 report does not record the servo speed. Table 6/2.6 (shunt, no load: 220 V at
# If = 0.48 A) implies ≈ 2800 rpm with the fitted OCC; table 6/2.3 (OCC) implies ≈ 2550 rpm.
GEN_N = 2800.0


def _dc_circuits(spec: DCSpec, v: str) -> dict[str, Any]:
    return {w: templates.dc_winding(w) for w, _ in WINDINGS}


COMMON: list[StudyDef] = [
    StudyDef(
        "insulation",
        "בדיקת בידוד (מגר)",
        "טבלה 2.1",
        InsulationCase,
        lambda spec: {"U_test": 500.0},
        None,
        editable_circuit=False,
    ),
    StudyDef(
        "dc_resistance",
        "התנגדות ליפופים",
        "ציור 2.1 / 3.1, טבלה 2.2",
        DcResistanceCase,
        lambda spec: {"I_targets": [0.7, 1.1, 1.6]},
        _dc_circuits,
        editable_circuit=False,
    ),
]

MOTOR_STUDIES: dict[str, StudyDef] = {
    s.kind: s
    for s in [
        *COMMON,
        StudyDef(
            "no_load_field",
            "מנוע מקבילי בריקם: n = f(If)",
            "ציור 3.2, טבלה 2.3",
            FieldSpeedCase,
            lambda spec: {
                "U": LAB_U,
                "M_load": 0.0,
                "If_targets": [0.46, 0.43, 0.405, 0.372, 0.339, 0.306],
            },
            lambda spec, v: templates.motor(LAB_U, 0.0),
        ),
        StudyDef(
            "load",
            "מנוע מקבילי בעומס",
            "טבלה 2.4",
            MotorLoadCase,
            lambda spec: {
                "U": LAB_U,
                "If": 0.46,
                "M_targets": [_m(spec, k) for k in (0, 0.15, 0.35, 0.5, 0.7, 0.85)],
            },
            lambda spec, v: templates.motor(LAB_U, 0.0),
        ),
        StudyDef(
            "load_rext",
            "מנוע מקבילי בעומס עם נגד נוסף",
            "טבלה 2.5",
            MotorLoadCase,
            lambda spec: {
                "U": LAB_U,
                "If": 0.46,
                "R_x": 30.0,
                "M_targets": [_m(spec, k) for k in (0, 0.15, 0.3, 0.45, 0.6, 0.7)],
            },
            lambda spec, v: templates.motor(LAB_U, 0.0, r_x=30.0),
        ),
        StudyDef(
            "rx_speed",
            "ויסות מהירות בנגד נוסף",
            "טבלה 2.6",
            RxSpeedCase,
            lambda spec: {
                "U": LAB_U,
                "If": 0.46,
                "M_load": _m(spec, 0.6),
                "R_values": [0.0, 3.0, 6.0, 12.0, 21.0, 30.0],
            },
            lambda spec, v: templates.motor(LAB_U, 0.0),
        ),
        StudyDef(
            "field_speed",
            "ויסות מהירות בזרם העירור (בעומס)",
            "טבלה 2.7",
            FieldSpeedCase,
            lambda spec: {
                "U": LAB_U,
                "M_load": _m(spec, 0.6),
                "If_targets": [0.46, 0.416, 0.388, 0.356, 0.332, 0.298],
            },
            lambda spec, v: templates.motor(LAB_U, 0.0),
        ),
        StudyDef(
            "compound",
            "מנוע בעירור מעורב",
            "ציור 3.6, טבלה 2.8",
            MotorLoadCase,
            lambda spec: {
                "U": LAB_U,
                "If": 0.46,
                "series": "cumulative",
                "M_targets": [_m(spec, k) for k in (0, 0.15, 0.3, 0.45, 0.6, 0.7)],
            },
            lambda spec, v: templates.motor(LAB_U, 0.0, series="cumulative"),
        ),
    ]
}


def _gen_circuits(exc: Literal["separate", "shunt"], series: list[Series]) -> dict[str, Any]:
    return {s: templates.generator(GEN_N, 0.0, R_OPEN, excitation=exc, series=s) for s in series}


GEN_STUDIES: dict[str, StudyDef] = {
    s.kind: s
    for s in [
        *COMMON,
        StudyDef(
            "occ",
            "אופיין ריקם בעירור זר",
            "ציור 2.2, טבלה 2.3",
            OccCase,
            lambda spec: {
                "n": 2500.0,
                "If_values": [0.0, 0.1, 0.15, 0.17, 0.19, 0.2, 0.22, 0.25, 0.27],
            },
            lambda spec, v: templates.generator(2500.0, 0.0, R_OPEN, closed=False),
        ),
        StudyDef(
            "ext_separate",
            "אופיין חיצוני בעירור זר",
            "טבלה 2.4",
            GenLoadCase,
            lambda spec: {
                "n": GEN_N,
                "U0": 220.0,
                "excitation": "separate",
                "connections": ["none"],
                "I_targets": [0.0, 0.17, 0.4, 0.5, 0.67, 0.83, 0.98, 1.13],
            },
            lambda spec, v: _gen_circuits("separate", ["none"]),
            editable_circuit=False,
        ),
        StudyDef(
            "regulation",
            "V1 = f(If) בזרם עומס קבוע",
            "טבלה 2.5",
            RegulationCase,
            lambda spec: {
                "n": GEN_N,
                "Ia": round(0.6 * spec.nameplate.I_n, 3),
                "If_values": [0.24, 0.3, 0.36, 0.42, 0.48, 0.54],
            },
            lambda spec, v: templates.generator(GEN_N, 0.0, 100.0),
        ),
        StudyDef(
            "shunt_load",
            "אופיין חיצוני בעירור מקבילי",
            "ציור 2.6, טבלה 2.6",
            GenLoadCase,
            lambda spec: {
                "n": GEN_N,
                "U0": 220.0,
                "excitation": "shunt",
                "connections": ["none"],
                "I_targets": [0.0, 0.168, 0.337, 0.5, 0.65, 0.81, 0.95, 1.3],
            },
            lambda spec, v: _gen_circuits("shunt", ["none"]),
            editable_circuit=False,
        ),
        StudyDef(
            "compound",
            "אופיין חיצוני בעירור מעורב (שתי קוטביות)",
            "ציור 2.8, טבלה 2.7",
            GenLoadCase,
            lambda spec: {
                "n": GEN_N,
                "U0": 220.0,
                "excitation": "shunt",
                "connections": ["cumulative", "differential"],
                "I_targets": [0.0, 0.23, 0.33, 0.5, 0.66, 0.82, 0.97, 1.13, 1.28],
            },
            lambda spec, v: _gen_circuits("shunt", ["cumulative", "differential"]),
            editable_circuit=False,
        ),
        StudyDef(
            "grid",
            "מחולל במקביל לרשת DC",
            "השיטה, סעיף 6 (ללא טבלה בחוברת)",
            GridCase,
            lambda spec: {
                "U": 220.0,
                "n": GEN_N,
                "If_values": [0.35, 0.4, 0.45, 0.5, 0.55, 0.59],
            },
            lambda spec, v: templates.grid_parallel(220.0, GEN_N, 0.0),
        ),
    ]
}


def _validate(sd: StudyDef | None, kind: str, case_doc: dict[str, Any]) -> Any:
    if sd is None:
        return Outcome(status="unsupported", error={"message": f"unknown study {kind}"})
    try:
        return sd.case_model.model_validate(case_doc)
    except Exception as exc:
        return Outcome(
            status="invalid_input", error={"message": "פרמטרי הניסוי שגויים", "details": str(exc)}
        )


MOTOR_TITLES = {
    "no_load_field": "טבלה 2.3 — מנוע מקבילי בריקם: n = f(If)",
    "field_speed": "טבלה 2.7 — ויסות מהירות בזרם העירור (עומס קבוע)",
    "load": "טבלה 2.4 — מנוע מקבילי בעומס",
    "load_rext": "טבלה 2.5 — מנוע מקבילי בעומס עם נגד נוסף",
    "compound": "טבלה 2.8 — מנוע בעירור מעורב",
}


def execute_motor(kind: str, spec: DCSpec, circuit_doc: Any, case_doc: dict[str, Any]) -> Outcome:
    case = _validate(MOTOR_STUDIES.get(kind), kind, case_doc)
    if isinstance(case, Outcome):
        return case
    try:
        if isinstance(case, InsulationCase):
            return run_insulation(spec, case, "2.1")
        if isinstance(case, DcResistanceCase):
            circuits = {k: CircuitModel.model_validate(v) for k, v in circuit_doc.items()}
            return run_dc_resistance(spec, circuits, case, "2.2")
        circuit = CircuitModel.model_validate(circuit_doc)
        if isinstance(case, FieldSpeedCase):
            return run_field_speed(spec, circuit, case, MOTOR_TITLES[kind])
        if isinstance(case, MotorLoadCase):
            if kind == "compound" and case.series == "none":
                case = case.model_copy(update={"series": "cumulative"})
            if case.series != "none":
                circuit = templates.motor(case.U, 0.0, r_x=case.R_x, series=case.series)
            return run_motor_load(spec, circuit, case, MOTOR_TITLES[kind])
        if isinstance(case, RxSpeedCase):
            return run_rx_speed(spec, circuit, case)
    except StudyError as f:
        return Outcome(status=f.status, error={"message": f.message, "details": f.details})
    return Outcome(status="unsupported", error={"message": f"study {kind} has no executor"})


GEN_FIXED: dict[str, dict[str, Any]] = {
    "ext_separate": {"excitation": "separate", "connections": ["none"]},
    "shunt_load": {"excitation": "shunt", "connections": ["none"]},
    "compound": {"excitation": "shunt", "connections": ["cumulative", "differential"]},
}

GEN_TITLES = {
    "ext_separate": "טבלה 2.4 — אופיין חיצוני בעירור זר (If קבוע)",
    "shunt_load": "טבלה 2.6 — אופיין חיצוני בעירור מקבילי",
    "compound": "טבלה 2.7 — אופיין חיצוני בעירור מעורב",
}


def execute_generator(
    kind: str, spec: DCSpec, circuit_doc: Any, case_doc: dict[str, Any]
) -> Outcome:
    case = _validate(GEN_STUDIES.get(kind), kind, case_doc)
    if isinstance(case, Outcome):
        return case
    try:
        if isinstance(case, InsulationCase):
            return run_insulation(spec, case, "2.1")
        if isinstance(case, DcResistanceCase):
            circuits = {k: CircuitModel.model_validate(v) for k, v in circuit_doc.items()}
            return run_dc_resistance(spec, circuits, case, "2.2")
        if isinstance(case, GenLoadCase):
            # each table has its own figure: excitation and series connections are fixed
            case = case.model_copy(update=GEN_FIXED[kind])
            circuits = _gen_circuits(case.excitation, list(case.connections))
            return run_gen_load(spec, circuits, case, GEN_TITLES[kind])
        circuit = CircuitModel.model_validate(circuit_doc)
        if isinstance(case, OccCase):
            return run_occ(spec, circuit, case)
        if isinstance(case, RegulationCase):
            return run_regulation(spec, circuit, case)
        if isinstance(case, GridCase):
            return run_grid(spec, circuit, case)
    except StudyError as f:
        return Outcome(status=f.status, error={"message": f.message, "details": f.details})
    return Outcome(status="unsupported", error={"message": f"study {kind} has no executor"})
