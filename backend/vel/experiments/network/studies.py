"""Studies of the network module: load flow and IEC 60909 short circuit.

Each study runs pandapower (reported) and our own solver (vel.engine.network.direct); the
largest relative difference between them is a parameter of every run, and a difference above
1e-6 is an `engines_disagree` warning."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vel.engine.network import direct, pp_model
from vel.experiments.common import Outcome, Param, StudyDef, StudyError, col
from vel.experiments.network.spec import BUS_LABELS, BUSES, NetworkSpec

MODEL_VERSION = "pandapower-3.5+net-direct-1.0"
TOL = 1e-6
DU_MAX = 4.0  # % — the IEC 60364-5-52 (Annex G) recommendation for other uses than lighting
ASSUMED = (
    "כל נתוני הרשת מוערכים (לא נמדדו): הם מדגימים את השיטה ואת סדרי הגודל, לא את המעבדה האמיתית"
)
BRANCH_LABELS = {"T": "שנאי מ״ג/מ״נ", "C1": "כבל ראשי B1–B2", "C2": "כבל לעמדה B2–B3"}


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-12)


def _scaled(spec: NetworkSpec, k: float) -> NetworkSpec:
    lo = spec.loads
    return spec.model_copy(
        update={"loads": lo.model_copy(update={"P2_kW": lo.P2_kW * k, "P3_kW": lo.P3_kW * k})}
    )


class LoadFlowCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scales: list[float] = Field(
        default_factory=lambda: [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5],
        min_length=1,
        max_length=20,
        description="multiples of the spec loads",
    )


class ShortCircuitCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_k: float = Field(default=1.0, gt=0, le=10, description="duration for I_th [s]")


def run_load_flow(spec: NetworkSpec, case: LoadFlowCase) -> Outcome:
    if any(not (0 <= k <= 10) for k in case.scales):
        raise StudyError("invalid_input", "מקדמי העומס חייבים להיות בין 0 ל-10")
    u_lv = spec.trafo.U2_V
    sweep: list[dict[str, Any]] = []
    dev = 0.0
    nominal: tuple[Any, Any] | None = None
    warnings: list[dict[str, Any]] = [{"code": "assumed_network", "message": ASSUMED}]
    for k in sorted(set([*case.scales, 1.0])):
        sp = _scaled(spec, k)
        try:
            pp_r = pp_model.load_flow(sp)
            dr = direct.load_flow(sp)
        except Exception as exc:  # noqa: BLE001 — a diverged load flow is a finding
            warnings.append(
                {
                    "code": "no_convergence",
                    "message": f"פי {k:g} מהעומס: זרימת העומס לא התכנסה ({exc})",
                }
            )
            continue
        dev = max(
            dev,
            *(float(abs(pp_r.U[b] - dr.U[b])) for b in BUSES),
            *(
                _rel(dr.I_branch[x], pp_r.I_branch[x])
                for x in BRANCH_LABELS
                if pp_r.I_branch[x] > 1e-9
            ),
        )
        if k == 1.0:
            nominal = (pp_r, dr)
        if k in case.scales:
            sweep.append(
                {
                    "k": k,
                    "P_kW": (spec.loads.P2_kW + spec.loads.P3_kW) * k,
                    **{f"u_{b}": 100 * abs(pp_r.U[b]) for b in BUSES[1:]},
                    "loss": pp_r.P_loss_kW,
                }
            )
    if nominal is None:
        raise StudyError("convergence_failure", "זרימת העומס בעומס הנקוב לא התכנסה")
    pp_r, dr = nominal
    if dev > TOL:
        warnings.append(
            {
                "code": "engines_disagree",
                "message": f"pandapower והפותר הישיר נבדלים ב-{dev:.2e} — טעות במודל או בנתונים",
            }
        )
    bus_rows = []
    for b in BUSES:
        v = pp_r.U[b]
        un = spec.grid.U_n_kV * 1e3 if b == "B0" else u_lv
        bus_rows.append(
            {
                "bus": f"{b} — {BUS_LABELS[b]}",
                "U": abs(v) * un,
                "u_pct": 100 * abs(v),
                "du": 100 * (1 - abs(v)),
                "angle": math.degrees(math.atan2(v.imag, v.real)),
            }
        )
    du_b3 = 100 * (1 - abs(pp_r.U["B3"]))
    if du_b3 > DU_MAX:
        warnings.append(
            {
                "code": "voltage_drop",
                "message": f"מפל המתח לעמדה {du_b3:.2f} % — מעל {DU_MAX:g} % "
                "(המלצת IEC 60364-5-52)",
            }
        )
    branch_rows = []
    for x, label in BRANCH_LABELS.items():
        branch_rows.append({"branch": label, "I": pp_r.I_branch[x], "loading": pp_r.loading[x]})
        if pp_r.loading[x] > 100:
            warnings.append(
                {
                    "code": "overload",
                    "message": f"{label}: עומס {pp_r.loading[x]:.0f} % מהנקוב",
                }
            )
    params = [
        Param("dU_B3", "מפל מתח עד העמדה", du_b3, "%", "1 − |U_B3|/U_n", "analytic"),
        Param("P_loss", "הפסדים בשנאי ובכבלים", pp_r.P_loss_kW, "kW", "", "analytic"),
        Param("I_T", "זרם השנאי (צד מ״נ)", pp_r.I_branch["T"], "A", "", "analytic"),
        Param(
            "engines_dev",
            "הפרש בין pandapower לפותר הישיר",
            dev,
            "",
            "max |ΔU| [pu], max ΔI/I",
            "analytic",
            note="שני מימושים בלתי תלויים של אותן משוואות; ההפרש צריך להיות ברמת השגיאה הנומרית",
        ),
    ]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "buses",
                    "title_he": "מתחי הצמתים בעומס הנקוב",
                    "columns": [
                        col("bus", "צומת", ""),
                        col("U", "U קווי", "V"),
                        col("u_pct", "U", "%"),
                        col("du", "מפל מתח", "%"),
                        col("angle", "זווית", "°"),
                    ],
                    "rows": bus_rows,
                },
                {
                    "id": "branches",
                    "title_he": "זרמים והעמסה",
                    "columns": [
                        col("branch", "ענף", ""),
                        col("I", "I", "A"),
                        col("loading", "העמסה", "%"),
                    ],
                    "rows": branch_rows,
                },
                {
                    "id": "sweep",
                    "title_he": "מתחים כפונקציה של העומס",
                    "columns": [
                        col("k", "פי העומס", ""),
                        col("P_kW", "P כולל", "kW"),
                        col("u_B1", "U B1", "%"),
                        col("u_B2", "U B2", "%"),
                        col("u_B3", "U B3", "%"),
                        col("loss", "הפסדים", "kW"),
                    ],
                    "rows": sweep,
                },
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [
                {
                    "id": "u",
                    "title_he": "מתח הצמתים מול העומס",
                    "x": "P_kW",
                    "y": "u_B1",
                    "y2": "u_B2",
                    "y3": "u_B3",
                    "table": "sweep",
                },
                {
                    "id": "loss",
                    "title_he": "הפסדים מול העומס",
                    "x": "P_kW",
                    "y": "loss",
                    "table": "sweep",
                },
            ],
        },
    )


def run_short_circuit(spec: NetworkSpec, case: ShortCircuitCase) -> Outcome:
    try:
        res = {
            c: (pp_model.short_circuit(spec, c, case.t_k), direct.short_circuit(spec, c, case.t_k))
            for c in ("max", "min")
        }
    except Exception as exc:  # noqa: BLE001
        raise StudyError("convergence_failure", f"חישוב הקצר נכשל: {exc}") from exc
    dev = max(
        _rel(getattr(d, q)[b], getattr(p, q)[b])
        for p, d in res.values()
        for q in ("Ik3", "ip", "Ith", "Ik1")
        for b in BUSES
    )
    warnings: list[dict[str, Any]] = [{"code": "assumed_network", "message": ASSUMED}]
    if dev > TOL:
        warnings.append(
            {
                "code": "engines_disagree",
                "message": f"pandapower והפותר הישיר נבדלים ב-{dev:.2e} — טעות במודל או בנתונים",
            }
        )
    pmax, dmax = res["max"]
    pmin, dmin = res["min"]
    u0 = spec.trafo.U2_V / math.sqrt(3)
    rows = []
    for b in BUSES:
        z1, z0 = dmax.Z1[b], dmax.Z0[b]
        rows.append(
            {
                "bus": f"{b} — {BUS_LABELS[b]}",
                "Ik3_max": pmax.Ik3[b],
                "Ik3_min": pmin.Ik3[b],
                "ip": pmax.ip[b],
                "Ith": pmax.Ith[b],
                "Ik1_max": pmax.Ik1[b],
                "Ik1_min": pmin.Ik1[b],
                "R_X": z1.real / z1.imag,
                "Z_loop": None if b == "B0" else abs(2 * z1 + z0) / 3,
            }
        )
    zl_b3 = abs(2 * dmax.Z1["B3"] + dmax.Z0["B3"]) / 3
    params = [
        Param(
            "Ik3_B3", "I''k3 מרבי בעמדה", pmax.Ik3["B3"], "kA", "c_max·U_n/(√3·|Z_k|)", "analytic"
        ),
        Param(
            "Ik1_min_B3",
            "I''k1 מזערי בעמדה",
            pmin.Ik1["B3"],
            "kA",
            "√3·c_min·U_n/|2Z1 + Z0|",
            "analytic",
            note="קובע אם ההגנה תנתק תקלה לאדמה",
        ),
        Param(
            "ip_B1",
            "זרם הלם בלוח הראשי",
            pmax.ip["B1"],
            "kA",
            "κ·√2·I''k",
            "analytic",
            note="קובע את כושר הסגירה הנדרש של המפסקים",
        ),
        Param(
            "Z_loop_B3",
            "עכבת לולאת L-PE בעמדה (מודל)",
            zl_b3,
            "Ω",
            "|2Z1 + Z0|/3",
            "analytic",
            note=f"מול מכשיר בדיקת המתקן: I = U0/Z = {u0 / zl_b3:.0f} A",
        ),
        Param(
            "engines_dev",
            "הפרש בין pandapower לפותר הישיר",
            dev,
            "",
            "max ΔI/I",
            "analytic",
            note="שני מימושים בלתי תלויים של IEC 60909-0",
        ),
    ]
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "sc",
                    "title_he": "זרמי קצר לפי IEC 60909-0",
                    "columns": [
                        col("bus", "צומת", ""),
                        col("Ik3_max", "I''k3 מרבי", "kA"),
                        col("Ik3_min", "I''k3 מזערי", "kA"),
                        col("ip", "i_p", "kA"),
                        col("Ith", f"I_th ({case.t_k:g} s)", "kA"),
                        col("Ik1_max", "I''k1 מרבי", "kA"),
                        col("Ik1_min", "I''k1 מזערי", "kA"),
                        col("R_X", "R/X", ""),
                        col("Z_loop", "Z לולאה", "Ω"),
                    ],
                    "rows": rows,
                }
            ],
            "parameters": [p.to_json() for p in params],
            "curves": [],
        },
    )


STUDIES: dict[str, StudyDef] = {
    "load_flow": StudyDef(
        "load_flow",
        "זרימת עומסים",
        "מודול רשת: מפלי מתח, העמסה והפסדים",
        LoadFlowCase,
        lambda spec: {"scales": [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]},
        None,
        editable_circuit=False,
    ),
    "short_circuit": StudyDef(
        "short_circuit",
        "זרמי קצר (IEC 60909)",
        "מודול רשת: קצר תלת-פאזי וחד-פאזי לאדמה בכל צומת",
        ShortCircuitCase,
        lambda spec: {"t_k": 1.0},
        None,
        editable_circuit=False,
    ),
}
_RUN = {"load_flow": run_load_flow, "short_circuit": run_short_circuit}


def execute(kind: str, spec: NetworkSpec, circuit_doc: Any, case_doc: dict[str, Any]) -> Outcome:
    sd = STUDIES.get(kind)
    if sd is None:
        return Outcome(status="unsupported", error={"message": f"unknown study {kind}"})
    try:
        case = sd.case_model.model_validate(case_doc or {})
    except Exception as exc:  # noqa: BLE001
        return Outcome(
            status="invalid_input", error={"message": "פרמטרי הניסוי שגויים", "details": str(exc)}
        )
    try:
        out: Outcome = _RUN[kind](spec, case)  # type: ignore[operator]
    except StudyError as exc:
        return Outcome(status=exc.status, error={"message": exc.message, "details": exc.details})
    return out
