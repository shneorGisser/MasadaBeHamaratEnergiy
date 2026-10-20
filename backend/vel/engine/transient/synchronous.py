"""Synchronous machine in the time domain: sudden three-phase short circuit at no load, and
synchronisation to the grid (`synchronize`).

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
* Short circuit: the drive holds the speed (ω = ω_b) — the lab test is done on the servo
  drive. Synchronisation: the speed is free, J·dω_m/dt = M_drive − M_em − M_fw, and the load
  angle δ is a state (dδ/dt = ω_e − ω_b).
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


def saturate(m: SmDynamics, k: float) -> SmDynamics:
    """Scale the mutual (magnetising) reactances X_ad = Xd − Xl, X_aq = Xq − Xl by the
    saturation factor k, keeping the rotor circuits (X_fd, X_1d, X_1q and their resistances).

    The equivalent-circuit identities fix the rotor leakages from the unsaturated data:
        X'd − Xl = X_ad‖X_fd,   X''d − Xl = X_ad‖X_fd‖X_1d,   X''q − Xl = X_aq‖X_1q
        T'd0 ∝ X_ad + X_fd,     T''d0 ∝ X_1d + X_ad‖X_fd,     T''q0 ∝ X_1q + X_aq
    so a saturated machine has a smaller Xd but nearly the same X'd and X''d (they are
    leakage-dominated) — which is what keeps Xl < X''d < X'd < Xd valid."""
    if k == 1.0:
        return m
    if not 0 < k <= 1.5:
        raise ValueError(f"saturation factor {k} out of range")

    def par(*x: float) -> float:
        return 1 / sum(1 / v for v in x)

    xad, xaq = m.Xd - m.Xl, m.Xq - m.Xl
    a1, a2, aq = m.Xd1 - m.Xl, m.Xd2 - m.Xl, m.Xq2 - m.Xl
    if not (0 < a2 < a1 < xad and 0 < aq < xaq):
        raise ValueError("need Xl < X''d < X'd < Xd and Xl < X''q < Xq")
    x_fd = 1 / (1 / a1 - 1 / xad)
    x_1d = 1 / (1 / a2 - 1 / a1)
    x_1q = 1 / (1 / aq - 1 / xaq)
    kad, kaq = k * xad, k * xaq
    return SmDynamics(
        R=m.R,
        Xl=m.Xl,
        Xd=m.Xl + kad,
        Xq=m.Xl + kaq,
        Xd1=m.Xl + par(kad, x_fd),
        Xd2=m.Xl + par(kad, x_fd, x_1d),
        Xq2=m.Xl + par(kaq, x_1q),
        Td01=m.Td01 * (kad + x_fd) / (xad + x_fd),
        Td02=m.Td02 * (x_1d + par(kad, x_fd)) / (x_1d + a1),
        Tq02=m.Tq02 * (x_1q + kaq) / (x_1q + xaq),
        f=m.f,
    )


@dataclass
class SyncResult:
    t: FArray
    i_abc: FArray  # (3, N) winding currents [A]
    delta_deg: FArray  # load angle: rotor q axis ahead of the bus voltage (generator +)
    n: FArray  # rpm
    p_el: FArray  # W, electrical power delivered to the grid (generator +)
    i_rms: FArray  # instantaneous RMS of the winding current, |i_dq|/√2
    i_peak: float
    i_rms_final: float  # winding current, mean over the last cycle
    p_final: float
    delta_final: float
    n_sync: float
    pulled_in: bool
    settled: bool


def synchronize(
    m: SmDynamics,
    *,
    poles: int,
    J: float,
    P_fw: float,
    V_rms: float,
    E_rms: float,
    E_fd_rms: float,
    delta0_deg: float,
    df: float,
    P_drive: float,
    t_end: float,
    dt_out: float = 2e-4,
) -> SyncResult:
    """Close the breaker onto an infinite bus (winding voltage V_rms, frequency m.f).

    Before closing the machine runs open-circuit at f + df with EMF E_rms (referred to rated
    speed), its q axis delta0 ahead of the bus voltage. The field voltage sustains E_fd_rms —
    equal to E_rms for a linear machine; the study passes a different value when it linearises
    the saturation at the final operating point. After closing the drive delivers a constant
    torque P_drive/ω_s and J·dω_m/dt = M_drive − M_em − M_fw, M_fw = P_fw/ω_s·(ω/ω_s)
    (P_fw ∝ n², as in the steady-state model).

    Rotor frame (Sauer–Pai, generator convention): v_d + j·v_q = √2·V·(sin δ + j·cos δ).
    The open-circuit EMF lies on the q axis, so δ0 = 0, df = 0, E = V is a perfect closing."""
    m.check()
    wb = 2 * math.pi * m.f
    pp = poles / 2
    ws_m = wb / pp
    e_fd = math.sqrt(2) * E_fd_rms
    e0 = math.sqrt(2) * E_rms
    k1 = (m.Xd2 - m.Xl) / (m.Xd1 - m.Xl)
    k2 = 1 - k1
    k3 = (m.Xq - m.Xq2) / (m.Xq - m.Xl)
    kk = (m.Xd1 - m.Xd2) / (m.Xd1 - m.Xl) ** 2
    v_amp = math.sqrt(2) * V_rms
    m_drive = P_drive / ws_m

    def rhs(_t: float, y: FArray) -> list[float]:
        psd, psq, eq1, p1d, p2q, dl, wm = y
        i_d = (k1 * eq1 + k2 * p1d - psd) / m.Xd2
        i_q = (k3 * p2q - psq) / m.Xq2
        we = pp * wm
        v_d, v_q = v_amp * math.sin(dl), v_amp * math.cos(dl)
        dpsd = wb * (v_d + m.R * i_d) + we * psq
        dpsq = wb * (v_q + m.R * i_q) - we * psd
        deq1 = (
            -eq1 - (m.Xd - m.Xd1) * (i_d - kk * (p1d + (m.Xd1 - m.Xl) * i_d - eq1)) + e_fd
        ) / m.Td01
        dp1d = (-p1d + eq1 - (m.Xd1 - m.Xl) * i_d) / m.Td02
        dp2q = (-p2q - (m.Xq - m.Xl) * i_q) / m.Tq02
        m_em = 1.5 * pp * (psd * i_q - psq * i_d) / wb
        m_fw = P_fw / ws_m * (wm / ws_m)
        return [dpsd, dpsq, deq1, dp1d, dp2q, we - wb, (m_drive - m_em - m_fw) / J]

    w0 = ws_m * (1 + df / m.f)
    # open circuit: no current, so ψd = E'q = ψ1d = E (flux linkage in volts at ω_b), ψq = 0
    y0 = np.array([e0, 0.0, e0, e0, 0.0, math.radians(delta0_deg), w0])
    t_eval = np.minimum(np.arange(0.0, t_end + 0.5 * dt_out, dt_out), t_end)
    sol = solve_ivp(
        rhs,
        (0.0, t_end),
        y0,
        method="Radau",
        t_eval=t_eval,
        rtol=1e-7,
        atol=1e-7 * max(e0, e_fd, v_amp),
    )
    if not sol.success:
        raise RuntimeError(f"transient solver failed: {sol.message}")
    y = sol.y
    i_d = (k1 * y[2] + k2 * y[3] - y[0]) / m.Xd2
    i_q = (k3 * y[4] - y[1]) / m.Xq2
    # stator angle of the rotor d axis: the bus angle ω_b·t plus δ − 90°
    th = wb * sol.t + y[5] - math.pi / 2
    i_abc = np.vstack(
        [
            i_d * np.cos(th - s) - i_q * np.sin(th - s)
            for s in (0.0, 2 * math.pi / 3, -2 * math.pi / 3)
        ]
    )
    v_d, v_q = v_amp * np.sin(y[5]), v_amp * np.cos(y[5])
    p_el = 1.5 * (v_d * i_d + v_q * i_q)
    n_rpm = y[6] * 60 / (2 * math.pi)
    n_s = 60 * m.f / pp
    d_deg = np.degrees(y[5])
    per = max(1, int(round(1 / m.f / dt_out)))
    tail = slice(max(0, len(sol.t) - per), None)
    # pulled in: at synchronous speed over the last cycle (no pole slipping)
    pulled = bool(abs(float(np.mean(n_rpm[tail])) - n_s) < 1e-3 * n_s)
    # settled: the swing has died out over the last 0.5 s
    w_set = slice(max(0, len(sol.t) - int(round(0.5 / dt_out))), None)
    settled = pulled and float(np.ptp(d_deg[w_set])) < 0.01 + 2e-3 * abs(float(d_deg[-1]))
    i_mag = np.hypot(i_d, i_q) / math.sqrt(2)
    return SyncResult(
        t=sol.t,
        i_abc=i_abc,
        delta_deg=d_deg,
        n=n_rpm,
        p_el=p_el,
        i_rms=i_mag,
        i_peak=float(np.max(np.abs(i_abc))),
        i_rms_final=float(np.mean(i_mag[tail])),
        p_final=float(np.mean(p_el[tail])),
        delta_final=float(d_deg[-1]),
        n_sync=n_s,
        pulled_in=pulled,
        settled=settled,
    )
