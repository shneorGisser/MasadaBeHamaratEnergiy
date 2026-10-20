"""DC machine in the time domain: shunt-generator voltage build-up and shunt-motor start.

The magnetic model is the steady-state one (vel.experiments.dc_machine.spec): the field MMF in
shunt-field amperes F = I_f − k_ar·|I_a| + F_res and the EMF E = (n/n_ref)·OCC(F). The time
domain adds what the steady state does not need:

* Field inductance. The field flux follows the OCC, so the incremental inductance saturates
  with it: L_f(F) = L_f0·OCC'(F)/a (L_f0 = unsaturated inductance, a = air-gap slope).
  The coupling of the armature-reaction term into the field circuit is neglected.
* Armature inductance L_a (constant).
* Inertia J (motor). Friction as in the steady state: P_rot ∝ |n|^k_rot.

Neither inductance nor J is on the nameplate — the studies say so.

Build-up (generator, servo at constant speed, load switch open, short shunt):
    (L_a + L_f(F))·di/dt = E(F) − (R_a + R_f + R_rheo)·i − U_b·tanh(i/I_b),   i = I_f = I_a
It starts from the remanence (i = 0, E = r·OCC(F_res)) and either builds up to the stable
root of the steady-state equation or, above the critical field resistance, stays near the
remanent voltage — the same answer the steady-state solver gives, now with its time course.

Motor start (shunt motor, supply U switched onto armature and field together, armature
starter R_st in steps, brake M_brake):
    L_a·di_a/dt = U − E(F, n) − (R_a + R_st)·i_a − U_b·tanh(i_a/I_b)
    L_f(F)·di_f/dt = U − (R_f + R_rheo)·i_f
    J·dω/dt = OCC(F)/ω_ref·i_a − M_fric(n) − M_brake·tanh(ω/ω_ε)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from vel.experiments.dc_machine.spec import DCSpec

FArray = npt.NDArray[np.float64]
I_BRUSH = 0.05  # A: the steady-state model's brush-drop smoothing current
W_EPS = 0.5  # rad/s


def _l_inc(spec: DCSpec, f: float, l_f0: float) -> float:
    """Incremental field inductance from the slope of the OCC (central difference)."""
    h = 1e-5
    d = (spec.occ.emf(f + h) - spec.occ.emf(f - h)) / (2 * h)
    return l_f0 * max(d, 1e-6 * spec.occ.a) / spec.occ.a


@dataclass
class DcResult:
    t: FArray
    u: FArray  # V, terminal voltage (generator) or supply (motor)
    i_a: FArray  # A
    i_f: FArray  # A
    n: FArray  # rpm
    M_em: FArray  # N·m
    solver: dict[str, float | int | str]
    events: list[dict[str, float | str]] = field(default_factory=list)


def shunt_buildup(
    spec: DCSpec,
    *,
    n: float,
    r_rheo: float,
    L_a: float,
    L_f0: float,
    t_end: float,
    dt_out: float = 1e-3,
) -> DcResult:
    e = spec.ecm
    r_tot = e.R_a + e.R_f + r_rheo
    k = n / spec.occ.n_ref

    def mmf(i: float) -> float:
        return i - e.k_ar * abs(i) + spec.occ.F_res

    def rhs(_t: float, y: FArray) -> list[float]:
        i = y[0]
        f = mmf(i)
        emf = k * spec.occ.emf(f)
        return [
            (emf - r_tot * i - e.U_brush * math.tanh(i / I_BRUSH)) / (L_a + _l_inc(spec, f, L_f0))
        ]

    t_eval = np.arange(0.0, t_end + 0.5 * dt_out, dt_out)
    t_eval = np.minimum(t_eval, t_end)  # float rounding must not overshoot the span
    sol = solve_ivp(rhs, (0.0, t_end), [0.0], method="Radau", t_eval=t_eval, rtol=1e-8, atol=1e-9)
    if not sol.success:
        raise RuntimeError(f"transient solver failed: {sol.message}")
    i = sol.y[0]
    emf = np.array([k * spec.occ.emf(mmf(x)) for x in i])
    u = emf - e.R_a * i - e.U_brush * np.tanh(i / I_BRUSH)
    return DcResult(
        t=sol.t,
        u=u,
        i_a=i,
        i_f=i,
        n=np.full(sol.t.size, n),
        M_em=np.array([spec.occ.emf(mmf(x)) / (2 * math.pi * spec.occ.n_ref / 60) * x for x in i]),
        solver={"method": "Radau", "rtol": 1e-8, "nfev": int(sol.nfev)},
    )


def shunt_motor_start(
    spec: DCSpec,
    *,
    U: float,
    r_rheo: float,
    steps: list[tuple[float, float]],  # (R_st, t_end of the step)
    J: float,
    L_a: float,
    L_f0: float,
    M_brake: float = 0.0,
    field_first: bool = True,
    dt_out: float = 5e-4,
) -> DcResult:
    """`field_first`: the field circuit is energised before the armature is switched on (the
    usual practice, and what a three-point starter's first contact does); False switches both
    together, so the motor starts on a field that is still rising with τ_f."""
    e, occ, npl = spec.ecm, spec.occ, spec.nameplate
    w_ref = 2 * math.pi * occ.n_ref / 60
    m0 = e.P_rot_n / (2 * math.pi * npl.n_n / 60)

    def m_fric(n_rpm: float) -> float:
        if n_rpm == 0:
            return 0.0
        return math.copysign(m0 * abs(n_rpm / npl.n_n) ** (e.k_rot - 1), n_rpm) * math.tanh(
            abs(n_rpm) / 1.0
        )

    def mmf(i_f: float, i_a: float) -> float:
        # armature reaction is cross-magnetising: through saturation it WEAKENS an existing main
        # field but cannot reverse it. The steady-state model's linear term k_ar·|I_a| is capped
        # at half the main-field MMF — inactive at any steady operating point of the fit
        # (k_ar·I_n ≈ 0.05 A ≪ I_f), but it stops a fake reversed flux while the field is still
        # rising at switch-on.
        main = i_f + occ.F_res
        return main - min(e.k_ar * abs(i_a), 0.5 * abs(main))

    x = np.zeros(3)  # i_a, i_f, ω
    if field_first:  # the field was switched on earlier and has settled
        x[1] = U / (e.R_f + r_rheo)
    t0 = 0.0
    out_t: list[FArray] = []
    out_y: list[FArray] = []
    events: list[dict[str, float | str]] = []
    nfev = 0
    for k, (r_st, t_end) in enumerate(steps):

        def rhs(_t: float, y: FArray, r_st: float = r_st) -> list[float]:
            i_a, i_f, w = y
            n_rpm = w * 60 / (2 * math.pi)
            f = mmf(i_f, i_a)
            occ_f = occ.emf(f)
            emf = n_rpm / occ.n_ref * occ_f
            di_a = (U - emf - (e.R_a + r_st) * i_a - e.U_brush * math.tanh(i_a / I_BRUSH)) / L_a
            di_f = (U - (e.R_f + r_rheo) * i_f) / _l_inc(spec, f, L_f0)
            m_em = occ_f / w_ref * i_a
            dw = (m_em - m_fric(n_rpm) - M_brake * math.tanh(w / W_EPS)) / J
            return [di_a, di_f, dw]

        grid = np.arange(t0, t_end, dt_out)
        grid = grid[grid > t0] if k else grid
        t_eval = np.append(grid, t_end)
        sol = solve_ivp(
            rhs, (t0, t_end), x, method="Radau", t_eval=t_eval, rtol=1e-7, atol=[1e-7, 1e-8, 1e-5]
        )
        if not sol.success:
            raise RuntimeError(f"transient solver failed in step {k + 1}: {sol.message}")
        nfev += int(sol.nfev)
        out_t.append(sol.t)
        out_y.append(sol.y)
        x = np.array(sol.y[:, -1], dtype=float)
        if k:
            events.append({"t": t0, "label": f"מתנע {r_st:g} Ω"})
        t0 = t_end
    t = np.concatenate(out_t)
    y = np.concatenate(out_y, axis=1)
    i_a, i_f, w = y
    f = np.array([mmf(a, b) for a, b in zip(i_f, i_a, strict=True)])
    occ_f = np.array([occ.emf(v) for v in f])
    return DcResult(
        t=t,
        u=np.full(t.size, U),
        i_a=i_a,
        i_f=i_f,
        n=w * 60 / (2 * math.pi),
        M_em=occ_f / w_ref * i_a,
        solver={"method": "Radau", "rtol": 1e-7, "nfev": nfev},
        events=events,
    )
