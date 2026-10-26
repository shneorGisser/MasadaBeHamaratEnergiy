"""Shunt DC motor start computed with gym-electric-motor's motor model (MIT, Paderborn).

Why: gym-electric-motor (GEM, Balakrishna et al., JOSS 2021) implements the DC machines as
linear state-space models: L_a·di_a/dt = u − R_a·i_a − L_e'·i_e·ω, M = L_e'·i_a·i_e. Ours
(vel.engine.transient.dcmachine) is built from the fitted, saturating OCC and works in rpm and
shunt-field amperes. Comparing the two checks the coupling — EMF constant, torque constant,
rpm ↔ rad/s, the 2π/60s — where an error would not show in any steady-state test.

The comparison is only meaningful where GEM's linear machine IS ours, so it is set up there:
field switched on first (i_f settled, constant), no armature reaction, no brush drop. At that
fixed field our E = (n/n_ref)·OCC(F) is linear in ω with k = OCC(F)/ω_ref, and GEM's L_e' is
chosen as k/i_f. Taken from GEM: ``DcShuntMotor.electrical_ode`` and ``torque``. Written here:
the supply, the starter steps, the mechanics (friction as in our model) and the integration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from vel.experiments.dc_machine.spec import DCSpec

FArray = npt.NDArray[np.float64]
W_EPS = 0.5  # rad/s, as in our engine


@dataclass
class RefDc:
    t: FArray
    i_a: FArray
    n: FArray  # rpm
    M_em: FArray


def linear_core(spec: DCSpec) -> DCSpec:
    """The part of our model GEM can reproduce: no armature reaction, no brush drop."""
    return spec.model_copy(
        update={"ecm": spec.ecm.model_copy(update={"k_ar": 0.0, "U_brush": 0.0})}
    )


def shunt_start(
    spec: DCSpec,
    *,
    U: float,
    r_rheo: float,
    steps: list[tuple[float, float]],
    J: float,
    L_a: float,
    L_f0: float,
    M_brake: float = 0.0,
    dt_out: float = 5e-4,
) -> RefDc:
    from gym_electric_motor.physical_systems.electric_motors import DcShuntMotor

    e, occ, npl = spec.ecm, spec.occ, spec.nameplate
    i_f = U / (e.R_f + r_rheo)
    w_ref = 2 * math.pi * occ.n_ref / 60
    k = occ.emf(i_f + occ.F_res) / w_ref  # V·s/rad at this field
    m0 = e.P_rot_n / (2 * math.pi * npl.n_n / 60)

    def m_fric(n_rpm: float) -> float:
        if n_rpm == 0:
            return 0.0
        return math.copysign(m0 * abs(n_rpm / npl.n_n) ** (e.k_rot - 1), n_rpm) * math.tanh(
            abs(n_rpm) / 1.0
        )

    t0, x = 0.0, np.array([0.0, i_f, 0.0])
    ts, ys = [], []
    for j, (r_st, t_end) in enumerate(steps):
        # the starter resistance is in series with the armature only: GEM's R_a absorbs it
        motor = DcShuntMotor(
            motor_parameter={
                "r_a": e.R_a + r_st,
                "r_e": e.R_f + r_rheo,
                "l_a": L_a,
                "l_e": L_f0,
                "l_e_prime": k / i_f,
                "j_rotor": J,
            }
        )

        def rhs(_t: float, y: FArray, motor: DcShuntMotor = motor) -> list[float]:
            d = motor.electrical_ode(y[:2], (U,), y[2])
            n_rpm = y[2] * 60 / (2 * math.pi)
            m_em = motor.torque(y[:2])
            dw = (m_em - m_fric(n_rpm) - M_brake * math.tanh(y[2] / W_EPS)) / J
            return [float(d[0]), float(d[1]), dw]

        grid = np.arange(t0, t_end, dt_out)
        grid = grid[grid > t0] if j else grid
        sol = solve_ivp(
            rhs,
            (t0, t_end),
            x,
            method="LSODA",
            t_eval=np.append(grid, t_end),
            rtol=1e-9,
            atol=[1e-9, 1e-10, 1e-7],
        )
        if not sol.success:
            raise RuntimeError(f"reference solver failed: {sol.message}")
        ts.append(sol.t)
        ys.append(sol.y)
        x = sol.y[:, -1].copy()
        t0 = t_end
    t = np.concatenate(ts)
    y = np.concatenate(ys, axis=1)
    return RefDc(t, y[0], y[2] * 60 / (2 * math.pi), k / i_f * y[0] * y[1])


def compare_shunt_start(spec: DCSpec, **kw: object) -> dict[str, float]:
    from vel.engine.transient.dcmachine import shunt_motor_start

    s = linear_core(spec)
    ours = shunt_motor_start(s, field_first=True, **kw)  # type: ignore[arg-type]
    ref = shunt_start(s, **kw)  # type: ignore[arg-type]
    di = np.abs(np.interp(ref.t, ours.t, ours.i_a) - ref.i_a)
    dn = np.abs(np.interp(ref.t, ours.t, ours.n) - ref.n)
    dm = np.abs(np.interp(ref.t, ours.t, ours.M_em) - ref.M_em)
    return {
        "i_err_max": float(di.max() / np.abs(ref.i_a).max()),
        "n_err_max": float(dn.max() / max(1.0, np.abs(ref.n).max())),
        "M_err_max": float(dm.max() / np.abs(ref.M_em).max()),
        "n_final": float(ref.n[-1]),
        "i_peak": float(np.abs(ref.i_a).max()),
    }
