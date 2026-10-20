"""Induction machine in the time domain: the 5th-order dq model (Krause), synchronous frame.

States: stator and rotor flux linkages ψs, ψr (space vectors, amplitude-invariant, referred to
the stator) and the mechanical speed ω_m. Per winding, with the leakage and magnetizing
reactances of the spec taken at f_n (L = X/ω_n):

    dψs/dt = v_s − R1·i_s − jω_e·ψs
    dψr/dt =      − R2'·i_r − j(ω_e − ω_r)·ψr,      ω_r = (p/2)·ω_m
    [ψs; ψr] = [[Ls, Lm], [Lm, Lr]]·[i_s; i_r],      Ls = L1σ + Lm,  Lr = L2σ' + Lm
    M_em = (3/2)·(p/2)·Im(ψs* · i_s)
    J·dω_m/dt = M_em − M_brake·tanh(ω_m/ω_ε) − M_fw(ω_m)

A start is a sequence of SEGMENTS, integrated one after another with the states carried over
(event-segmented integration): each segment fixes the winding voltage (or leaves the stator
open), the winding connection that turns winding currents into line currents, and the extra
rotor resistance (wound rotor starter). Within a segment the system is smooth, so the stiff
solver never steps across a discontinuity.

* Stator open (the dead time of an open-transition star-delta changeover): i_s = 0, so
  ψs = (Lm/Lr)·ψr and only ψr and ω_m evolve: dψr/dt = −(R2'/Lr)·ψr − j(ω_e − ω_r)·ψr.
  The rotor flux keeps turning with the rotor and decays — the reason the reclosing current
  spike depends on the dead time.
* The supply is ideal. The phase angle of v_a at switch-on sets the DC offset of the currents.
* Friction and windage: P_fw ∝ n² as in the steady-state model, i.e. M_fw = P_fw,n/ω_n·(n/n_n).
* The brake holds a set torque against the rotation; tanh makes it vanish at standstill.
* NOT modelled: iron loss (the studies report its effect on the steady state), saturation of
  the leakage paths at starting current, deep-bar effect (R2', X2' constant), supply
  impedance, contact bounce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from vel.experiments.induction_motor.spec import MotorSpec

FArray = npt.NDArray[np.float64]
CArray = npt.NDArray[np.complex128]
A120 = complex(-0.5, math.sqrt(3) / 2)
W_EPS = 0.5  # rad/s: speed over which the brake torque builds up from zero
SQ3 = math.sqrt(3)


@dataclass(frozen=True)
class ImParams:
    """Per-winding equivalent circuit referred to the stator, reactances at f_n."""

    R1: float
    X1: float
    R2p: float
    X2p: float
    Xm: float
    f_n: float
    poles: int
    k_fw: float  # M_fw = k_fw·ω_m (P_fw ∝ n²)

    @staticmethod
    def of_motor(spec: MotorSpec) -> ImParams:
        e, n = spec.ecm, spec.nameplate
        w_n = 2 * math.pi * n.n_n / 60
        return ImParams(e.R1, e.X1, e.R2p, e.X2p, e.Xm, n.f_n, n.poles, e.P_fw_n / w_n / w_n)


@dataclass(frozen=True)
class Segment:
    """One switching state, from the end of the previous segment until t_end [s]."""

    t_end: float
    U_winding: float | None  # RMS voltage across each winding; None = stator open
    phase_deg: float = 0.0  # angle of that voltage relative to phase L1-N at t = 0
    connection: Literal["Y", "D"] = "Y"  # how line currents are formed from winding currents
    R2_extra: float = 0.0  # added rotor resistance per phase, referred to the stator [Ω]
    label: str = ""


@dataclass
class StartResult:
    t: FArray  # s
    i_line: FArray  # A, line current L1 (instantaneous)
    i_line_rms: FArray  # A, RMS envelope of the line current
    n: FArray  # rpm
    M_em: FArray  # N·m, electromagnetic torque
    n_final: float
    i_line_rms_final: float
    i_peak: float  # A, largest |instantaneous| line current
    t_95: float | None  # s, time to reach 95 % of the final speed
    solver: dict[str, float | int | str]
    events: list[dict[str, float | str]] = field(default_factory=list)


def simulate(
    m: ImParams,
    segments: list[Segment],
    *,
    f: float,
    J: float,
    M_brake: float = 0.0,
    dt_out: float = 2.5e-4,
) -> StartResult:
    """Integrate the segments in order, from standstill with zero fluxes."""
    if not segments or any(
        b.t_end <= a.t_end for a, b in zip(segments, segments[1:], strict=False)
    ):
        raise ValueError("segments must have increasing end times")
    wb = 2 * math.pi * m.f_n
    lm = m.Xm / wb
    ls, lr = m.X1 / wb + lm, m.X2p / wb + lm
    d = ls * lr - lm * lm
    we = 2 * math.pi * f
    pp = m.poles / 2
    u_ref = max(s.U_winding or 0.0 for s in segments) or 1.0
    psi_b = math.sqrt(2) * u_ref / we
    x = np.zeros(5)  # ψs (2), ψr (2), ω_m
    t0 = 0.0
    ts: list[FArray] = []
    ps_all: list[CArray] = []
    pr_all: list[CArray] = []
    wm_all: list[FArray] = []
    conn_all: list[FArray] = []  # 1 for Δ samples, 0 for Y
    nfev = 0
    events: list[dict[str, float | str]] = []
    for k, seg in enumerate(segments):
        r2 = m.R2p + seg.R2_extra
        open_stator = seg.U_winding is None
        u_seg = seg.U_winding or 0.0
        ang = math.radians(seg.phase_deg)
        v_s = math.sqrt(2) * u_seg * complex(math.cos(ang), math.sin(ang))

        def rhs(
            _t: float, y: FArray, v_s: complex = v_s, r2: float = r2, op: bool = open_stator
        ) -> list[float]:
            pr = complex(y[2], y[3])
            wm = y[4]
            if op:
                dpr = -(r2 / lr) * pr - 1j * (we - pp * wm) * pr
                m_em = 0.0
                dps = 0j
            else:
                ps = complex(y[0], y[1])
                i_s = (lr * ps - lm * pr) / d
                i_r = (ls * pr - lm * ps) / d
                dps = v_s - m.R1 * i_s - 1j * we * ps
                dpr = -r2 * i_r - 1j * (we - pp * wm) * pr
                m_em = 1.5 * pp * (ps.conjugate() * i_s).imag
            m_load = M_brake * math.tanh(wm / W_EPS) + m.k_fw * wm
            return [dps.real, dps.imag, dpr.real, dpr.imag, (m_em - m_load) / J]

        if open_stator:
            # no stator current: the stator flux is the rotor flux seen through Lm
            pr0 = complex(x[2], x[3])
            ps0 = lm / lr * pr0
            x[0], x[1] = ps0.real, ps0.imag
        grid = np.arange(t0, seg.t_end, dt_out)
        grid = grid[grid > t0] if k else grid
        t_eval = np.append(grid, seg.t_end)  # the segment end is always a sample: states carry over
        atol = [1e-7 * psi_b] * 4 + [1e-6 * we]
        sol = solve_ivp(
            rhs, (t0, seg.t_end), x, method="Radau", t_eval=t_eval, rtol=1e-7, atol=atol
        )
        if not sol.success:
            raise RuntimeError(f"transient solver failed in segment {k + 1}: {sol.message}")
        nfev += int(sol.nfev)
        y = sol.y
        pr = y[2] + 1j * y[3]
        ps = (lm / lr) * pr if open_stator else y[0] + 1j * y[1]
        ts.append(sol.t)
        ps_all.append(ps)
        pr_all.append(pr)
        wm_all.append(y[4])
        conn_all.append(np.full(sol.t.size, 1.0 if seg.connection == "D" else 0.0))
        x = np.array(y[:, -1], dtype=float)
        if open_stator:  # leave the dead time with the stator flux the rotor flux induces
            ps_end = lm / lr * complex(x[2], x[3])
            x[0], x[1] = ps_end.real, ps_end.imag
        if k:
            events.append({"t": t0, "label": seg.label or f"שלב {k + 1}"})
        t0 = seg.t_end

    t = np.concatenate(ts)
    ps = np.concatenate(ps_all)
    pr = np.concatenate(pr_all)
    wm = np.concatenate(wm_all)
    is_d = np.concatenate(conn_all) > 0.5
    open_mask = np.concatenate(
        [np.full(a.size, s.U_winding is None) for a, s in zip(ts, segments, strict=True)]
    )
    i_s = np.where(open_mask, 0j, (lr * ps - lm * pr) / d)
    rot = np.exp(1j * we * t)
    i_ab = i_s * rot
    i_a = i_ab.real
    i_c = (i_ab * A120).real
    # Δ: line L1 current = i_a − i_c (winding a between L1 and L2, winding c between L3 and L1)
    i_line = np.where(is_d, i_a - i_c, i_a)
    i_rms = np.abs(i_s) / math.sqrt(2) * np.where(is_d, SQ3, 1.0)
    n_rpm = wm * 60 / (2 * math.pi)
    m_em = np.where(open_mask, 0.0, 1.5 * pp * (np.conj(ps) * i_s).imag)
    n_fin = float(n_rpm[-1])
    above = np.nonzero(n_rpm >= 0.95 * n_fin)[0]
    return StartResult(
        t=t,
        i_line=i_line,
        i_line_rms=i_rms,
        n=n_rpm,
        M_em=m_em,
        n_final=n_fin,
        i_line_rms_final=float(i_rms[-1]),
        i_peak=float(np.max(np.abs(i_line))),
        t_95=float(t[above[0]]) if n_fin > 1 and above.size else None,
        solver={"method": "Radau", "rtol": 1e-7, "nfev": nfev, "steps_out": int(t.size)},
        events=events,
    )


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
    """Direct-on-line start: one segment."""
    u_w = U_line if connection == "D" else U_line / SQ3
    # a Δ winding (L1–L2) sees the line voltage, which leads L1–N by 30°
    phase = angle_deg + (30.0 if connection == "D" else 0.0)
    seg = Segment(t_end, u_w, phase, connection)
    return simulate(ImParams.of_motor(spec), [seg], f=f, J=J, M_brake=M_brake, dt_out=dt_out)


def star_delta_start(
    spec: MotorSpec,
    *,
    U_line: float,
    f: float,
    J: float,
    t_switch: float,
    t_dead: float,
    M_brake: float = 0.0,
    t_end: float = 1.5,
    angle_deg: float = 0.0,
    dt_out: float = 2.5e-4,
) -> StartResult:
    """Star-delta start with an open transition: Y until t_switch, stator open for t_dead,
    then Δ. The windings must be rated for the line voltage (a Δ machine on this supply)."""
    segs = [Segment(t_switch, U_line / SQ3, angle_deg, "Y", label="כוכב")]
    if t_dead > 0:
        segs.append(Segment(t_switch + t_dead, None, 0.0, "D", label="מעבר (מנותק)"))
    segs.append(Segment(t_end, U_line, angle_deg + 30.0, "D", label="משולש"))
    return simulate(ImParams.of_motor(spec), segs, f=f, J=J, M_brake=M_brake, dt_out=dt_out)


@dataclass(frozen=True)
class VfRamp:
    """Scalar V/f control of an inverter, fundamental (average) model.

    f(t) rises linearly from f_start to f_target in t_ramp, then stays. The winding voltage
    follows U(f) = U_boost + (U_n − U_boost)·f/f_n (IR-compensation boost at low frequency),
    capped at U_n above f_n (field weakening)."""

    U_n: float  # RMS winding voltage at f_n
    f_n: float
    f_target: float
    t_ramp: float
    boost: float = 0.0  # U_boost / U_n
    f_start: float = 0.0

    def f(self, t: float) -> float:
        if self.t_ramp <= 0 or t >= self.t_ramp:
            return self.f_target
        return self.f_start + (self.f_target - self.f_start) * t / self.t_ramp

    def u(self, f: float) -> float:
        ub = self.boost * self.U_n
        return min(self.U_n, ub + (self.U_n - ub) * abs(f) / self.f_n)

    def theta(self, t: FArray) -> FArray:
        """Supply angle ∫2πf dt (rad)."""
        tr = self.t_ramp
        a = (self.f_target - self.f_start) / tr if tr > 0 else 0.0
        in_ramp = 2 * math.pi * (self.f_start * t + 0.5 * a * t * t)
        th_r = 2 * math.pi * (self.f_start * tr + 0.5 * a * tr * tr) if tr > 0 else 0.0
        after = th_r + 2 * math.pi * self.f_target * (t - max(tr, 0.0))
        return np.where(t < tr, in_ramp, after)


def vf_start(
    m: ImParams,
    ramp: VfRamp,
    *,
    connection: Literal["Y", "D"],
    J: float,
    M_brake: float = 0.0,
    t_end: float = 2.0,
    dt_out: float = 2.5e-4,
) -> StartResult:
    """Start on an inverter with a V/f ramp. Same dq model as `simulate`, in a frame turning
    with the (time-varying) supply frequency, so v_s = √2·U(f(t)) is real. Integrated in two
    pieces (ramp, then constant frequency) so the solver never steps across the kink.

    NOT modelled (average model): PWM ripple and its harmonic losses, dead time, the DC-link
    voltage limit and the inverter's current limit — the computed current is what the motor
    asks for, which a real drive may clip."""
    wb = 2 * math.pi * m.f_n
    lm = m.Xm / wb
    ls, lr = m.X1 / wb + lm, m.X2p / wb + lm
    d = ls * lr - lm * lm
    pp = m.poles / 2

    def rhs(t: float, y: FArray) -> list[float]:
        ps, pr, wm = complex(y[0], y[1]), complex(y[2], y[3]), y[4]
        fe = ramp.f(t)
        we = 2 * math.pi * fe
        v = math.sqrt(2) * ramp.u(fe)
        i_s = (lr * ps - lm * pr) / d
        i_r = (ls * pr - lm * ps) / d
        dps = v - m.R1 * i_s - 1j * we * ps
        dpr = -m.R2p * i_r - 1j * (we - pp * wm) * pr
        m_em = 1.5 * pp * (ps.conjugate() * i_s).imag
        m_load = M_brake * math.tanh(wm / W_EPS) + m.k_fw * wm
        return [dps.real, dps.imag, dpr.real, dpr.imag, (m_em - m_load) / J]

    psi_b = math.sqrt(2) * ramp.U_n / wb
    atol = [1e-7 * psi_b] * 4 + [1e-6 * wb]
    pieces = [(0.0, min(ramp.t_ramp, t_end))] if ramp.t_ramp > 0 else []
    if t_end > ramp.t_ramp:
        pieces.append((max(ramp.t_ramp, 0.0), t_end))
    x = np.zeros(5)
    ts: list[FArray] = []
    ys: list[FArray] = []
    nfev = 0
    for k, (a, b) in enumerate(pieces):
        grid = np.arange(a, b, dt_out)
        grid = grid[grid > a] if k else grid
        sol = solve_ivp(
            rhs, (a, b), x, method="Radau", t_eval=np.append(grid, b), rtol=1e-7, atol=atol
        )
        if not sol.success:
            raise RuntimeError(f"transient solver failed: {sol.message}")
        nfev += int(sol.nfev)
        ts.append(sol.t)
        ys.append(sol.y)
        x = np.array(sol.y[:, -1], dtype=float)
    t = np.concatenate(ts)
    y = np.concatenate(ys, axis=1)
    ps, pr, wm = y[0] + 1j * y[1], y[2] + 1j * y[3], y[4]
    i_s = (lr * ps - lm * pr) / d
    i_ab = i_s * np.exp(1j * ramp.theta(t))
    i_a = i_ab.real
    i_c = (i_ab * A120).real
    is_d = connection == "D"
    i_line = i_a - i_c if is_d else i_a
    i_rms = np.abs(i_s) / math.sqrt(2) * (SQ3 if is_d else 1.0)
    n_rpm = wm * 60 / (2 * math.pi)
    m_em = 1.5 * pp * (np.conj(ps) * i_s).imag
    n_fin = float(n_rpm[-1])
    above = np.nonzero(n_rpm >= 0.95 * n_fin)[0]
    events: list[dict[str, float | str]] = []
    if 0 < ramp.t_ramp < t_end:
        events.append({"t": ramp.t_ramp, "label": f"סוף הרמפה ({ramp.f_target:g} Hz)"})
    return StartResult(
        t=t,
        i_line=i_line,
        i_line_rms=i_rms,
        n=n_rpm,
        M_em=m_em,
        n_final=n_fin,
        i_line_rms_final=float(i_rms[-1]),
        i_peak=float(np.max(np.abs(i_line))),
        t_95=float(t[above[0]]) if n_fin > 1 and above.size else None,
        solver={"method": "Radau", "rtol": 1e-7, "nfev": nfev, "steps_out": int(t.size)},
        events=events,
    )
