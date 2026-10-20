"""Study: protection of the feeder — time–current curves, disconnection and selectivity.

The breakers use the thermal-magnetic model of experiment 8 (vel.experiments.installation.
physics.mcb_trip), with the fault currents of the IEC 60909 study. Three checks:

* disconnection: the minimum earth-fault current at the end of each protected zone must trip
  the breaker within t_disc (final circuit, Q3) or 5 s (distribution circuits, Q1, Q2) —
  IEC 60364-4-41, TN system;
* overload: I_n ≤ I_z of the protected cable;
* selectivity: for every fault current up to the maximum at the downstream bus, the
  downstream breaker must trip first. In this model two magnetic releases trip in the same
  t_mag, so selectivity ends at the upstream magnetic threshold — the "partial selectivity"
  of manufacturers' tables. Real breakers can do better (current limitation, energy
  selectivity); that needs the manufacturer's tables, which are not modelled.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from vel.engine.network import direct, pp_model
from vel.experiments.common import Outcome, Param, StudyError, col
from vel.experiments.installation.physics import mcb_trip
from vel.experiments.installation.spec import Mcb
from vel.experiments.network.spec import NetworkSpec

T_DIST = 5.0  # s, distribution circuits (IEC 60364-4-41, 411.3.2.3)
T_MAX_PLOT = 1e4


class ProtectionCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    margin: float = Field(default=0.0, ge=0, le=1, description="required time margin, ×t_down")


def devices(spec: NetworkSpec) -> dict[str, tuple[Mcb, float]]:
    p = spec.protection
    out = {}
    for name, i_n, km, tau in (
        ("Q1", p.Q1_In, p.Q1_km, p.Q1_tau),
        ("Q2", p.Q2_In, p.Q2_km, p.Q2_tau),
        ("Q3", p.Q3_In, p.Q3_km, p.Q3_tau),
    ):
        out[name] = (Mcb(curve="C", tau=tau, k_t=p.k_t, k_m=km, t_mag=p.t_mag), i_n)
    return out


def trip_time(dev: tuple[Mcb, float], current: float) -> float | None:
    t, _ = mcb_trip(dev[0], dev[1], current)
    return t


def selectivity_limit(
    down: tuple[Mcb, float], up: tuple[Mcb, float], i_max: float, margin: float
) -> float | None:
    """Largest current up to i_max for which the downstream breaker always trips first (with
    the margin); None = selective over the whole range."""

    def bad(i: float) -> bool:
        td, tu = trip_time(down, i), trip_time(up, i)
        if tu is None:
            return False  # upstream does not trip at all
        return td is None or tu <= td * (1 + margin)

    grid = np.geomspace(down[1] * 1.0001, i_max, 2000)
    prev = float(grid[0])
    if bad(prev):
        return prev
    for i in grid[1:]:
        if bad(float(i)):
            lo, hi = prev, float(i)  # refine the boundary by bisection
            while hi - lo > 1e-9 * hi:
                mid = 0.5 * (lo + hi)
                lo, hi = (lo, mid) if bad(mid) else (mid, hi)
            return hi
        prev = float(i)
    return None


def run_protection(spec: NetworkSpec, case: ProtectionCase) -> Outcome:
    try:
        pmax = pp_model.short_circuit(spec, "max")
        pmin = pp_model.short_circuit(spec, "min")
        dmax = direct.short_circuit(spec, "max")
        dmin = direct.short_circuit(spec, "min")
    except Exception as exc:  # noqa: BLE001
        raise StudyError("convergence_failure", f"חישוב הקצר נכשל: {exc}") from exc
    dev_engines = max(
        abs(a / b - 1)
        for x, y in ((dmax, pmax), (dmin, pmin))
        for q in ("Ik3", "Ik1")
        for a, b in zip(getattr(x, q).values(), getattr(y, q).values(), strict=True)
    )
    d = devices(spec)
    p = spec.protection
    warnings: list[dict[str, Any]] = [
        {
            "code": "assumed_network",
            "message": "נתוני הרשת והמפסקים מוערכים; τ של Q1 ו-Q2 אינם מקטלוג",
        }
    ]
    # zone: (device, location bus, end-of-zone bus, protected cable, required time)
    zones = (
        ("Q1", "B1", "B2", spec.cable1, T_DIST, "כבל ראשי C1"),
        ("Q2", "B2", "B3", spec.cable2, T_DIST, "כבל לעמדה C2"),
        ("Q3", "B3", "B3", None, p.t_disc, "מעגל העמדה"),
    )
    rows = []
    for name, loc, end, cable, t_req, label in zones:
        mcb, i_n = d[name]
        i_min = pmin.Ik1[end] * 1e3
        t = trip_time(d[name], i_min)
        ok_disc = t is not None and t <= t_req
        ok_ol = cable is None or i_n <= cable.I_max
        rows.append(
            {
                "dev": name,
                "zone": label,
                "In": i_n,
                "I_mag": mcb.k_m * i_n,
                "Ik1_min": i_min,
                "t": t,
                "t_req": t_req,
                "disc": "עומד" if ok_disc else "לא עומד",
                "Iz": None if cable is None else cable.I_max,
                "Ik3_loc": pmax.Ik3[loc],
            }
        )
        if not ok_disc:
            warnings.append(
                {
                    "code": "disconnection_fails",
                    "message": f"{name}: תקלה לאדמה בסוף {label} ({i_min:.0f} A) "
                    + (
                        "אינה מפעילה את המפסק"
                        if t is None
                        else f"מנותקת אחרי {t:.2g} s — יותר מ-{t_req:g} s"
                    ),
                }
            )
        if not ok_ol:
            warnings.append(
                {
                    "code": "overload_unprotected",
                    "message": f"{name}: I_n = {i_n:g} A גדול מהזרם המותר של {label} "
                    f"({cable.I_max:g} A)",  # type: ignore[union-attr]
                }
            )
    sel_rows = []
    params = []
    # a fault just below the downstream breaker: at its own bus
    for down, up, bus in (("Q3", "Q2", "B3"), ("Q2", "Q1", "B2")):
        i_f = pmax.Ik3[bus] * 1e3
        lim = selectivity_limit(d[down], d[up], i_f, case.margin)
        sel_rows.append(
            {
                "pair": f"{down} ← {up}",
                "I_fault": i_f,
                "I_s": lim,
                "verdict": "מלאה" if lim is None else "חלקית",
            }
        )
        if lim is not None:
            warnings.append(
                {
                    "code": "partial_selectivity",
                    "message": f"{down}/{up}: סלקטיביות עד {lim:.0f} A בלבד; בקצר של עד "
                    f"{i_f:.0f} A שני המפסקים מנתקים (במודל: שחרור מגנטי ב-{p.t_mag:g} s בשניהם)",
                }
            )
        params.append(
            Param(
                f"Is_{down}_{up}",
                f"גבול הסלקטיביות {down}/{up}",
                lim,
                "A",
                "הזרם הראשון שבו המפסק העליון מנתק לא אחרי התחתון",
                "analytic",
                undefined_reason="סלקטיביות מלאה עד זרם הקצר המרבי" if lim is None else None,
            )
        )
    t3 = trip_time(d["Q3"], pmin.Ik1["B3"] * 1e3)
    params += [
        Param(
            "t_Q3",
            "זמן ניתוק Q3 בתקלה מזערית לאדמה בעמדה",
            t3,
            "s",
            "",
            "analytic",
            undefined_reason=None if t3 is not None else "המפסק לא מנתק",
        ),
        Param("engines_dev", "הפרש בין pandapower לפותר הישיר", dev_engines, "", "", "analytic"),
    ]
    i0 = 0.95 * p.k_t * min(p.Q1_In, p.Q2_In, p.Q3_In)  # below this nothing trips
    grid = np.geomspace(i0, max(3e4, 3 * pmax.Ik3["B1"] * 1e3), 240)
    tcc = []
    for i in grid:
        r: dict[str, Any] = {"I": float(i)}
        for k, name in (("t3", "Q3"), ("t2", "Q2"), ("t1", "Q1")):
            t = trip_time(d[name], float(i))
            r[k] = t if t is not None and t <= T_MAX_PLOT else None
        tcc.append(r)
    return Outcome(
        status="success_with_warnings" if warnings else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "zones",
                    "title_he": "בדיקת ניתוק והגנת עומס יתר",
                    "columns": [
                        col("dev", "מפסק", ""),
                        col("zone", "מגן על", ""),
                        col("In", "I_n", "A"),
                        col("I_mag", "סף מגנטי", "A"),
                        col("Ik1_min", "I''k1 מזערי בסוף הקטע", "A"),
                        col("t", "זמן ניתוק", "s"),
                        col("t_req", "נדרש", "s"),
                        col("disc", "ניתוק", ""),
                        col("Iz", "I_z כבל", "A"),
                        col("Ik3_loc", "I''k3 במקום (כושר ניתוק נדרש)", "kA"),
                    ],
                    "rows": rows,
                },
                {
                    "id": "selectivity",
                    "title_he": "סלקטיביות",
                    "columns": [
                        col("pair", "תחתון ← עליון", ""),
                        col("I_fault", "קצר מרבי", "A"),
                        col("I_s", "גבול סלקטיביות", "A"),
                        col("verdict", "סלקטיביות", ""),
                    ],
                    "rows": sel_rows,
                },
                {
                    "id": "tcc",
                    "title_he": "אופייני זמן–זרם",
                    "columns": [
                        col("I", "I", "A"),
                        col("t3", "Q3", "s"),
                        col("t2", "Q2", "s"),
                        col("t1", "Q1", "s"),
                    ],
                    "rows": tcc,
                },
            ],
            "parameters": [x.to_json() for x in params],
            "curves": [
                {
                    "id": "tcc",
                    "title_he": "אופייני זמן–זרם (Q3, Q2, Q1)",
                    "x": "I",
                    "y": "t3",
                    "y2": "t2",
                    "y3": "t1",
                    "table": "tcc",
                    "log": True,
                }
            ],
        },
    )
