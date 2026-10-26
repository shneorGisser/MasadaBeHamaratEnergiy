"""Fit the experiment-2 squirrel-cage motor (Appli-com AP-3030) to the 2026 bench sheet,
jointly over no-load, locked-rotor and load, and test which stator connection the lab used.

Plate (photo, 26.10.2026): 0.37 kW, 380/660 V Δ/Y, 1.13/0.65 A, cos φ 0.67, 1400 rpm, 50 Hz.
Sheet: vel.labdata induction_motor_2026 (docs/lab-data-2026-exp2.md for the readings).

The sheet does not say whether the stator was in Δ (rated at 380 V) or in Y (each winding at
220 V, a third of rated torque). The terminal behaviour can be fitted either way — the two
fits differ only by the factor 3 in winding impedances. What discriminates is the plate: each
fit is evaluated at the plate's rated condition (winding at 380 V, 1400 rpm). Free: R1,
X1 = X2', R2', Xm, R_fe, P_fw. Run from backend/: python ../scripts/fit_induction_2026.py
"""

from __future__ import annotations

import math
import sys

import numpy as np
from scipy.optimize import least_squares

from vel.engine.simulate import operating_point, operating_point_at_slip
from vel.experiments.induction_motor import templates as tpl
from vel.experiments.induction_motor.spec import MotorNameplate, MotorSpec, assumed_lab_motor
from vel.labdata import get

DS = {t.study_kind: t for t in get("induction_motor_2026").tables}


def rows(kind: str) -> list[dict[str, float]]:
    t = DS[kind]
    keys = [k for k, _ in t.columns]
    return [dict(zip(keys, r, strict=True)) for r in t.rows]  # type: ignore[arg-type]


def plate(conn: str) -> MotorNameplate:
    if conn == "D":
        return MotorNameplate(
            P_n=370, U_n=380, I_n=1.13, f_n=50, n_n=1400, poles=4, connection="D", cos_phi_n=0.67
        )
    return MotorNameplate(
        P_n=370, U_n=660, I_n=0.65, f_n=50, n_n=1400, poles=4, connection="Y", cos_phi_n=0.67
    )


def spec_of(p: np.ndarray, conn: str) -> MotorSpec:
    r1, x, r2p, xm, rfe, pfw = (float(v) for v in p)
    base = assumed_lab_motor()
    return base.model_copy(
        update={
            "nameplate": plate(conn),
            "ecm": base.ecm.model_copy(
                update={
                    "R1": r1,
                    "X1": x,
                    "X2p": x,
                    "R2p": r2p,
                    "Xm": xm,
                    "R_fe": rfe,
                    "P_fw_n": pfw,
                }
            ),
        }
    )


def resid(p: np.ndarray, conn: str) -> np.ndarray:
    """Lab connection `conn`; residuals in tolerance units (0.01 A, 1 W, 5 rpm)."""
    s = spec_of(p, conn)
    r: list[float] = []
    for row in rows("no_load"):
        op = operating_point(tpl.no_load(row["U1L"], 50, conn), s)  # type: ignore[arg-type]
        r += [
            (op.readings["A"]["I"] - row["I0"]) / 0.01,
            (op.readings["W"]["P"] - row["P_W"]) / 1.0,
        ]
    for row in rows("locked_rotor"):
        op = operating_point(tpl.locked_rotor(row["U_k"], 50, conn), s)  # type: ignore[arg-type]
        r += [
            (op.readings["A"]["I"] - row["I_k"]) / 0.01,
            (op.readings["W"]["P"] - row["P_W"]) / 1.0,
        ]
    for row in rows("load"):
        op = operating_point(tpl.load_test(row["U1L"], 50, conn, row["M"]), s)  # type: ignore[arg-type]
        r += [
            (op.readings["A"]["I"] - row["I1"]) / 0.01,
            (op.readings["W"]["P"] - row["P_W"]) / 1.0,
            (op.readings["M"]["n"] - row["n"]) / 5.0,
        ]
    return np.array(r)


def at_plate(s: MotorSpec) -> dict[str, float]:
    """The fitted machine at the plate's rated condition (winding voltage 380 V, 1400 rpm)."""
    n = s.nameplate
    op = operating_point_at_slip(tpl.load_test(n.U_n, 50, n.connection), s, (1500 - 1400) / 1500)
    i, pw = op.readings["A"]["I"], op.readings["W"]["P"]
    m = op.readings["M"]["M"]
    return {
        "I": i,
        "cos": pw / (n.U_n / math.sqrt(3) * i),
        "P2": m * 1400 * 2 * math.pi / 60,
        "P1": 3 * pw,
    }


def fit(conn: str) -> tuple[np.ndarray, float]:
    k = 3.0 if conn == "D" else 1.0  # Δ winding impedances are 3× the Y-equivalent
    p0 = np.array([30, 45, 40, 550, 6000, 25]) * np.array([k, k, k, k, k, 1])
    res = least_squares(
        resid,
        p0,
        args=(conn,),
        bounds=([1, 5, 2, 100, 500, 0], [2000, 3000, 2000, 30000, 1e6, 200]),
        x_scale=p0,
    )
    rr = resid(res.x, conn)
    return res.x, math.sqrt(float(np.mean(rr**2)))


if __name__ == "__main__":
    for conn in sys.argv[1:] or ["D", "Y"]:
        x, rms = fit(conn)
        s = spec_of(x, conn)
        print(f"== lab connection {conn}")
        print("  R1, X1=X2', R2', Xm, R_fe, P_fw =", [round(float(v), 3) for v in x])
        print("  rms (tolerance units):", round(rms, 3))
        print("  residuals:", np.round(resid(x, conn), 2).tolist())
        print(
            "  at plate (1400 rpm):",
            {k: round(v, 3) for k, v in at_plate(s).items()},
            "plate: I",
            s.nameplate.I_n,
            "cos 0.67 P2 370",
        )
