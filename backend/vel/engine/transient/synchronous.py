"""Synchronous machine in the time domain: sudden three-phase short circuit at no load.

Sub-transient dq model (Sauer & Pai's two-axis model with stator transients, cylindrical rotor),
rotor reference frame, generator convention, amplitude-invariant transform, fluxes in volts
(ψ = ω_b·λ) and reactances in ohms of the winding:

  stator  (1/ω_b)·dψ_d/dt = v_d + R·i_d + (ω/ω_b)·ψ_q
          (1/ω_b)·dψ_q/dt = v_q + R·i_q − (ω/ω_b)·ψ_d
  fluxes  ψ_d = −X''d·i_d + k1·E'q + k2·ψ1d,   k1 = (X''d − Xl)/(X'd − Xl), k2 = 1 − k1
          ψ_q = −X''q·i_q + k3·ψ2q,             k3 = (Xq − X''q)/(Xq − Xl)
  rotor   T'd0·dE'q/dt  = −E'q − (Xd − X'd)·[i_d − kk·(ψ1d + (X'd − Xl)·i_d − E'q)] + E_fd,
                          kk = (X'd − X''d)/(X'd − Xl)²
          T''d0·dψ1d/dt = −ψ1d + E'q − (X'd − Xl)·i_d
          T''q0·dψ2q/dt = −ψ2q − (Xq − Xl)·i_q
  (X'q = Xq: no q-axis transient winding.)

* E_fd is the open-circuit EMF (peak, per winding) the field current gives on the AIR-GAP
  LINE — the model is linear. For the sustained short-circuit current that is the right
  choice (a short-circuited machine is unsaturated, and the steady-state model gives the same
  current). Before the fault, at a field current where the OCC bends, the real no-load
  voltage is lower than E_fd; the study reports both.
* The drive holds the speed (ω = ω_b) — the lab test is done on the servo drive.
* Xd = Xq = X_s(unsat) = Xl + a·k_a from the spec. X'd, X''d and the time constants are NOT
  in the spec; the study takes them as inputs (X''d defaults to the measured X2, since
  X2 ≈ (X''d + X''q)/2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

FArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class SmDynamics:
    R: float
    Xl: float
    Xd: float
    Xq: float
    Xd1: float  # X'd
    Xd2: float  # X''d
    Xq2: float  # X''q
    Td01: float  # T'd0 [s]
    Td02: float  # T''d0 [s]
    Tq02: float  # T''q0 [s]
    f: float

    def check(self) -> None:
        if not (self.Xl < self.Xd2 < self.Xd1 < self.Xd):
            raise ValueError("need Xl < X''d < X'd < Xd")
        if not (self.Xl < self.Xq2 < self.Xq):
            raise ValueError("need Xl < X''q < Xq")


@dataclass
class ScResult:
    t: FArray
    i_abc: FArray  # (3, N) winding currents [A]
    i_ac_env: FArray  # A peak: magnitude of the dq current averaged over a cycle (AC envelope)
    if_ratio: FArray  # field current / its pre-fault value
    i_peak: float
    i_sustained_rms: float
    e_fd: float  # pre-fault EMF on the air-gap line, peak per winding


def sudden_short_circuit(
    m: SmDynamics, *, E_rms: float, angle_deg: float, t_end: float, dt_out: float = 1e-4
) -> ScResult:
    m.check()
    wb = 2 * math.pi * m.f
    e_fd = math.sqrt(2) * E_rms
    k1 = (m.Xd2 - m.Xl) / (m.Xd1 - m.Xl)
    k2 = 1 - k1
    k3 = (m.Xq - m.Xq2) / (m.Xq - m.Xl)
    kk = (m.Xd1 - m.Xd2) / (m.Xd1 - m.Xl) ** 2

    def currents(y: FArray) -> tuple[float, float]:
        psd, psq, eq1, p1d, p2q = y
        i_d = (k1 * eq1 + k2 * p1d - psd) / m.Xd2
        i_q = (k3 * p2q - psq) / m.Xq2
        return i_d, i_q

    def rhs(_t: float, y: FArray) -> list[float]:
        psd, psq, eq1, p1d, p2q = y
        i_d, i_q = currents(y)
        # terminals shorted: v_d = v_q = 0
        dpsd = wb * (m.R * i_d + psq)
        dpsq = wb * (m.R * i_q - psd)
        deq1 = (
            -eq1 - (m.Xd - m.Xd1) * (i_d - kk * (p1d + (m.Xd1 - m.Xl) * i_d - eq1)) + e_fd
        ) / m.Td01
        dp1d = (-p1d + eq1 - (m.Xd1 - m.Xl) * i_d) / m.Td02
        dp2q = (-p2q - (m.Xq - m.Xl) * i_q) / m.Tq02
        return [dpsd, dpsq, deq1, dp1d, dp2q]

    y0 = np.array([e_fd, 0.0, e_fd, e_fd, 0.0])  # open circuit, steady
    t_eval = np.minimum(np.arange(0.0, t_end + 0.5 * dt_out, dt_out), t_end)
    sol = solve_ivp(
        rhs, (0.0, t_end), y0, method="Radau", t_eval=t_eval, rtol=1e-8, atol=1e-6 * e_fd
    )
    if not sol.success:
        raise RuntimeError(f"transient solver failed: {sol.message}")
    y = sol.y
    i_d = (k1 * y[2] + k2 * y[3] - y[0]) / m.Xd2
    i_q = (k3 * y[4] - y[1]) / m.Xq2
    th = wb * sol.t + math.radians(angle_deg)
    i_abc = np.vstack(
        [
            i_d * np.cos(th - s) - i_q * np.sin(th - s)
            for s in (0.0, 2 * math.pi / 3, -2 * math.pi / 3)
        ]
    )
    # AC envelope: the DC offset of the stator appears in the rotor frame as a fundamental
    # ripple on (i_d, i_q); averaging over one cycle leaves the symmetrical (AC) part
    per = max(1, int(round(1 / m.f / dt_out)))
    kern = np.ones(per) / per
    env = np.hypot(np.convolve(i_d, kern, mode="same"), np.convolve(i_q, kern, mode="same"))
    # the centred average is undefined within half a cycle of either end (zero padding)
    half = per // 2
    env[:half] = np.nan
    env[len(env) - half :] = np.nan
    # field current: X_ad·i_fd = E'q + (Xd − X'd)·[i_d − kk·(ψ1d + (X'd − Xl)·i_d − E'q)]
    xad_ifd = y[2] + (m.Xd - m.Xd1) * (i_d - kk * (y[3] + (m.Xd1 - m.Xl) * i_d - y[2]))
    return ScResult(
        t=sol.t,
        i_abc=i_abc,
        i_ac_env=env,
        if_ratio=xad_ifd / e_fd,
        i_peak=float(np.max(np.abs(i_abc))),
        i_sustained_rms=float(math.hypot(i_d[-1], i_q[-1]) / math.sqrt(2)),
        e_fd=e_fd,
    )


def ieee_envelope(m: SmDynamics, E_rms: float, t: FArray) -> FArray:
    """AC component (peak) of the short-circuit current, IEEE Std 115 / Kundur form:
    √2·E·[1/Xd + (1/X'd − 1/Xd)·e^(−t/T'd) + (1/X''d − 1/X'd)·e^(−t/T''d)],
    T'd = T'd0·X'd/Xd, T''d = T''d0·X''d/X'd (valid for R ≪ X)."""
    td1 = m.Td01 * m.Xd1 / m.Xd
    td2 = m.Td02 * m.Xd2 / m.Xd1
    return np.asarray(
        math.sqrt(2)
        * E_rms
        * (
            1 / m.Xd
            + (1 / m.Xd1 - 1 / m.Xd) * np.exp(-t / td1)
            + (1 / m.Xd2 - 1 / m.Xd1) * np.exp(-t / td2)
        )
    )
