"""Induction machine in the time domain: the 5th-order dq model (Krause), synchronous frame.

States: stator and rotor flux linkages ψs, ψr (space vectors, amplitude-invariant, referred to
the stator) and the mechanical speed ω_m. Per winding, with the leakage and magnetizing
reactances of the spec taken at f_n (L = X/ω_n):

    dψs/dt = v_s − R1·i_s − jω_e·ψs
    dψr/dt =      − R2'·i_r − j(ω_e − ω_r)·ψr,      ω_r = (p/2)·ω_m
    [ψs; ψr] = [[Ls, Lm], [Lm, Lr]]·[i_s; i_r],      Ls = L1σ + Lm,  Lr = L2σ' + Lm
    M_em = (3/2)·(p/2)·Im(ψs* · i_s)
    J·dω_m/dt = M_em − M_brake·tanh(ω_m/ω_ε) − M_fw(ω_m)

* The supply is switched on at an instant set by the phase angle of v_a (switching angle),
  which sets the DC offset of the starting currents. An ideal (zero-impedance) supply.
* Friction and windage: P_fw ∝ n² as in the steady-state model, i.e. M_fw = P_fw,n/ω_n·(n/n_n).
* The brake (magnetic powder) holds a set torque against the rotation; tanh makes it vanish
  smoothly at standstill instead of switching sign.
* NOT modelled: iron loss (R_Fe has no place in the flux model; its effect on the steady state
  is reported by the study), saturation of the leakage paths at starting current, deep-bar /
  skin effect in the rotor (R2', X2' are constant), slot harmonics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from vel.experiments.induction_motor.spec import MotorSpec

FArray = npt.NDArray[np.float64]
A120 = complex(-0.5, math.sqrt(3) / 2)
W_EPS = 0.5  # rad/s: speed over which the brake torque builds up from zero


@dataclass
class StartResult:
    t: FArray  # s
    i_line: FArray  # A, line current L1 (instantaneous)
    i_line_rms: FArray  # A, RMS envelope of the line current (|i_s|/√2 × line factor)
    n: FArray  # rpm
    M_em: FArray  # N·m, electromagnetic torque
    n_final: float
    i_line_rms_final: float
    i_peak: float  # A, largest |instantaneous| line current
    t_95: float | None  # s, time to reach 95 % of the final speed
    solver: dict[str, float | int | str]


def _params(spec: MotorSpec) -> tuple[float, float, float, float, float, float, float]:
    e, n = spec.ecm, spec.nameplate
    wb = 2 * math.pi * n.f_n
    lm = e.Xm / wb
    return e.R1, e.R2p, e.X1 / wb + lm, e.X2p / wb + lm, lm, wb, n.poles / 2


def dol_start(
    spec: MotorSpec,
    *,
    U_line: float,
    f: float,
    connection: Literal["Y", "D"],
    J: float,
    M_brake: float = 0.0,
    t_end: float = 1.0,
    angle_deg: float = 0.0,
    dt_out: float = 2.5e-4,
) -> StartResult:
    """Direct-on-line start from standstill with zero initial fluxes."""
    r1, r2, ls, lr, lm, wb, pp = _params(spec)
    d = ls * lr - lm * lm
    we = 2 * math.pi * f
    u_w = U_line if connection == "D" else U_line / math.sqrt(3)
    v_s = (
        math.sqrt(2)
        * u_w
        * complex(math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg)))
    )
    npl = spec.nameplate
    w_n = 2 * math.pi * npl.n_n / 60
    k_fw = spec.ecm.P_fw_n / w_n / w_n  # M_fw = k_fw·ω_m

    def rhs(_t: float, x: FArray) -> list[float]:
        ps = complex(x[0], x[1])
        pr = complex(x[2], x[3])
        wm = x[4]
        i_s = (lr * ps - lm * pr) / d
        i_r = (ls * pr - lm * ps) / d
        dps = v_s - r1 * i_s - 1j * we * ps
        dpr = -r2 * i_r - 1j * (we - pp * wm) * pr
        m_em = 1.5 * pp * (ps.conjugate() * i_s).imag
        m_load = M_brake * math.tanh(wm / W_EPS) + k_fw * wm
        return [dps.real, dps.imag, dpr.real, dpr.imag, (m_em - m_load) / J]

    psi_b = math.sqrt(2) * u_w / we
    atol = [1e-7 * psi_b] * 4 + [1e-6 * we]
    t_eval = np.arange(0.0, t_end + 0.5 * dt_out, dt_out)
    sol = solve_ivp(
        rhs, (0.0, t_end), np.zeros(5), method="Radau", t_eval=t_eval, rtol=1e-7, atol=atol
    )
    if not sol.success:
        raise RuntimeError(f"transient solver failed: {sol.message}")
    x = sol.y
    ps = x[0] + 1j * x[1]
    pr = x[2] + 1j * x[3]
    i_s = (lr * ps - lm * pr) / d
    # back to the stator (abc) frame: winding currents
    rot = np.exp(1j * (we * sol.t))
    i_ab = i_s * rot
    i_a = i_ab.real
    i_c = (i_ab * A120).real  # winding c lags a by 240° (= leads by 120°)
    line_k = math.sqrt(3) if connection == "D" else 1.0
    # Δ: line L1 current = i_a − i_c (winding a between L1 and L2, winding c between L3 and L1)
    i_line = i_a - i_c if connection == "D" else i_a
    i_rms = np.abs(i_s) / math.sqrt(2) * line_k
    n_rpm = x[4] * 60 / (2 * math.pi)
    m_em = 1.5 * pp * (np.conj(ps) * i_s).imag
    n_fin = float(n_rpm[-1])
    above = np.nonzero(n_rpm >= 0.95 * n_fin)[0]
    return StartResult(
        t=sol.t,
        i_line=i_line,
        i_line_rms=i_rms,
        n=n_rpm,
        M_em=m_em,
        n_final=n_fin,
        i_line_rms_final=float(i_rms[-1]),
        i_peak=float(np.max(np.abs(i_line))),
        t_95=float(sol.t[above[0]]) if n_fin > 1 and above.size else None,
        solver={
            "method": "Radau",
            "rtol": 1e-7,
            "nfev": int(sol.nfev),
            "steps_out": int(sol.t.size),
        },
    )
