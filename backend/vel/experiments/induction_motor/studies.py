"""Study definitions for experiment 2 (induction motor) and their executors."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine.circuit import CircuitModel
from vel.engine.simulate import MechanicalError, OperatingPoint, operating_point_at_slip
from vel.experiments.common import (
    Outcome,
    Param,
    StudyDef,
    StudyError,
    col,
    read,
    solve,
    undefined_warnings,
    with_param,
)
from vel.experiments.induction_motor import derive, templates
from vel.experiments.induction_motor.derive import MotorLike
from vel.experiments.induction_motor.spec import MotorSpec
from vel.experiments.induction_motor.templates import WINDINGS
from vel.experiments.induction_motor.transient import J_ASSUMED, DolStartCase, run_dol_start

MODEL_VERSION = "mna-phasor-1.0+im-T-slip-1.0+im-dq5-1.0"

MOTOR = "M"


def _positive(v: list[float], hi: float, what: str) -> list[float]:
    if any((not math.isfinite(x)) or x <= 0 or x > hi for x in v):
        raise ValueError(f"{what} must be in (0, {hi:g}]")
    return v


# --------------------------------------------------------------------------- cases


class NoLoadCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    U_line_values: list[float] = Field(min_length=1, max_length=40)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {
            "U1L": "V1.U",
            "I0": "A.I",
            "P_W": "W.P",
            "pf": "W.pf",
            "n": "M.n",
        }
    )

    @field_validator("U_line_values")
    @classmethod
    def _pos(cls, v: list[float]) -> list[float]:
        return _positive(v, 1e5, "voltages")


class LockedRotorCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    I_targets_pu: list[float] = Field(min_length=1, max_length=20)
    max_U_pu: float = Field(default=0.6, gt=0, le=1.0)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {"U_k": "V1.U", "I_k": "A.I", "P_W": "W.P", "pf": "W.pf"}
    )

    @field_validator("I_targets_pu")
    @classmethod
    def _pos(cls, v: list[float]) -> list[float]:
        return _positive(v, 1.5, "current targets (× I_n)")


class LoadCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    U_line: float | None = Field(default=None, gt=0, description="None → rated U_n")
    M_targets: list[float] = Field(min_length=1, max_length=30, description="brake torque [N·m]")
    torque_speed_curve: bool = True
    bindings: dict[str, str] = Field(
        default_factory=lambda: {
            "U1L": "V1.U",
            "I1": "A.I",
            "P_W": "W.P",
            "pf": "W.pf",
            "n": "M.n",
            "M": "M.M",
        }
    )

    @field_validator("M_targets")
    @classmethod
    def _nonneg(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x < 0 or x > 1e4 for x in v):
            raise ValueError("brake torques must be in [0, 1e4] N·m")
        return v


class InverterPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    f: float = Field(gt=0, le=400)
    M: float = Field(ge=0, le=1e4)


class InverterCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = "G"
    points: list[InverterPoint] = Field(min_length=1, max_length=40)
    law: Literal["V/f"] = "V/f"
    U_boost: float = Field(default=0.0, ge=0, le=100, description="voltage boost at 0 Hz [V]")
    f_start: float = Field(default=10.0, gt=0, le=50)
    bindings: dict[str, str] = Field(
        default_factory=lambda: {
            "U_out": "V1.U",
            "I_out": "A.I",
            "P_W": "W.P",
            "pf": "W.pf",
            "n": "M.n",
            "M": "M.M",
        }
    )


class DcResistanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_targets: list[float] = Field(min_length=1, max_length=10)

    @field_validator("I_targets")
    @classmethod
    def _pos(cls, v: list[float]) -> list[float]:
        return _positive(v, 50, "currents [A]")


class InsulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_test: float = Field(default=500.0, gt=0, le=5000)


# --------------------------------------------------------------------------- helpers


def _row(op: OperatingPoint, bindings: dict[str, str], **extra: Any) -> dict[str, Any]:
    r: dict[str, Any] = dict(extra)
    for c, b in bindings.items():
        r[c] = read(op, b)
    return r


def _op_warnings(op: OperatingPoint, row: int) -> list[dict[str, Any]]:
    return [{**w, "row": row} for w in op.warnings]


def _mech(op: OperatingPoint) -> dict[str, float]:
    return op.internals.get(f"{MOTOR}.mech", {})


def _status(warnings: list[dict[str, Any]]) -> Literal["success", "success_with_warnings"]:
    return "success_with_warnings" if warnings else "success"


def _vf(spec: MotorLike, f: float, boost: float) -> float:
    """V/f law: U = U_boost + (U_n − U_boost)·f/f_n, limited to U_n above f_n (field weakening)."""
    un, fn = spec.nameplate.U_n, spec.nameplate.f_n
    return min(un, boost + (un - boost) * f / fn)


# --------------------------------------------------------------------------- studies


def run_no_load(spec: MotorLike, circuit: CircuitModel, case: NoLoadCase) -> Outcome:
    base = with_param(circuit, MOTOR, "M_load", 0.0)
    rows, warnings = [], []
    for i, u in enumerate(case.U_line_values):
        op = solve(with_param(base, case.source, "U_line", u), spec)
        rows.append(_row(op, case.bindings, point=i + 1, U_set=u, slip=_mech(op).get("s")))
        warnings += undefined_warnings(op, i, case.bindings) + _op_warnings(op, i)
        if u > 1.1 * spec.nameplate.U_n:
            warnings.append(
                {
                    "code": "saturation_not_modelled",
                    "row": i,
                    "message": "מעל 1.1·Un: הרוויה של ענף המגנוט אינה ממודלת במנוע (Xm קבוע)",
                }
            )
    rows, params, at, dw = derive.no_load(rows, spec)
    warnings += dw
    if not params:
        raise StudyError("invalid_circuit", "חסרות קריאות לחישוב פרמטרי הריקם")
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 4.4 — ריקם",
                    "columns": [
                        col("point", "#", ""),
                        col("U1L", "U1 קווי", "V"),
                        col("I0", "I0", "A"),
                        col("P_W", "קריאת מד ההספק", "W"),
                        col("P0", "P0 = 3·P", "W"),
                        col("pf", "cos φ0", ""),
                        col("n", "n", "rpm"),
                        col("slip", "s", ""),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "parameters_at": at,
            "curves": [
                {"id": "i0", "title_he": "זרם ריקם I0 = f(U1)", "x": "U1L", "y": "I0"},
                {"id": "p0", "title_he": "הספק ריקם P0 = f(U1)", "x": "U1L", "y": "P0"},
            ],
        },
    )


def run_locked_rotor(spec: MotorLike, circuit: CircuitModel, case: LockedRotorCase) -> Outcome:
    un, i_n = spec.nameplate.U_n, spec.nameplate.I_n
    base = with_param(circuit, MOTOR, "locked", True)
    i_bind = case.bindings["I_k"]
    u_max = case.max_U_pu * un

    def current_at(u: float) -> tuple[float, OperatingPoint]:
        op = solve(with_param(base, case.source, "U_line", u), spec)
        val = read(op, i_bind)
        if val is None or val <= 0:
            raise StudyError("invalid_circuit", "אין זרם במנוע — המעגל פתוח?")
        return val, op

    rows, warnings = [], []
    for k, tpu in enumerate(case.I_targets_pu):
        target = tpu * i_n
        # Locked rotor is linear in U (constant impedance): one probe gives the exact setting;
        # a second solve confirms it.
        i_probe, _ = current_at(0.01 * un)
        u = 0.01 * un * target / i_probe
        if u > u_max:
            raise StudyError(
                "constraint_violation",
                f"הזרם {tpu:g}·In דורש {u:.4g} V — מעל הגבול {case.max_U_pu:g}·Un. "
                "האם הרוטור באמת נעול?",
                {"U_needed": u, "U_max": u_max},
            )
        i_got, op = current_at(u)
        if abs(i_got - target) > 1e-9 * target:
            raise StudyError("convergence_failure", "כיוון המתח לזרם המטרה לא התכנס")
        rows.append(_row(op, case.bindings, point=k + 1, I_target_pu=tpu, U_set=u))
        warnings += undefined_warnings(op, k, case.bindings)
        if tpu > 1.0:
            warnings.append(
                {"code": "above_rated_current", "row": k, "message": "זרם מעל הנומינלי — אסור"}
            )
    rows, params, at, dw = derive.locked_rotor(rows, spec)
    warnings += dw
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 4.5 — רוטור נעול (קצר)",
                    "columns": [
                        col("point", "#", ""),
                        col("U_k", "Uk קווי", "V"),
                        col("I_k", "Ik", "A"),
                        col("P_W", "קריאת מד ההספק", "W"),
                        col("P_k", "Pk = 3·P", "W"),
                        col("pf", "cos φk", ""),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "parameters_at": at,
            "curves": [
                {"id": "uk", "title_he": "Uk = f(Ik)", "x": "I_k", "y": "U_k"},
                {"id": "pk", "title_he": "Pk = f(Ik)", "x": "I_k", "y": "P_k"},
            ],
        },
    )


def _kloss(m_max: float, s_cr: float, s: float) -> float:
    return 2 * m_max / (s / s_cr + s_cr / s) if s > 0 else 0.0


def run_load(spec: MotorLike, circuit: CircuitModel, case: LoadCase) -> Outcome:
    u = case.U_line or spec.nameplate.U_n
    base = with_param(circuit, case.source, "U_line", u)
    base = with_param(base, MOTOR, "locked", False)
    rows, warnings = [], []
    mech: dict[str, float] = {}
    for k, m in enumerate(case.M_targets):
        op = solve(with_param(base, MOTOR, "M_load", m), spec)
        mech = _mech(op)
        rows.append(_row(op, case.bindings, point=k + 1, M_set=m))
        warnings += undefined_warnings(op, k, case.bindings) + _op_warnings(op, k)
        i1 = rows[-1].get("I1")
        if i1 is not None and i1 > 1.05 * spec.nameplate.I_n:
            warnings.append(
                {"code": "above_rated_current", "row": k, "message": "זרם המנוע מעל הנומינלי"}
            )
    rows = derive.load(rows, spec)
    tables = [
        {
            "id": "readings",
            "title_he": "טבלה 4.6 — עומס (בלם אבקה מגנטית)",
            "columns": [
                col("point", "#", ""),
                col("U1L", "U1 קווי", "V"),
                col("I1", "I1", "A"),
                col("P_W", "קריאת מד ההספק", "W"),
                col("P1", "P1 = 3·P", "W"),
                col("n", "N", "rpm"),
                col("M", "M", "N·m"),
                col("P2", "P2 = M·n/9.55", "W"),
                col("eta", "η = P2/P1", ""),
                col("slip", "s", ""),
                col("pf", "cos φ", ""),
            ],
            "rows": rows,
        }
    ]
    params: list[Param] = []
    if mech:
        m_max, s_cr = mech["M_max"], mech["s_at_M_max"]
        params = [
            Param("M_max", "מומנט פריצה M_max", m_max, "N·m", "max M(s)", "analytic"),
            Param("s_cr", "החלקה קריטית s_cr", s_cr, "", "argmax M(s)", "analytic"),
            Param("M_start", "מומנט התנעה", mech["M_start"], "N·m", "M(s = 1)", "analytic"),
            Param(
                "M_n",
                "מומנט נקוב (שלט)",
                spec.M_n,
                "N·m",
                "9.55·Pn / nn",
                "consistent",
            ),
        ]
    curves = [
        {"id": "s", "title_he": "החלקה S = f(P2)", "x": "P2", "y": "slip"},
        {"id": "m", "title_he": "מומנט M = f(P2)", "x": "P2", "y": "M"},
        {"id": "i1", "title_he": "זרם I1 = f(P2)", "x": "P2", "y": "I1"},
        {"id": "pf", "title_he": "cos φ = f(P2)", "x": "P2", "y": "pf"},
        {"id": "eta", "title_he": "נצילות η = f(P2)", "x": "P2", "y": "eta"},
    ]
    if case.torque_speed_curve and mech:
        ts = []
        grid = sorted({*(i / 40 for i in range(1, 41)), *(0.002 * i for i in range(1, 25))})
        for s in grid:
            try:
                op = operating_point_at_slip(base, spec, s)
            except MechanicalError as exc:
                raise StudyError(exc.status, exc.message, exc.details) from exc
            mm = _mech(op)
            ts.append(
                {
                    "slip": s,
                    "n": mm["n"],
                    "M_em": mm["M_em"],
                    "M_kloss": _kloss(mech["M_max"], mech["s_at_M_max"], s),
                    "I1": read(op, case.bindings["I1"]),
                }
            )
        tables.append(
            {
                "id": "torque_speed",
                "title_he": "אופיין מומנט–מהירות (סימולציה בלבד; כולל הענף הלא יציב)",
                "columns": [
                    col("slip", "s", ""),
                    col("n", "n", "rpm"),
                    col("M_em", "M אלקטרומגנטי", "N·m"),
                    col("M_kloss", "M* (נוסחת קלוס)", "N·m"),
                    col("I1", "I1", "A"),
                ],
                "rows": ts,
            }
        )
        curves += [
            {
                "id": "torque_speed",
                "title_he": "M = f(n) — מודל מול נוסחת קלוס",
                "x": "n",
                "y": "M_em",
                "y2": "M_kloss",
                "table": "torque_speed",
            },
            {
                "id": "current_speed",
                "title_he": "I1 = f(n)",
                "x": "n",
                "y": "I1",
                "table": "torque_speed",
            },
        ]
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={"tables": tables, "parameters": [p.to_json() for p in params], "curves": curves},
    )


INVERTER_WARNING = (
    "מודל יסודית בלבד: האינוורטר ממודל כמקור סינוסי במתח ובתדר היסודית. לא ממודלים הרמוניות "
    "PWM, הפסדי האינוורטר, תלות הפסדי הברזל בתדר, וקריאת מכשיר true-RMS על צורת גל לא סינוסית."
)


def run_inverter(spec: MotorLike, circuit: CircuitModel, case: InverterCase) -> Outcome:
    base = with_param(circuit, MOTOR, "locked", False)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = [{"code": "fundamental_only", "message": INVERTER_WARNING}]
    for k, pt in enumerate(case.points):
        u = _vf(spec, pt.f, case.U_boost)
        c = with_param(with_param(base, case.source, "U_line", u), case.source, "f", pt.f)
        try:
            op = solve(with_param(c, MOTOR, "M_load", pt.M), spec)
        except StudyError as exc:
            if exc.status != "constraint_violation":
                raise
            # a stalled point ends that frequency's curve; it does not void the other points
            rows.append({"point": k + 1, "f": pt.f, "M_set": pt.M, "state": "נעצר"})
            warnings.append(
                {"code": "stalled", "row": k, "message": f"f = {pt.f:g} Hz: {exc.message}"}
            )
            continue
        rows.append(_row(op, case.bindings, point=k + 1, f=pt.f, M_set=pt.M, state="עובד"))
        warnings += undefined_warnings(op, k, case.bindings) + _op_warnings(op, k)
    rows = derive.inverter(rows, spec)

    # Starting current: DOL at rated U/f versus the inverter at f_start on the V/f law.
    start_rows = []
    for label, f, u in (
        ("ישירות לרשת", spec.nameplate.f_n, spec.nameplate.U_n),
        (f"אינוורטר {case.f_start:g} Hz", case.f_start, _vf(spec, case.f_start, case.U_boost)),
    ):
        c = with_param(with_param(base, case.source, "U_line", u), case.source, "f", f)
        op = solve(with_param(c, MOTOR, "locked", True), spec)
        start_rows.append(
            {
                "mode": label,
                "f": f,
                "U_out": u,
                "I_start": read(op, case.bindings["I_out"]),
                "M_start": _mech(op).get("M_em"),
            }
        )
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "מנוע עם אינוורטר — חוק V/f",
                    "columns": [
                        col("point", "#", ""),
                        col("f", "f", "Hz"),
                        col("U_out", "Vout קווי", "V"),
                        col("I_out", "Iout", "A"),
                        col("M", "M", "N·m"),
                        col("n", "n", "rpm"),
                        col("pf", "cos φ", ""),
                        col("P1", "Pin = 3·P", "W"),
                        col("P2", "Pout = M·n/9.55", "W"),
                        col("eta", "η", ""),
                        col("slip", "s", ""),
                        col("state", "מצב", ""),
                    ],
                    "rows": rows,
                },
                {
                    "id": "starting",
                    "title_he": "זרם התנעה: ישירות לרשת מול אינוורטר בתדר נמוך",
                    "columns": [
                        col("mode", "אופן התנעה", ""),
                        col("f", "f", "Hz"),
                        col("U_out", "U", "V"),
                        col("I_start", "זרם התנעה", "A"),
                        col("M_start", "מומנט התנעה", "N·m"),
                    ],
                    "rows": start_rows,
                },
            ],
            "parameters": [],
            "curves": [
                {"id": "n_m", "title_he": "n = f(M) לכל תדר", "x": "M", "y": "n", "group": "f"},
            ],
        },
    )


def run_dc_resistance(
    spec: MotorSpec, circuits: dict[str, CircuitModel], case: DcResistanceCase
) -> Outcome:
    rows, summary = [], []
    for w, label in WINDINGS:
        circuit = circuits[w]
        r_values = []
        for target in case.I_targets:
            op1 = solve(with_param(circuit, "G", "U", 1.0), spec, dc=True)
            i1 = read(op1, "A.I")
            if not i1:
                raise StudyError("invalid_circuit", f"אין זרם ב{label}")
            op = solve(with_param(circuit, "G", "U", target / i1), spec, dc=True)
            i_m, u_m = read(op, "A.I"), read(op, "V.U")
            assert i_m is not None and u_m is not None
            r_values.append(u_m / i_m)
            rows.append({"winding": label, "I": i_m, "U": u_m, "R": u_m / i_m})
        summary.append({"winding": label, "R_avg": sum(r_values) / len(r_values)})
    return Outcome(
        status="success_with_warnings",
        warnings=[
            {
                "code": "no_temperature_model",
                "message": "ההתנגדות אינה תלויה בטמפרטורה במודל (אין תיקון לטמפרטורת עבודה)",
            }
        ],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 4.2 — התנגדות ליפופי הסטטור בזרם ישר",
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
                    "title_he": "התנגדות ממוצעת לליפוף",
                    "columns": [col("winding", "ליפוף", ""), col("R_avg", "R ממוצע", "Ω")],
                    "rows": summary,
                },
            ],
            "parameters": [],
            "curves": [],
        },
    )


def run_insulation(spec: MotorSpec, case: InsulationCase) -> Outcome:
    ins = spec.insulation
    pairs = (
        ("ליפוף U – מארז (ארקה)", ins.U_frame_Mohm),
        ("ליפוף V – מארז (ארקה)", ins.V_frame_Mohm),
        ("ליפוף W – מארז (ארקה)", ins.W_frame_Mohm),
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
                    "title_he": "טבלה 4.1 — התנגדות בידוד",
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


# --------------------------------------------------------------------------- registry


def _conn(spec: MotorLike) -> Literal["Y", "D"]:
    return spec.nameplate.connection


def _load_default(spec: MotorLike) -> dict[str, Any]:
    mn = spec.M_n
    return {
        "M_targets": [round(k * mn, 3) for k in (0.0, 0.25, 0.5, 0.75, 1.0, 1.15)],
        "U_line": None,
        "torque_speed_curve": True,
    }


def _inverter_default(spec: MotorLike) -> dict[str, Any]:
    mn = spec.M_n
    return {
        "points": [
            {"f": f, "M": round(k * mn, 3)}
            for f in (20, 35, 50, 60)
            for k in (0.25, 0.5, 0.75, 1.0)
        ],
        "law": "V/f",
        "U_boost": 0.0,
        "f_start": 10.0,
    }


STUDIES: dict[str, StudyDef] = {
    s.kind: s
    for s in [
        StudyDef(
            "insulation",
            "בדיקת בידוד (מגר)",
            "בדיקת מצב הבידוד, ציור 4-1, טבלה 4.1",
            InsulationCase,
            lambda spec: {"U_test": 500.0},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "dc_resistance",
            "התנגדות ליפופי הסטטור בזרם ישר",
            "ציור 4-2, טבלה 4.2",
            DcResistanceCase,
            lambda spec: {"I_targets": [0.3, 0.6, 0.9]},
            lambda spec, variant: {w: templates.dc_winding(w) for w, _ in WINDINGS},
            editable_circuit=False,
        ),
        StudyDef(
            "no_load",
            "ניסוי ריקם",
            "ציור 4-3, טבלה 4.4",
            NoLoadCase,
            lambda spec: {"U_line_values": [spec.nameplate.U_n]},
            lambda spec, variant: templates.no_load(
                spec.nameplate.U_n, spec.nameplate.f_n, _conn(spec)
            ),
        ),
        StudyDef(
            "locked_rotor",
            "ניסוי רוטור נעול (קצר)",
            "ציור 4-3, טבלה 4.5",
            LockedRotorCase,
            lambda spec: {"I_targets_pu": [0.4, 0.6, 0.8, 1.0]},
            lambda spec, variant: templates.locked_rotor(
                0.1 * spec.nameplate.U_n, spec.nameplate.f_n, _conn(spec)
            ),
        ),
        StudyDef(
            "load",
            "ניסוי עומס (בלם)",
            "ציור 4-3, טבלה 4.6, ציור 4-4",
            LoadCase,
            _load_default,
            lambda spec, variant: templates.load_test(
                spec.nameplate.U_n, spec.nameplate.f_n, _conn(spec)
            ),
        ),
        StudyDef(
            "inverter",
            "מנוע עם אינוורטר (V/f)",
            "ציור 4-5, טבלת 16 הנקודות",
            InverterCase,
            _inverter_default,
            lambda spec, variant: templates.inverter(
                spec.nameplate.U_n, spec.nameplate.f_n, _conn(spec)
            ),
        ),
    ]
}


STUDIES["dol_start"] = StudyDef(
    "dol_start",
    "התנעה ישירה (סימולציה בזמן)",
    "ציור 4-5: השוואת זרם ההתנעה הישירה לזו שבאינוורטר",
    DolStartCase,
    lambda spec: {"U_line": None, "J": J_ASSUMED, "M_brake": 0.0, "t_end": 1.0, "angle_deg": 0.0},
    None,
    editable_circuit=False,
)


def execute(kind: str, spec: MotorSpec, circuit_doc: Any, case_doc: dict[str, Any]) -> Outcome:
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
        if isinstance(case, InsulationCase):
            return run_insulation(spec, case)
        if isinstance(case, DolStartCase):
            return run_dol_start(spec, case)
        if isinstance(case, DcResistanceCase):
            circuits = {k: CircuitModel.model_validate(v) for k, v in circuit_doc.items()}
            return run_dc_resistance(spec, circuits, case)
        circuit = CircuitModel.model_validate(circuit_doc)
        if isinstance(case, NoLoadCase):
            return run_no_load(spec, circuit, case)
        if isinstance(case, LockedRotorCase):
            return run_locked_rotor(spec, circuit, case)
        if isinstance(case, LoadCase):
            return run_load(spec, circuit, case)
        if isinstance(case, InverterCase):
            return run_inverter(spec, circuit, case)
    except StudyError as f:
        return Outcome(status=f.status, error={"message": f.message, "details": f.details})
    return Outcome(status="unsupported", error={"message": f"study {kind} has no executor"})
