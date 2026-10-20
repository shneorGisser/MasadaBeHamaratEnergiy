"""Our own solver for the radial lab feeder: the independent second engine.

Every network study is solved twice — by pandapower (the general engine) and by this short,
readable implementation of the same textbook equations — and the two must agree. A
disagreement means a modelling or input error, and the run says so.

Load flow (per unit, S_base = 1 MVA, V_base = the bus's nominal voltage, ideal ratio): the
slack B0 holds 1∠0; the transformer is a T model (series impedance halved on either side of
the magnetising branch g − jb, which pandapower also uses by default); loads are constant
power. Nodal fixed point V = Y_LL⁻¹·(conj(S/V) − Y_L0·V0), converged to 1e-12.

Short circuit, IEC 60909-0 (equivalent voltage source c·U_n/√3 at the fault, no loads, no
magnetising branch):

* grid feeder Z_Q = c·U_nQ²/S''kQ, R/X given, referred to LV by (U2/U1)²;
* transformer Z_T = uk·U_rT²/S_rT, R_T = ur·…, corrected by K_T = 0.95·c_max/(1 + 0.6·x_T)
  for the MAXIMUM currents only (as pandapower does; whether the standard also asks for it in
  the minimum case is not settled here — it moves I''k,min by ≈ 1 %);
* cables: R at 20 °C for the maximum currents, at 80 °C (×1.24) for the minimum ones;
* c = 1.10 / 0.95 (LV, +10 % tolerance), 1.10 / 1.00 (MV) — IEC 60909-0:2016 Table 1.
  (pandapower takes c_min = 0.90 for a +10 % LV grid; its minimum case is therefore run with
  lv_tol_percent = 6, whose c_min is 0.95 — c_max does not enter the minimum case);
* i_p = κ·√2·I''k, κ = 1.02 + 0.98·e^(−3R/X) (method C coincides with the R/X of the fault
  path for a radial feeder: every element sits in series);
* I_th = I''k·√(m + n), n = 1 (far from generators), m from κ and T_k;
* single phase to earth: I''k1 = √3·c·U_n / |2·Z1 + Z0|. The Dyn transformer isolates the MV
  zero sequence, so Z0 = K_T·Z_T + Σ Z0,cable (Z0' = (R0/R, X0/X)·Z').
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vel.experiments.network.spec import BUSES, NetworkSpec

S_BASE = 1e6  # VA
ALPHA_CU = 0.004  # 1/K, IEC 60909 uses 0.004 for Cu and Al
C_LV = {"max": 1.10, "min": 0.95}
C_MV = {"max": 1.10, "min": 1.00}


@dataclass
class LoadFlow:
    U: dict[str, complex]  # bus voltage, pu
    I_branch: dict[str, float]  # A, current magnitude (LV side for the transformer)
    loading: dict[str, float]  # % of the rating
    P_loss_kW: float
    iterations: int


def _branches(spec: NetworkSpec) -> dict[str, complex]:
    """Series impedances in pu (cables at 20 °C)."""
    t = spec.trafo
    zb_lv = (t.U2_V**2) / S_BASE
    zt = t.uk / 100 * S_BASE / (t.S_n_kVA * 1e3)
    rt = t.ur / 100 * S_BASE / (t.S_n_kVA * 1e3)
    out = {"T": complex(rt, math.sqrt(max(zt * zt - rt * rt, 0.0)))}
    for k, c in (("C1", spec.cable1), ("C2", spec.cable2)):
        out[k] = complex(c.r, c.x) * c.L_m / 1000 / zb_lv
    return out


def load_flow(spec: NetworkSpec, tol: float = 1e-12, max_iter: int = 200) -> LoadFlow:
    t = spec.trafo
    z = _branches(spec)
    sn = t.S_n_kVA * 1e3 / S_BASE
    g = t.P_0_kW * 1e3 / S_BASE
    ym_abs = t.i0 / 100 * sn
    ym = complex(g, -math.sqrt(max(ym_abs * ym_abs - g * g, 0.0)))
    # nodes: 0 = B0 (slack), 1 = T midpoint, 2 = B1, 3 = B2, 4 = B3
    y = np.zeros((5, 5), dtype=complex)

    def add(a: int, b: int, zz: complex) -> None:
        yy = 1 / zz
        y[a, a] += yy
        y[b, b] += yy
        y[a, b] -= yy
        y[b, a] -= yy

    add(0, 1, z["T"] / 2)
    add(1, 2, z["T"] / 2)
    y[1, 1] += ym
    add(2, 3, z["C1"])
    add(3, 4, z["C2"])
    lo = spec.loads
    s = np.zeros(5, dtype=complex)
    for node, p, pf in ((3, lo.P2_kW, lo.pf2), (4, lo.P3_kW, lo.pf3)):
        p_pu = p * 1e3 / S_BASE
        s[node] = -complex(p_pu, p_pu * math.tan(math.acos(pf)))
    v = np.ones(5, dtype=complex)
    yll = y[1:, 1:]
    yl0 = y[1:, 0]
    iterations = 0
    for _ in range(max_iter):
        iterations += 1
        rhs = np.conj(s[1:] / v[1:]) - yl0 * v[0]
        new = np.linalg.solve(yll, rhs)
        err = float(np.max(np.abs(new - v[1:])))
        v[1:] = new
        if err < tol:
            break
    else:
        raise RuntimeError("load flow did not converge (overloaded feeder?)")
    ib_lv = S_BASE / (math.sqrt(3) * t.U2_V)
    i_t = abs((v[1] - v[2]) / (z["T"] / 2)) * ib_lv
    i_c1 = abs((v[2] - v[3]) / z["C1"]) * ib_lv
    i_c2 = abs((v[3] - v[4]) / z["C2"]) * ib_lv
    s_in = v[0] * np.conj(y[0] @ v)
    p_load = -float(np.real(s[3] + s[4]))
    return LoadFlow(
        U={"B0": complex(v[0]), "B1": complex(v[2]), "B2": complex(v[3]), "B3": complex(v[4])},
        I_branch={"T": i_t, "C1": i_c1, "C2": i_c2},
        loading={
            # as pandapower: the larger apparent power of the two sides over S_n
            "T": 100
            * max(abs(s_in), abs(v[2] * np.conj((v[1] - v[2]) / (z["T"] / 2))))
            * S_BASE
            / (t.S_n_kVA * 1e3),
            "C1": 100 * i_c1 / spec.cable1.I_max,
            "C2": 100 * i_c2 / spec.cable2.I_max,
        },
        P_loss_kW=(float(np.real(s_in)) - p_load) * S_BASE / 1e3,
        iterations=iterations,
    )


@dataclass
class ShortCircuit:
    case: str
    Ik3: dict[str, float]  # kA
    ip: dict[str, float]  # kA
    Ith: dict[str, float]  # kA (T_k = 1 s)
    Ik1: dict[str, float]  # kA
    Z1: dict[str, complex]  # Ω at the bus's voltage
    Z0: dict[str, complex]


def kappa(r_over_x: float) -> float:
    return 1.02 + 0.98 * math.exp(-3 * r_over_x)


def ith_factor_m(k: float, f: float, tk: float) -> float:
    if k <= 1.0:
        return 0.0
    a = math.log(k - 1)
    return 1 / (2 * f * tk * a) * (math.exp(4 * f * tk * a) - 1)


def short_circuit(spec: NetworkSpec, case: str, tk: float = 1.0) -> ShortCircuit:
    g, t = spec.grid, spec.trafo
    c_lv, c_mv = C_LV[case], C_MV[case]
    un_mv, un_lv = g.U_n_kV * 1e3, t.U2_V
    sk = (g.Sk_max_MVA if case == "max" else g.Sk_min_MVA) * 1e6
    zq_abs = c_mv * un_mv**2 / sk
    xq = zq_abs / math.sqrt(1 + g.RX**2)
    zq = complex(g.RX * xq, xq)  # at MV
    ratio2 = (t.U2_V / (t.U1_kV * 1e3)) ** 2
    zt_abs = t.uk / 100 * un_lv**2 / (t.S_n_kVA * 1e3)
    rt = t.ur / 100 * un_lv**2 / (t.S_n_kVA * 1e3)
    xt = math.sqrt(max(zt_abs**2 - rt**2, 0.0))
    k_t = 0.95 * C_LV["max"] / (1 + 0.6 * xt / (un_lv**2 / (t.S_n_kVA * 1e3)))
    zt = (k_t if case == "max" else 1.0) * complex(rt, xt)
    temp = 1.0 if case == "max" else 1 + ALPHA_CU * 60
    z1c, z0c = [], []
    for cab in (spec.cable1, spec.cable2):
        lk = cab.L_m / 1000
        z1c.append(complex(cab.r * temp, cab.x) * lk)
        z0c.append(complex(cab.r * cab.r0_r * temp, cab.x * cab.x0_x) * lk)
    z1 = {"B0": zq}
    z1["B1"] = zq * ratio2 + zt
    z1["B2"] = z1["B1"] + z1c[0]
    z1["B3"] = z1["B2"] + z1c[1]
    z0 = {"B0": complex(g.RX * xq, xq), "B1": zt}  # MV: X0 = X1, R0/X0 = R/X (assumed)
    z0["B2"] = z0["B1"] + z0c[0]
    z0["B3"] = z0["B2"] + z0c[1]
    out = ShortCircuit(case, {}, {}, {}, {}, z1, z0)
    for b in BUSES:
        un, c = (un_mv, c_mv) if b == "B0" else (un_lv, c_lv)
        ik = c * un / (math.sqrt(3) * abs(z1[b])) / 1e3
        k = kappa(z1[b].real / z1[b].imag)
        out.Ik3[b] = ik
        out.ip[b] = k * math.sqrt(2) * ik
        out.Ith[b] = ik * math.sqrt(ith_factor_m(k, g.f, tk) + 1.0)
        out.Ik1[b] = math.sqrt(3) * c * un / abs(2 * z1[b] + z0[b]) / 1e3
    return out
