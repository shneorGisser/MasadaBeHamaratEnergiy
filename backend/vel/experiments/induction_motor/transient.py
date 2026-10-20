"""Studies: starting the induction motor in the time domain (direct-on-line, star-delta).

The transient model (vel.engine.transient.induction) and the steady-state phasor model share the
spec. Each study reports how far the transient's final state is from the steady-state solver's
answer for the same machine and brake — the self-consistency check of the two engines — and
how much the neglected iron loss moves that answer.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vel.engine.simulate import operating_point
from vel.engine.transient.induction import StartResult, dol_start, star_delta_start
from vel.experiments.common import Outcome, Param, StudyError
from vel.experiments.induction_motor import templates
from vel.experiments.induction_motor.spec import MotorSpec
from vel.experiments.transient_common import start_outcome

# rotor + coupling + brake [kg·m²]: not on any nameplate. A 0.37 kW 4-pole rotor is ≈ 1e-3;
# the powder brake and coupling are assumed to double it.
J_ASSUMED = 0.003


class DolStartCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5)
    J: float = Field(default=J_ASSUMED, gt=0, le=1e4)
    M_brake: float = Field(default=0.0, ge=0, le=1e4)
    t_end: float = Field(default=1.0, gt=0, le=10.0)
    angle_deg: float = Field(default=0.0, ge=-360, le=360)


class StarDeltaCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_line: float | None = Field(default=None, gt=0, le=1e5)
    J: float = Field(default=J_ASSUMED, gt=0, le=1e4)
    M_brake: float = Field(default=0.0, ge=0, le=1e4)
    t_switch: float = Field(default=0.5, gt=0, le=10.0)
    t_dead: float = Field(default=0.05, ge=0, le=1.0)
    t_end: float = Field(default=1.2, gt=0, le=10.0)
    angle_deg: float = Field(default=0.0, ge=-360, le=360)

    @model_validator(mode="after")
    def _order(self) -> StarDeltaCase:
        if self.t_switch + self.t_dead >= self.t_end:
            raise ValueError("t_switch + t_dead must be before t_end")
        return self


def _reference(
    spec: MotorSpec, u: float, conn: Literal["Y", "D"], m: float
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Steady state of the same machine from the phasor solver, without and with iron loss."""
    no_fe = spec.model_copy(update={"ecm": spec.ecm.model_copy(update={"R_fe": 1e9})})
    circ = templates.load_test(u, spec.nameplate.f_n, conn, m_load=m)
    ref: dict[str, float] = {}
    warnings: list[dict[str, Any]] = []
    for key, sp in (("no_fe", no_fe), ("full", spec)):
        try:
            op = operating_point(circ, sp)
            ref[f"n_{key}"] = float(op.readings["M"]["n"] or 0.0)
            ref[f"I_{key}"] = float(op.readings["A"]["I"] or 0.0)
        except Exception as exc:  # noqa: BLE001 — a stalled steady state is a finding, not a crash
            warnings.append({"code": "no_steady_state", "message": f"אין נקודת עבודה יציבה: {exc}"})
    return ref, warnings


def _run(fn: Any, **kw: Any) -> StartResult:
    try:
        r: StartResult = fn(**kw)
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    return r


def run_dol_start(spec: MotorSpec, case: DolStartCase) -> Outcome:
    npl = spec.nameplate
    u = case.U_line or npl.U_n
    conn = npl.connection
    r = _run(
        dol_start,
        spec=spec,
        U_line=u,
        f=npl.f_n,
        connection=conn,
        J=case.J,
        M_brake=case.M_brake,
        t_end=case.t_end,
        angle_deg=case.angle_deg,
    )
    ref, ref_w = _reference(spec, u, conn, case.M_brake)
    return start_outcome(
        r,
        title=f"התנעה ישירה ב-{u:.0f} V ({conn}), J = {case.J:g} kg·m², בלם {case.M_brake:g} N·m",
        t_end=case.t_end,
        J=case.J,
        J_assumed=J_ASSUMED,
        ref=ref,
        ref_warnings=ref_w,
    )


def run_star_delta(spec: MotorSpec, case: StarDeltaCase) -> Outcome:
    """Star-delta needs windings rated for the line voltage: the default supply is the rated
    WINDING voltage, so that the windings are at their rating once in Δ."""
    npl = spec.nameplate
    u = case.U_line or spec.U_winding
    extra_w: list[dict[str, Any]] = []
    if u > spec.U_winding * 1.05:
        extra_w.append(
            {
                "code": "winding_overvoltage",
                "message": f"במשולש כל ליפוף מקבל {u:g} V — מעל המתח הנקוב לליפוף "
                f"({spec.U_winding:.0f} V). כוכב-משולש מתאים רק למנוע שמתח המשולש שלו הוא "
                "מתח הרשת",
            }
        )
    r = _run(
        star_delta_start,
        spec=spec,
        U_line=u,
        f=npl.f_n,
        J=case.J,
        t_switch=case.t_switch,
        t_dead=case.t_dead,
        M_brake=case.M_brake,
        t_end=case.t_end,
        angle_deg=case.angle_deg,
    )
    # how far the motor got in star before the changeover
    k_sw = int(min(len(r.t) - 1, max(0, round(case.t_switch / (r.t[1] - r.t[0])) - 1)))
    n_sw = float(r.n[k_sw])
    after = r.t > case.t_switch + case.t_dead
    i_reclose = float(max(abs(r.i_line[after][:200]))) if after.any() else math.nan
    ref_y, _ = _reference(spec, u, "Y", case.M_brake)
    if ref_y.get("n_no_fe") and n_sw < 0.9 * ref_y["n_no_fe"]:
        extra_w.append(
            {
                "code": "early_changeover",
                "message": f"המעבר למשולש ב-{n_sw:.0f} סל״ד, לפני שהמנוע הגיע למהירות "
                f"הכוכב ({ref_y['n_no_fe']:.0f} סל״ד) — קפיצת הזרם במעבר תהיה גדולה",
            }
        )
    ref, ref_w = _reference(spec, u, "D", case.M_brake)
    return start_outcome(
        r,
        title=f"כוכב-משולש ב-{u:.0f} V: מעבר ב-{case.t_switch:g} s, "
        f"ניתוק {case.t_dead * 1000:g} ms",
        t_end=case.t_end,
        J=case.J,
        J_assumed=J_ASSUMED,
        ref=ref,
        ref_warnings=ref_w,
        extra_warnings=extra_w,
        extra_params=[
            Param("n_switch", "מהירות ברגע המעבר", n_sw, "rpm", "", "analytic"),
            Param(
                "I_reclose",
                "שיא הזרם בחיבור המשולש",
                i_reclose,
                "A",
                "max|i_L1| אחרי המעבר",
                "analytic",
                note="תלוי בזמן הניתוק ובפאזה של שטף הרוטור שנשאר",
            ),
        ],
    )
