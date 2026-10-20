"""Study: starting the wound-rotor machine through a rotor starter, in the time domain.

The starter adds a resistance per phase on the slip rings. Referred to the stator it adds
k²·R_st to R2' — so the starting torque rises (up to the pull-out torque when
R2' + k²·R_st ≈ X1 + X2') while the starting current falls. The starter is cut out in steps;
each step is a segment of the event-segmented integration (vel.engine.transient.induction).
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine.simulate import operating_point
from vel.engine.transient.induction import ImParams, Segment, StartResult, simulate
from vel.experiments.common import Outcome, Param, StudyError
from vel.experiments.transient_common import start_outcome
from vel.experiments.wound_rotor import templates
from vel.experiments.wound_rotor.spec import WoundSpec

# rotor + coupling + brake [kg·m²], not on the nameplate (the lab machine is ≈ 1 kW)
J_ASSUMED = 0.01
SQ3 = math.sqrt(3)


class StarterStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    R: float = Field(ge=0, le=1e4, description="starter resistance per phase, actual [Ω]")
    t: float = Field(gt=0, le=10, description="time at which this step ends [s]")


class StarterCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[StarterStep] = Field(min_length=1, max_length=10)
    J: float = Field(default=J_ASSUMED, gt=0, le=1e4)
    M_brake: float = Field(default=0.0, ge=0, le=1e4)
    angle_deg: float = Field(default=0.0, ge=-360, le=360)

    @field_validator("points")
    @classmethod
    def _increasing(cls, v: list[StarterStep]) -> list[StarterStep]:
        if any(b.t <= a.t for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("step end times must increase")
        return v


def im_params(spec: WoundSpec) -> ImParams:
    e, n = spec.ecm, spec.nameplate
    w_n = 2 * math.pi * n.n_n / 60
    return ImParams(
        e.R1, e.X1, spec.R2_referred, spec.X2_referred, e.Xm, n.f_n, n.poles, e.P_fw_n / w_n**2
    )


def default_steps(spec: WoundSpec) -> list[dict[str, float]]:
    """First step: the resistance that puts the pull-out torque at standstill
    (R2' + k²·R_st = X1 + X2'), then half of it, then the rings shorted."""
    e = spec.ecm
    r1 = max(0.0, (e.X1 + spec.X2_referred - spec.R2_referred) / e.k**2)
    r1 = round(r1, 2)
    return [{"R": r1, "t": 0.4}, {"R": round(r1 / 2, 2), "t": 0.8}, {"R": 0.0, "t": 1.5}]


def run_starter(spec: WoundSpec, case: StarterCase) -> Outcome:
    npl = spec.nameplate
    u = npl.U_n
    conn = npl.connection
    u_w = u if conn == "D" else u / SQ3
    phase = case.angle_deg + (30.0 if conn == "D" else 0.0)
    k2 = spec.ecm.k**2
    segs = [
        Segment(p.t, u_w, phase, conn, R2_extra=k2 * p.R, label=f"מתנע {p.R:g} Ω")
        for p in case.points
    ]
    try:
        r: StartResult = simulate(im_params(spec), segs, f=npl.f_n, J=case.J, M_brake=case.M_brake)
    except RuntimeError as exc:
        raise StudyError("convergence_failure", str(exc)) from exc
    # starting torque of each step at standstill (from the first samples of the first step)
    m0 = float(max(r.M_em[: max(1, int(0.05 / (r.t[1] - r.t[0])))]))
    # the steady state with the last step's resistance, from the phasor solver
    last_r = case.points[-1].R
    no_fe = spec.model_copy(update={"ecm": spec.ecm.model_copy(update={"R_fe": 1e9})})
    ref: dict[str, float] = {}
    ref_w: list[dict[str, Any]] = []
    for key, sp in (("no_fe", no_fe), ("full", spec)):
        circ = templates.motor(u, npl.f_n, conn, r_ext=last_r if last_r > 0 else None)
        circ.component("M").params["M_load"] = case.M_brake
        try:
            op = operating_point(circ, sp)
            ref[f"n_{key}"] = float(op.readings["M"]["n"] or 0.0)
            ref[f"I_{key}"] = float(op.readings["A"]["I"] or 0.0)
        except Exception as exc:  # noqa: BLE001 — a stalled steady state is a finding
            ref_w.append({"code": "no_steady_state", "message": f"אין נקודת עבודה יציבה: {exc}"})
    steps = ", ".join(f"{p.R:g} Ω עד {p.t:g} s" for p in case.points)
    return start_outcome(
        r,
        title=f"התנעה דרך מתנע רוטור ({steps}), J = {case.J:g} kg·m²",
        t_end=case.points[-1].t,
        J=case.J,
        J_assumed=J_ASSUMED,
        ref=ref,
        ref_warnings=ref_w,
        extra_params=[
            Param(
                "M_start",
                "מומנט התנעה (שלב ראשון)",
                m0,
                "N·m",
                "max M_em ב-50 ms הראשונות",
                "analytic",
                note="כולל תנודת המומנט של רכיב ה-DC בזרם",
            ),
        ],
    )
