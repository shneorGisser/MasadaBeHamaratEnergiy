"""Study definitions for experiment 4 (wound-rotor induction machine).

No-load, locked-rotor, load and inverter tests reuse the experiment-2 runners: the wound
machine has the same parameters (M_load, locked) and the same readings, so the engineering
code is not duplicated. New here: turns ratio with the rotor open (and turned by hand),
load with an external rotor resistance, the induction regulator, and the machine as an
induction generator on the grid.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine.circuit import CircuitModel
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
from vel.experiments.induction_motor import studies as im
from vel.experiments.wound_rotor import templates
from vel.experiments.wound_rotor.spec import WoundSpec
from vel.experiments.wound_rotor.templates import WINDINGS

MODEL_VERSION = "mna-phasor-1.2+wrim-T-slip-1.0"
MOTOR = "M"


def _status(w: list[dict[str, Any]]) -> Literal["success", "success_with_warnings"]:
    return "success_with_warnings" if w else "success"


class InsulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_test: float = Field(default=500.0, gt=0, le=5000)


class DcResistanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_targets: list[float] = Field(min_length=1, max_length=10)

    @field_validator("I_targets")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x > 50 for x in v):
            raise ValueError("currents must be in (0, 50] A")
        return v


class RatioCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5, description="None → U_n")
    n_hand: float = Field(default=30.0, ge=0, le=1500, description="hand-turning speed [rpm]")


class LoadRextCase(im.LoadCase):
    R_ext: float = Field(gt=0, le=1e5, description="starter resistance per phase [Ω]")


class RegulatorCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float = Field(default=100.0, gt=0, le=1e5)
    angles: list[float] = Field(min_length=1, max_length=73, description="mechanical [°]")

    @field_validator("angles")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or abs(x) > 3600 for x in v):
            raise ValueError("angles must be within ±3600°")
        return v


class GeneratorCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5)
    n_values: list[float] = Field(min_length=1, max_length=40, description="driven speed [rpm]")


# --------------------------------------------------------------------------- runners


def run_insulation(spec: WoundSpec, case: InsulationCase) -> Outcome:
    ins = spec.insulation
    pairs = (
        ("סטטור U – מארז", ins.U_frame_Mohm),
        ("סטטור V – מארז", ins.V_frame_Mohm),
        ("סטטור W – מארז", ins.W_frame_Mohm),
        ("רוטור – מארז", ins.rotor_frame_Mohm),
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


def run_dc_resistance(
    spec: WoundSpec, circuits: dict[str, CircuitModel], case: DcResistanceCase
) -> Outcome:
    rows: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for w, label in WINDINGS:
        vals: list[float] = []
        for target in case.I_targets:
            op1 = solve(with_param(circuits[w], "P", "U", 1.0), spec, dc=True)
            i1 = read(op1, "A.I")
            if not i1:
                raise StudyError("invalid_circuit", f"אין זרם ב{label}")
            op = solve(with_param(circuits[w], "P", "U", target / i1), spec, dc=True)
            i_m, u_m = read(op, "A.I"), read(op, "V.U")
            assert i_m is not None and u_m is not None
            vals.append(u_m / i_m)
            rows.append({"winding": label, "I": i_m, "U": u_m, "R": u_m / i_m})
        summary.append({"winding": label, "R_avg": sum(vals) / len(vals)})
    rotor = [float(s["R_avg"]) for s in summary[3:]]
    params = [
        Param(
            "R2_phase",
            "התנגדות פאזת רוטור",
            sum(rotor) / len(rotor) / 2,
            "Ω",
            "R(בין טבעות) / 2",
            "consistent",
            note="כוכב פנימי: בין שתי טבעות נמדדות שתי פאזות בטור",
        )
    ]
    return Outcome(
        status="success_with_warnings",
        warnings=[{"code": "no_temperature_model", "message": "אין תלות טמפרטורה במודל"}],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 4.2 — התנגדות ליפופים בזרם ישר",
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


def run_ratio(spec: WoundSpec, circuit: CircuitModel, case: RatioCase) -> Outcome:
    u = case.U_line or spec.nameplate.U_n
    base = with_param(circuit, "G", "U_line", u)
    rows: list[dict[str, Any]] = []
    for label, n in (
        ("רוטור נח", 0.0),
        ("מסובב בכיוון השדה", case.n_hand),
        ("מסובב נגד השדה", -case.n_hand),
    ):
        op = solve(
            with_param(with_param(base, MOTOR, "speed_mode", "speed"), MOTOR, "n_set", n), spec
        )
        u1, u2 = read(op, "V1.U"), read(op, "V2.U")
        rows.append(
            {
                "state": label,
                "n": n,
                "U1": u1,
                "U2": u2,
                "k": (u1 / u2) if (u1 and u2) else None,
                "f2": op.readings[MOTOR].get("f_rotor"),
            }
        )
    k0 = rows[0]["k"]
    assert k0 is None or isinstance(k0, float)
    params = [
        Param("k", "מקדם השנאה k = U1/U2 (רוטור נח)", k0, "", "U1 / U2", "consistent"),
        Param(
            "k_turns",
            "יחס הכריכות האפקטיבי במודל",
            spec.ecm.k,
            "",
            "E1/E2",
            "analytic",
            note="k הנמדד גדול ממנו מעט: מפל המתח של זרם המגנוט על R1 + jX1",
        ),
    ]
    return Outcome(
        status="success",
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 4.3 — מקדם השנאה (רוטור פתוח)",
                    "columns": [
                        col("state", "מצב", ""),
                        col("n", "n", "rpm"),
                        col("U1", "U1", "V"),
                        col("U2", "U2 (רוטור)", "V"),
                        col("k", "k = U1/U2", ""),
                        col("f2", "תדר ברוטור", "Hz"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [],
        },
    )


def run_load_rext(spec: WoundSpec, circuit: CircuitModel, case: LoadRextCase) -> Outcome:
    c = with_param(circuit, "Rst", "value", case.R_ext)
    base = im.LoadCase.model_validate(case.model_dump(exclude={"R_ext"}))
    out = im.run_load(spec, c, base)
    if out.result is not None:
        out.result["tables"][0]["title_he"] = (
            f"טבלה 4.7 — עומס עם נגד נוסף ברוטור ({case.R_ext:g} Ω לפאזה)"
        )
    return out


def run_regulator(spec: WoundSpec, circuit: CircuitModel, case: RegulatorCase) -> Outcome:
    base = with_param(circuit, "G", "U_line", case.U_line)
    pp = spec.nameplate.poles / 2
    rows = []
    for a in case.angles:
        op = solve(with_param(base, MOTOR, "angle", a), spec)
        rows.append(
            {
                "angle": a,
                "angle_e": (pp * a) % 360,
                "U1": read(op, "V1.U"),
                "U2": read(op, "V2.U"),
            }
        )
    u2 = [r["U2"] for r in rows if r["U2"] is not None]
    params = []
    if u2:
        params = [
            Param("U2_min", "מתח יציאה מינימלי", min(u2), "V", "min U2(α)", "consistent"),
            Param("U2_max", "מתח יציאה מרבי", max(u2), "V", "max U2(α)", "consistent"),
        ]
    return Outcome(
        status="success",
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "טבלה 5.1 — מכונת השראה כווסת מתח",
                    "columns": [
                        col("angle", "α גאומטרית", "°"),
                        col("angle_e", "α חשמלית = p·α", "°"),
                        col("U1", "U1", "V"),
                        col("U2", "U2", "V"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [{"id": "reg", "title_he": "U2 = f(α)", "x": "angle", "y": "U2"}],
        },
    )


def run_generator(spec: WoundSpec, circuit: CircuitModel, case: GeneratorCase) -> Outcome:
    u = case.U_line or spec.nameplate.U_n
    base = with_param(with_param(circuit, "G", "U_line", u), MOTOR, "speed_mode", "speed")
    rows = []
    for n in case.n_values:
        op = solve(with_param(base, MOTOR, "n_set", n), spec)
        p_w, q_w = read(op, "W.P"), read(op, "W.Q")
        rows.append(
            {
                "n": n,
                "slip": op.readings[MOTOR]["s"],
                "I1": read(op, "A.I"),
                "P1": 3 * p_w if p_w is not None else None,
                "Q1": 3 * q_w if q_w is not None else None,
                "pf": read(op, "W.pf"),
                "M": op.readings[MOTOR]["M"],
                "mode": "מחולל" if (p_w or 0) < 0 else "מנוע",
            }
        )
    return Outcome(
        status="success_with_warnings",
        warnings=[
            {
                "code": "sign_convention",
                "message": "P1 שלילי = הספק מוחזר לרשת; Q1 חיובי = המכונה צורכת הספק היגבי "
                "גם כמחולל (מכונת השראה אינה יכולה לספק את עירורה בעצמה)",
            }
        ],
        result={
            "tables": [
                {
                    "id": "readings",
                    "title_he": "מכונת השראה כמחולל במקביל לרשת",
                    "columns": [
                        col("n", "n", "rpm"),
                        col("slip", "s", ""),
                        col("I1", "I1", "A"),
                        col("P1", "P1 = 3·P", "W"),
                        col("Q1", "Q1 = 3·Q", "var"),
                        col("pf", "cos φ", ""),
                        col("M", "M בציר", "N·m"),
                        col("mode", "אופן", ""),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [],
            "curves": [
                {"id": "p", "title_he": "P1 = f(n)", "x": "n", "y": "P1"},
                {"id": "m", "title_he": "M = f(n)", "x": "n", "y": "M"},
            ],
        },
    )


# --------------------------------------------------------------------------- registry


def _conn(spec: WoundSpec) -> Literal["Y", "D"]:
    return spec.nameplate.connection


def _load_default(spec: WoundSpec) -> dict[str, Any]:
    # up to rated torque only: the nameplate fit has a pull-out torque of just ~1.1·M_n
    mn = spec.M_n
    return {
        "M_targets": [round(k * mn, 3) for k in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)],
        "U_line": None,
        "torque_speed_curve": True,
    }


def _inverter_default(spec: WoundSpec) -> dict[str, Any]:
    mn = spec.M_n
    return {
        "points": [
            {"f": f, "M": round(k * mn, 3)} for f in (20, 35, 50, 60) for k in (0.2, 0.4, 0.6, 0.8)
        ],
        "law": "V/f",
        "U_boost": 0.0,
        "f_start": 10.0,
    }


def _motor(spec: WoundSpec, **kw: Any) -> CircuitModel:
    return templates.motor(spec.nameplate.U_n, spec.nameplate.f_n, _conn(spec), **kw)


STUDIES: dict[str, StudyDef] = {
    s.kind: s
    for s in [
        StudyDef(
            "insulation",
            "בדיקת בידוד (מגר)",
            "ציור 4-1, טבלה 4.1",
            InsulationCase,
            lambda spec: {"U_test": 500.0},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "dc_resistance",
            "התנגדות ליפופי סטטור ורוטור",
            "ציור 4-2, טבלה 4.2",
            DcResistanceCase,
            lambda spec: {"I_targets": [0.2, 0.4, 0.6]},
            lambda spec, v: {w: templates.dc_winding(w) for w, _ in WINDINGS},
            editable_circuit=False,
        ),
        StudyDef(
            "ratio",
            "מקדם השנאה (רוטור פתוח)",
            "ציור 4-3, טבלה 4.3",
            RatioCase,
            lambda spec: {"U_line": None, "n_hand": 30.0},
            lambda spec, v: templates.rotor_open(
                spec.nameplate.U_n, spec.nameplate.f_n, _conn(spec)
            ),
        ),
        StudyDef(
            "no_load",
            "ניסוי ריקם",
            "טבלה 4.4",
            im.NoLoadCase,
            lambda spec: {"U_line_values": [spec.nameplate.U_n]},
            lambda spec, v: _motor(spec),
        ),
        StudyDef(
            "locked_rotor",
            "ניסוי קצר (רוטור נעול)",
            "טבלה 4.5",
            im.LockedRotorCase,
            lambda spec: {"I_targets_pu": [0.4, 0.6, 0.8, 1.0]},
            lambda spec, v: templates.motor(
                0.1 * spec.nameplate.U_n, spec.nameplate.f_n, _conn(spec), locked=True
            ),
        ),
        StudyDef(
            "load",
            "ניסוי עומס (מתנע באפס)",
            "טבלה 4.6",
            im.LoadCase,
            _load_default,
            lambda spec, v: _motor(spec),
        ),
        StudyDef(
            "load_rext",
            "עומס עם נגד נוסף ברוטור",
            "טבלה 4.7",
            LoadRextCase,
            lambda spec: {**_load_default(spec), "R_ext": 3.0},
            lambda spec, v: _motor(spec, r_ext=3.0),
        ),
        StudyDef(
            "regulator",
            "מכונת השראה כווסת מתח",
            "ציור 4-6, טבלה 5.1",
            RegulatorCase,
            lambda spec: {"U_line": 100.0, "angles": [float(a) for a in range(0, 361, 45)]},
            lambda spec, v: templates.regulator(100.0, spec.nameplate.f_n),
        ),
        StudyDef(
            "generator",
            "מחולל במקביל לרשת",
            "ציור 4-8",
            GeneratorCase,
            lambda spec: {
                "U_line": None,
                "n_values": [1490.0, 1500.0, 1510.0, 1520.0, 1540.0, 1560.0, 1580.0],
            },
            lambda spec, v: _motor(spec),
        ),
        StudyDef(
            "inverter",
            "מנוע עם אינוורטר (V/f)",
            "ממיר AC/AC, טבלת 16 הנקודות",
            im.InverterCase,
            _inverter_default,
            lambda spec, v: _motor(spec, label="אינוורטר (יסודית)"),
        ),
    ]
}


def execute(kind: str, spec: WoundSpec, circuit_doc: Any, case_doc: dict[str, Any]) -> Outcome:
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
        if isinstance(case, DcResistanceCase):
            circuits = {k: CircuitModel.model_validate(v) for k, v in circuit_doc.items()}
            return run_dc_resistance(spec, circuits, case)
        circuit = CircuitModel.model_validate(circuit_doc)
        if isinstance(case, LoadRextCase):
            return run_load_rext(spec, circuit, case)
        runners: dict[type, Any] = {
            RatioCase: run_ratio,
            RegulatorCase: run_regulator,
            GeneratorCase: run_generator,
            im.NoLoadCase: im.run_no_load,
            im.LockedRotorCase: im.run_locked_rotor,
            im.LoadCase: im.run_load,
            im.InverterCase: im.run_inverter,
        }
        fn = runners.get(type(case))
        if fn is not None:
            out: Outcome = fn(spec, circuit, case)
            return out
    except StudyError as f:
        return Outcome(status=f.status, error={"message": f.message, "details": f.details})
    return Outcome(status="unsupported", error={"message": f"study {kind} has no executor"})
