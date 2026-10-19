"""Fit the experiment-4 machine to the 2025 report (tables 4.4, 4.5, 4.6), Δ at 220–230 V.

Interpretation (see docs/lab-data-2025-exp4.md): stator in Δ; the wattmeter reading P_W of
tables 4.4 and 4.6 is one phase (P1 = 3·P_W); in table 4.5 the written Pk is not usable with
that reading (it gives cos φ > 1), so only Ik is fitted there. R1 (33.3 Ω) and k are kept.
Run from backend/: python ../scripts/fit_wound_rotor_2025.py
"""

import math

import numpy as np
from scipy.optimize import least_squares
from vel.engine.simulate import operating_point
from vel.experiments.common import with_param
from vel.experiments.wound_rotor import templates as T
from vel.experiments.wound_rotor.spec import nameplate_fit

NL = [(220, 0.44, 19), (180, 0.31, 14), (150, 0.25, 11), (100, 0.18, 9)]
LR = [(90, 0.78), (100, 0.9), (115, 1.03), (130, 1.24)]
LOAD_U = 230.0
LOAD = [  # M, I1, P_W, n
    (0.0, 0.48, 29, 1467),
    (0.212, 0.48, 36, 1452),
    (0.3, 0.49, 42.5, 1446),
    (0.4, 0.5, 46, 1439),
    (0.5, 0.51, 51, 1432),
    (0.6, 0.51, 58, 1427),
]


def spec_of(p):
    s = nameplate_fit()
    x1, r2p, xm, rfe, pfw = p
    k = s.ecm.k
    return s.model_copy(
        update={
            "nameplate": s.nameplate.model_copy(
                update={"connection": "D", "U_n": 230.0, "I_n": 1.44}
            ),
            "ecm": s.ecm.model_copy(
                update={
                    "X1": x1,
                    "X2": x1 / k**2,
                    "R2": r2p / k**2,
                    "Xm": xm,
                    "R_fe": rfe,
                    "P_fw_n": pfw,
                }
            ),
        }
    )


def resid(p):
    s = spec_of(p)
    r = []
    for u, i, pw in NL:
        op = operating_point(T.motor(u, 50, "D"), s)
        r += [(op.readings["A"]["I"] - i) / 0.01, (op.readings["W"]["P"] - pw) / 1.0]
    for u, i in LR:
        op = operating_point(T.motor(u, 50, "D", locked=True), s)
        r += [(op.readings["A"]["I"] - i) / 0.01]
    base = T.motor(LOAD_U, 50, "D")
    for m, i, pw, n in LOAD:
        op = operating_point(with_param(base, "M", "M_load", m), s)
        r += [
            (op.readings["A"]["I"] - i) / 0.01,
            (op.readings["W"]["P"] - pw) / 1.0,
            (op.readings["M"]["n"] - n) / 5.0,
        ]
    return np.array(r)


if __name__ == "__main__":
    p0 = [77.0, 21.5, 780.0, 20000.0, 28.0]
    res = least_squares(
        resid,
        p0,
        bounds=([5, 2, 100, 1000, 0], [500, 200, 5000, 1e6, 200]),
        x_scale=[50, 10, 300, 10000, 10],
    )
    rr = resid(res.x)
    print("X1=X2', R2', Xm, R_fe, P_fw =", [round(float(v), 4) for v in res.x])
    print(
        "rms (tolerance units):",
        math.sqrt(float(np.mean(rr**2))),
        "max:",
        float(np.max(np.abs(rr))),
    )
    print("residuals:", np.round(rr, 2).tolist())
