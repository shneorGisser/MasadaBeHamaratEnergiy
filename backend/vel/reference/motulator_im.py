"""Direct-on-line start of the induction motor, computed with motulator's machine model.

Why: our transient engine (vel.engine.transient.induction) is a T-model in synchronous
coordinates, integrated with Radau. motulator (Aalto University, MIT licence) models the same
machine differently:
  - a Γ-equivalent circuit instead of the T circuit;
  - stationary (αβ) coordinates instead of synchronous ones;
  - its own code for fluxes, currents and torque.
We integrate it here with a different solver, LSODA. If both give the same line current,
speed and torque, a mistake in our frame transformation, scaling or torque formula would have
to be repeated, independently, in someone else's code.

Kept identical on purpose (they are inputs, not the model under test):
  - the T → inverse-Γ parameter conversion, which is exact without saturation:
      L_M = Lm²/Lr, L_σ = Ls − Lm²/Lr, R_R = R2'·(Lm/Lr)²;
  - the load model: brake torque·tanh(ω/ω_ε) plus friction k_fw·ω;
  - the supply: ideal and sinusoidal.
Iron loss is off in both, because our transient model has none.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from vel.engine.transient.induction import W_EPS, ImParams, VfRamp
from vel.experiments.induction_motor.spec import MotorSpec

FArray = npt.NDArray[np.float64]


@dataclass
class RefStart:
    t: FArray
    i_a: FArray  # A, line L1 (Y connection)
    n: FArray  # rpm
    M_em: FArray  # N·m


def dol_start_y(
    m: ImParams,
    *,
    U_line: float,
    f: float,
    J: float,
    M_brake: float = 0.0,
    angle_deg: float = 0.0,
    t_end: float = 1.0,
    dt_out: float = 2.5e-4,
) -> RefStart:
    from motulator.drive.model import InductionMachine, InductionMachineInvGammaPars

    wb = 2 * math.pi * m.f_n
    lm = m.Xm / wb
    ls, lr = m.X1 / wb + lm, m.X2p / wb + lm
    par = InductionMachineInvGammaPars(
        n_p=m.poles // 2,
        R_s=m.R1,
        R_R=m.R2p * (lm / lr) ** 2,
        L_sgm=ls - lm**2 / lr,
        L_M=lm**2 / lr,
    )
    machine = InductionMachine(par)
    we = 2 * math.pi * f
    u_pk = math.sqrt(2) * U_line / math.sqrt(3)
    phi = math.radians(angle_deg)

    def rhs(t: float, y: FArray) -> list[float]:
        machine.state.psi_s_ab = complex(y[0], y[1])
        machine.state.psi_r_ab = complex(y[2], y[3])
        machine.inp.u_s_ab = u_pk * complex(math.cos(we * t + phi), math.sin(we * t + phi))
        machine.inp.w_M = float(y[4])
        machine.set_outputs(t)
        d_ps, d_pr = machine.rhs(t)
        load = M_brake * math.tanh(y[4] / W_EPS) + m.k_fw * y[4]
        return [d_ps.real, d_ps.imag, d_pr.real, d_pr.imag, (machine.out.tau_M - load) / J]

    t_eval = np.arange(0.0, t_end + 0.5 * dt_out, dt_out)
    psi_b = u_pk / we
    sol = solve_ivp(
        rhs,
        (0.0, t_end),
        np.zeros(5),
        method="LSODA",
        t_eval=t_eval,
        rtol=1e-8,
        atol=[1e-8 * psi_b] * 4 + [1e-7 * we],
    )
    if not sol.success:
        raise RuntimeError(f"reference solver failed: {sol.message}")
    i_a = np.empty(sol.t.size)
    tau = np.empty(sol.t.size)
    for k in range(sol.t.size):
        machine.state.psi_s_ab = complex(sol.y[0, k], sol.y[1, k])
        machine.state.psi_r_ab = complex(sol.y[2, k], sol.y[3, k])
        machine.set_outputs(float(sol.t[k]))
        i_a[k] = machine.out.i_s_ab.real
        tau[k] = machine.out.tau_M
    return RefStart(sol.t, i_a, sol.y[4] * 60 / (2 * math.pi), tau)


def compare_dol(
    spec: MotorSpec, *, U_line: float, J: float, M_brake: float = 0.0, t_end: float = 1.0
) -> dict[str, float]:
    """Our engine vs motulator on the same DOL start (Y). Errors relative to the peaks."""
    from vel.engine.transient.induction import dol_start

    ours = dol_start(spec, U_line=U_line, f=50.0, connection="Y", J=J, M_brake=M_brake, t_end=t_end)
    ref = dol_start_y(
        ImParams.of_motor(spec), U_line=U_line, f=50.0, J=J, M_brake=M_brake, t_end=t_end
    )
    n = min(ours.t.size, ref.t.size)
    assert np.allclose(ours.t[:n], ref.t[:n], atol=1e-9), "time grids differ"
    di = np.abs(ours.i_line[:n] - ref.i_a[:n])
    dn = np.abs(ours.n[:n] - ref.n[:n])
    dm = np.abs(ours.M_em[:n] - ref.M_em[:n])
    return {
        "i_err_max": float(di.max() / np.abs(ref.i_a[:n]).max()),
        "n_err_max": float(dn.max() / max(1.0, np.abs(ref.n[:n]).max())),
        "M_err_max": float(dm.max() / np.abs(ref.M_em[:n]).max()),
        "i_peak_ours": float(np.abs(ours.i_line[:n]).max()),
        "i_peak_ref": float(np.abs(ref.i_a[:n]).max()),
        "n_final_ours": float(ours.n[n - 1]),
        "n_final_ref": float(ref.n[n - 1]),
        "samples": float(n),
    }


def vf_start_y(
    m: ImParams,
    ramp: VfRamp,
    *,
    J: float,
    M_brake: float = 0.0,
    t_end: float = 1.0,
    dt_out: float = 2.5e-4,
) -> RefStart:
    """Star-connected inverter start, u_ab = √2·U(f(t))·e^{jθ(t)} with θ = ∫2πf dt — the
    fundamental (average) model, as in our vf_start. Integrated in two pieces so LSODA never
    steps across the end of the ramp."""
    from motulator.drive.model import InductionMachine, InductionMachineInvGammaPars

    wb = 2 * math.pi * m.f_n
    lm = m.Xm / wb
    ls, lr = m.X1 / wb + lm, m.X2p / wb + lm
    machine = InductionMachine(
        InductionMachineInvGammaPars(
            n_p=m.poles // 2,
            R_s=m.R1,
            R_R=m.R2p * (lm / lr) ** 2,
            L_sgm=ls - lm**2 / lr,
            L_M=lm**2 / lr,
        )
    )

    def u_ab(t: float) -> complex:
        th = float(ramp.theta(np.array([t]))[0])
        return math.sqrt(2) * ramp.u(ramp.f(t)) * complex(math.cos(th), math.sin(th))

    def rhs(t: float, y: FArray) -> list[float]:
        machine.state.psi_s_ab = complex(y[0], y[1])
        machine.state.psi_r_ab = complex(y[2], y[3])
        machine.inp.u_s_ab = u_ab(t)
        machine.inp.w_M = float(y[4])
        machine.set_outputs(t)
        d_ps, d_pr = machine.rhs(t)
        load = M_brake * math.tanh(y[4] / W_EPS) + m.k_fw * y[4]
        return [d_ps.real, d_ps.imag, d_pr.real, d_pr.imag, (machine.out.tau_M - load) / J]

    psi_b = math.sqrt(2) * ramp.U_n / wb
    atol = [1e-8 * psi_b] * 4 + [1e-7 * wb]
    edges = [0.0, *([ramp.t_ramp] if 0 < ramp.t_ramp < t_end else []), t_end]
    x = np.zeros(5)
    ts, ys = [], []
    for k in range(len(edges) - 1):
        a, b = edges[k], edges[k + 1]
        grid = np.arange(a, b, dt_out)
        grid = grid[grid > a] if k else grid
        sol = solve_ivp(
            rhs, (a, b), x, method="LSODA", t_eval=np.append(grid, b), rtol=1e-8, atol=atol
        )
        if not sol.success:
            raise RuntimeError(f"reference solver failed: {sol.message}")
        ts.append(sol.t)
        ys.append(sol.y)
        x = sol.y[:, -1].copy()
    t = np.concatenate(ts)
    y = np.concatenate(ys, axis=1)
    i_a = np.empty(t.size)
    tau = np.empty(t.size)
    for k in range(t.size):
        machine.state.psi_s_ab = complex(y[0, k], y[1, k])
        machine.state.psi_r_ab = complex(y[2, k], y[3, k])
        machine.inp.u_s_ab = u_ab(float(t[k]))
        machine.set_outputs(float(t[k]))
        i_a[k] = machine.out.i_s_ab.real
        tau[k] = machine.out.tau_M
    return RefStart(t, i_a, y[4] * 60 / (2 * math.pi), tau)


def compare_vf(
    spec: MotorSpec, ramp: VfRamp, *, J: float, M_brake: float = 0.0, t_end: float = 1.0
) -> dict[str, float]:
    """Our V/f start vs motulator on the same ramp (Y). Errors relative to the peaks; compared
    on the reference's time grid (interpolated, since the two piecewise grids may differ by a
    sample at the ramp end)."""
    from vel.engine.transient.induction import vf_start

    m = ImParams.of_motor(spec)
    ours = vf_start(m, ramp, connection="Y", J=J, M_brake=M_brake, t_end=t_end)
    ref = vf_start_y(m, ramp, J=J, M_brake=M_brake, t_end=t_end)
    di = np.abs(np.interp(ref.t, ours.t, ours.i_line) - ref.i_a)
    dn = np.abs(np.interp(ref.t, ours.t, ours.n) - ref.n)
    dm = np.abs(np.interp(ref.t, ours.t, ours.M_em) - ref.M_em)
    return {
        "i_err_max": float(di.max() / np.abs(ref.i_a).max()),
        "n_err_max": float(dn.max() / max(1.0, np.abs(ref.n).max())),
        "M_err_max": float(dm.max() / np.abs(ref.M_em).max()),
    }
