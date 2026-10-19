"""Fit the DC-machine model to the 2025 lab reports of experiments 5 and 6 (same machine)."""
import math

import numpy as np
from scipy.optimize import least_squares

RA = 12.5
RS = 5.2
W_REF = 2 * math.pi * 2000 / 60


def occ(F, a, Is, m):
    x = np.abs(F)
    return np.sign(F) * a * x / (1 + (x / Is) ** m) ** (1 / m)


# exp 5, table 2.3 (no load, U1 not recorded — assumed 174 V like the other tables)
t23 = dict(If=[0.505, 0.46, 0.43, 0.405, 0.372, 0.339, 0.306],
           I=[0.417, 0.417, 0.417, 0.421, 0.427, 0.438, 0.462],
           n=[2000, 2075, 2100, 2160, 2220, 2300, 2380], U=174.0)
# 2.4 shunt load (U=174.3, If=0.48), sorted by M
t24 = dict(I=[0.358, 0.972, 1.63, 1.23, 1.9, 0.58], n=[2058, 1990, 1895, 1954, 1852, 2053],
           M=[0, 0.5, 1, 0.7, 1.2, 0.2], U=174.3, If=0.48, Rx=0.0)
# 2.5 with R_nosaf = 30 Ω (U=173, If=0.48)
t25 = dict(I=[0.33, 0.56, 0.814, 1.07, 1.32, 1.57], n=[1952, 1840, 1711, 1580, 1448, 1319],
           M=[0, 0.2, 0.4, 0.6, 0.8, 1.0], U=173.0, If=0.48, Rx=30.0)
# 2.8 compound (U=174, If=0.462)
t28 = dict(I=[0.346, 0.578, 0.8, 1.04, 1.3, 1.52], n=[2026, 1950, 1880, 1800, 1732, 1663],
           M=[0, 0.2, 0.4, 0.6, 0.8, 1.0], U=174.0, If=0.462)
# exp 6 table 2.3 OCC rising branch, speed not recorded
o6 = dict(If=[0, 0.1, 0.15, 0.17, 0.19, 0.2, 0.22, 0.25, 0.27],
          E=[5, 78, 111, 122, 137.5, 143, 150, 162, 168])


def resid(p, ub):
    a, Is, m, Fr, kar, rho, s6, M0 = p
    r = []
    # motor speeds: U = E + I(Ra+Rx[+Rs]) + ub ; E = n/2000·OCC(F)
    for t, rx, comp in ((t23, 0.0, False), (t24, 0.0, False), (t25, 30.0, False),
                        (t28, 0.0, True)):
        If = np.array(t["If"]) if isinstance(t["If"], list) else t["If"]
        I = np.array(t["I"])
        F = If + Fr - kar * I + (rho * I if comp else 0)
        e = t["U"] - I * (RA + rx + (RS if comp else 0)) - ub
        n_model = 2000 * e / occ(F, a, Is, m)
        r += list((n_model - np.array(t["n"])) / 20.0)  # 20 rpm ~ reading accuracy
        if "M" in t:
            m_model = occ(F, a, Is, m) / W_REF * I - M0
            r += list((m_model - np.array(t["M"])) / 0.05)
    # exp 6 OCC (scaled by unknown speed ratio s6)
    F6 = np.array(o6["If"]) + Fr
    r += list((s6 * occ(F6, a, Is, m) - np.array(o6["E"])) / 3.0)
    return np.array(r)


for ub in (0.0, 2.0):
    p0 = [600, 0.4, 2.0, 0.01, 0.0, 0.03, 1.2, 0.3]
    lo = [100, 0.05, 1.0, 0.0, 0.0, 0.0, 0.5, 0.0]
    hi = [5000, 3.0, 20.0, 0.1, 0.1, 0.5, 2.5, 1.0]
    res = least_squares(resid, p0, bounds=(lo, hi), args=(ub,))
    rr = resid(res.x, ub)
    print(f"Ub={ub}: cost={res.cost:.2f} rms={math.sqrt(np.mean(rr**2)):.2f}")
    names = ["a", "I_s", "m", "F_res", "k_ar", "rho_s", "s6", "M0"]
    for k, v in zip(names, res.x):
        print(f"   {k} = {v:.5g}")
    a, Is, m, Fr, kar, rho, s6, M0 = res.x
    print("   exp6 OCC speed ≈", 2000 * s6, "rpm")
    print("   OCC(0.48+Fr) at 2000:", occ(0.48 + Fr, a, Is, m))
    # residual detail
    print("   max |res| (units of tolerance):", np.max(np.abs(rr)))
