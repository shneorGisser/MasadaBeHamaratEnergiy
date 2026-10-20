"""Three-phase transformer energisation in the time domain: inrush current.

Per limb (bank model, as in the steady state — no magnetic coupling between limbs), primary
side, secondary open:

    e_k(t) − v_n = R1·i_k + L1σ·di_k/dt + u_k          (supply phase k, star point v_n)
    u_k = dλ_k/dt = R_Fe·(i_k − i_m(λ_k))                (core loss in parallel)
    i_m(λ) = λ/L_m0 · (1 + c'·|λ/λ_n|^n)                 (single-valued magnetising curve)

* Star primary WITHOUT neutral (the lab feed; `neutral=True` connects it): Σi_k = 0, which
  fixes the star-point voltage algebraically, v_n = ⅓·Σ(e_k − R1·i_k − u_k). Delta primary:
  each winding sits across its line voltage, no constraint.
* The steady-state model saturates through an RMS-dependent X_m(E) = X_m0/(1 + c·(E/E_n)^n)
  (a describing function). The instantaneous curve uses the same shape; c' is chosen so that
  the FUNDAMENTAL of the magnetising current at rated flux equals the steady-state model's
  value — so the two engines agree at the rated point, and the instantaneous model adds the
  harmonics and the inrush the phasor model cannot show.
* Remanence enters as the initial flux of each limb, pattern (+r, −r, 0)·λ_n, on the
  single-valued curve (no hysteresis loop). At t = 0 that implies a magnetising current
  i_m(λ_r) — below the no-load peak, negligible beside the inrush. The flux offset then decays
  through R1 and R_Fe as in a real energisation; with no hysteresis loss the decay is
  somewhat slower than measured.
* NOT modelled: hysteresis, three-limb coupling (zero-sequence flux), supply impedance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from vel.experiments.transformer3ph.spec import TransformerSpec

FArray = npt.NDArray[np.float64]
SQ3 = math.sqrt(3)


def _fundamental_rms(lm0: float, c: float, n: float, lam_n: float, amp: float) -> float:
    """RMS of the fundamental of i_m(λ̂·sin θ) — by quadrature over one period."""
    th = np.linspace(0, 2 * math.pi, 2049)[:-1]
    lam = amp * np.sin(th)
    i = lam / lm0 * (1 + c * np.abs(lam / lam_n) ** n)
    b1 = 2 * np.mean(i * np.sin(th))
    return float(abs(b1) / math.sqrt(2))


def instantaneous_c(spec: TransformerSpec) -> float:
    """c' such that the fundamental at rated flux equals the steady-state magnetising current."""
    e = spec.ecm
    if e.sat_c == 0:
        return 0.0
    w = 2 * math.pi * spec.nameplate.f_n
    lm0 = e.Xm_unsat / w
    lam_n = math.sqrt(2) * spec.U1_winding / w
    target = spec.U1_winding / (e.Xm_unsat / (1 + e.sat_c))  # I = E/X_m(E_n)

    def g(c: float) -> float:
        return _fundamental_rms(lm0, c, e.sat_n, lam_n, lam_n) - target

    return float(brentq(g, 0.0, 10 * e.sat_c + 10))


@dataclass
class InrushResult:
    t: FArray
    i_line: FArray  # (3, N) line currents L1..L3
    lam_pu: FArray  # (3, N) limb fluxes / λ_n
    i_peak: float
    i_peak_phase: int
    i0_peak_steady: float  # peak of the steady no-load line current (end of run)
    i0_rms_fund: float  # fundamental RMS of the steady no-load line current, phase L1
    t_decay: float | None  # first time after which every cycle's peak < 2 × steady peak
    c_inst: float


def energise(
    spec: TransformerSpec,
    *,
    U_line: float,
    angle_deg: float,
    remanence: float,
    t_end: float,
    dt_out: float = 1e-4,
    steady_start: bool = False,
    neutral: bool = False,
) -> InrushResult:
    """`steady_start` starts every limb on its sinusoidal steady-state flux (no DC offset):
    the reference case without inrush, used to compare with the phasor model."""
    e, npl = spec.ecm, spec.nameplate
    f = npl.f_n
    w = 2 * math.pi * f
    lm0 = e.Xm_unsat / w
    l1 = e.X1 / w
    lam_n = math.sqrt(2) * spec.U1_winding / w
    c_i = instantaneous_c(spec)
    n_s = e.sat_n
    delta = npl.primary == "D"
    u_w = U_line if delta else U_line / SQ3
    a0 = math.radians(angle_deg)
    shifts = (0.0, -2 * math.pi / 3, 2 * math.pi / 3)
    # Δ windings A, B, C across L1–L2, L2–L3, L3–L1: +30° to the phase voltages
    w_shift = math.pi / 6 if delta else 0.0

    def i_m(lam: FArray) -> FArray:
        return lam / lm0 * (1 + c_i * np.abs(lam / lam_n) ** n_s)

    def rhs(t: float, y: FArray) -> FArray:
        i = y[0:3]
        lam = y[3:6]
        u = e.R_fe * (i - i_m(lam))
        ek = np.array([math.sqrt(2) * u_w * math.sin(w * t + a0 + s + w_shift) for s in shifts])
        drive = ek - e.R1 * i - u
        if not delta and not neutral:
            drive = drive - drive.mean()  # star without neutral: Σi = 0 ⇒ Σdi/dt = 0
        return np.concatenate([drive / l1, u])

    if steady_start:
        amp = math.sqrt(2) * u_w / w
        lam0 = np.array([-amp * math.cos(a0 + s + w_shift) for s in shifts])
        if not delta and not neutral:
            lam0 = lam0 - lam0.mean()
    else:
        lam0 = np.array([remanence, -remanence, 0.0]) * lam_n
    y0 = np.concatenate([i_m(lam0), lam0])
    t_eval = np.arange(0.0, t_end + 0.5 * dt_out, dt_out)
    t_eval = np.minimum(t_eval, t_end)
    sol = solve_ivp(
        rhs,
        (0.0, t_end),
        y0,
        method="Radau",
        t_eval=t_eval,
        rtol=1e-6,
        atol=np.concatenate([np.full(3, 1e-6), np.full(3, 1e-8 * lam_n)]),
    )
    if not sol.success:
        raise RuntimeError(f"transient solver failed: {sol.message}")
    iw = sol.y[0:3]
    # line currents: star → the winding currents; delta → i_L1 = i_A − i_C, …
    i_line = np.vstack([iw[0] - iw[2], iw[1] - iw[0], iw[2] - iw[1]]) if delta else iw
    k_pk = int(np.argmax(np.max(np.abs(i_line), axis=1)))
    i_peak = float(np.max(np.abs(i_line)))
    per = max(1, int(round(1 / f / dt_out)))
    last = np.abs(i_line[:, -per:])
    i0_pk = float(last.max())
    th = w * sol.t[-per:]
    b = 2 * np.mean(i_line[0, -per:] * np.sin(th))
    a = 2 * np.mean(i_line[0, -per:] * np.cos(th))
    i0_fund = math.hypot(a, b) / math.sqrt(2)
    t_decay = None
    n_cyc = len(sol.t) // per
    peaks = [float(np.abs(i_line[:, k * per : (k + 1) * per]).max()) for k in range(n_cyc)]
    for k in range(n_cyc):
        if all(p < 2 * i0_pk for p in peaks[k:]):
            t_decay = float(sol.t[k * per])
            break
    return InrushResult(
        t=sol.t,
        i_line=i_line,
        lam_pu=sol.y[3:6] / lam_n,
        i_peak=i_peak,
        i_peak_phase=k_pk,
        i0_peak_steady=i0_pk,
        i0_rms_fund=float(i0_fund),
        t_decay=t_decay,
        c_inst=c_i,
    )
