"""Fit the experiment-3 impedances to the 2025 short-circuit table (6.4) — OCC unchanged.

The 2025 OCC (table 6.3) already agrees with the model fitted to the 2026 data, but all three
2025 fault currents are ≈ 1.85× the model's with the SAME ratios Ik(2)/Ik(3), Ik(1)/Ik(3).
So the 2025 data scale every reactance (X_l, k_a, X2, X0) by one factor λ. Ra stays measured.
Run from backend/: python ../scripts/fit_synchronous_2025.py
"""

import numpy as np
from scipy.optimize import least_squares

from vel.experiments import registry

M = registry.get("synchronous")
D = {
    "Ik3": ([0.2, 0.6, 1, 1.23, 1.6, 1.8], [0.1, 0.25, 0.44, 0.56, 0.71, 0.8]),
    "Ik2": ([0.4, 0.5, 0.65, 0.8, 1.15], [0.23, 0.3, 0.4, 0.5, 0.7]),
    "Ik1": ([0.26, 0.41, 0.52, 0.67, 0.9], [0.2, 0.37, 0.47, 0.6, 0.83]),
}


def spec_of(lam: float):  # type: ignore[no-untyped-def]
    s = M.default_spec()
    e = s.ecm
    return s.model_copy(
        update={
            "ecm": e.model_copy(
                update={"Xl": e.Xl * lam, "k_a": e.k_a * lam, "X2": e.X2 * lam, "X0": e.X0 * lam}
            )
        }
    )


def model(spec, key, ifs):  # type: ignore[no-untyped-def]
    sd = M.studies["short_circuit"]
    c = sd.default_circuit(spec, "")
    doc = {k: v.model_dump() for k, v in c.items()} if isinstance(c, dict) else c.model_dump()
    out = M.execute("short_circuit", spec, doc, {**sd.default_case(spec), "If_values": ifs})
    return np.array([r[key] for r in out.result["tables"][0]["rows"]])


def resid(p):  # type: ignore[no-untyped-def]
    s = spec_of(p[0])
    return np.concatenate([(model(s, k, i) - np.array(v)) / 0.01 for k, (i, v) in D.items()])


if __name__ == "__main__":
    res = least_squares(resid, [0.5], bounds=([0.1], [2.0]))
    s = spec_of(res.x[0])
    print("lambda =", round(float(res.x[0]), 4), "Xs_unsat =", round(s.ecm.Xl + s.occ.a * s.ecm.k_a, 1))
    print("residuals [0.01 A]:", np.round(resid(res.x), 2).tolist())
