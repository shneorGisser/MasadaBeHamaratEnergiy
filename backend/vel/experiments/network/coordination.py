"""Study: protection coordination at station level — MV fuse, LV main (fuse or relay), Q1.

Why a second protection study: "protection" grades the three feeder breakers of the lab. This
one asks the questions of the substation that feeds them, the ones ETAP's "Star" view answers:

1. Does the transformer's MV fuse survive the energising inrush (k_inrush·I_n for t_inrush)?
   Criterion: its minimum pre-arcing time at that current is longer than t_inrush.
2. Does the MV fuse back up the LV board? Time to clear a fault on B1 (3-phase and
   phase-to-earth) seen through the Dyn transformer.
3. Is the LV main selective against the MV fuse, and Q1 against the LV main, up to the maximum
   fault current below each? Fuse ↔ fuse: the upstream minimum (pre-arcing) time must exceed the
   downstream total clearing time; relays need a grading interval (case.cti, 0.3 s typical).

Currents through the transformer (Dyn, ratio U1/U2):
  3-phase LV fault I  → MV line current I·U2/U1;
  phase–earth LV fault I → current I/n in one delta winding, i.e. in two MV lines,
  n = U1/(U2/√3) → MV line current I·U2/(√3·U1).
The 3-phase case is the critical one for selectivity (the larger MV current), the earth fault
for MV back-up (the smaller one).

Curves come from pandapower's fuse library (vel.engine.network.devices) and are only used
inside their catalogue range; outside it the answer is "no time", never an extrapolation.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from vel.engine.installation import mcb_trip
from vel.engine.network import pp_model
from vel.engine.network.devices import FuseCurve, Relay, fuse_curve, log_grid
from vel.experiments.common import Outcome, Param, StudyError, col
from vel.experiments.network.protection import devices as feeder_devices
from vel.experiments.network.spec import NetworkSpec


class CoordinationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cti: float = Field(default=0.3, ge=0, le=2, description="grading interval for relays [s]")


Timer = Any  # callable current [A, LV side] -> (t | None, reason | None)


def _fuse_timer(curve: FuseCurve, factor: float) -> Timer:
    """Time at an LV current, for a fuse that carries `factor` × that current."""
    return lambda i: curve.time(i * factor)


def run_coordination(spec: NetworkSpec, case: CoordinationCase) -> Outcome:
    p, t = spec.protection, spec.trafo
    try:
        pmax = pp_model.short_circuit(spec, "max")
        pmin = pp_model.short_circuit(spec, "min")
    except Exception as exc:  # noqa: BLE001
        raise StudyError("convergence_failure", f"חישוב הקצר נכשל: {exc}") from exc
    ratio = t.U2_V / (t.U1_kV * 1e3)  # MV current per LV current, 3-phase fault
    In_mv = t.S_n_kVA / (math.sqrt(3) * t.U1_kV)
    mv_min, mv_tot = fuse_curve(p.F_MV, "min"), fuse_curve(p.F_MV, "total")
    lv_fuse = fuse_curve(p.F_LV)
    relay = Relay(p.R_Is, p.R_tms, p.R_curve, p.R_Iinst or None)
    mcb, q1_in = feeder_devices(spec)["Q1"]

    def q1(i: float) -> tuple[float | None, str | None]:
        tt, _ = mcb_trip(mcb, q1_in, i)
        return (tt, None) if tt is not None else (None, "אינו מנתק")

    lv_main: Timer = lv_fuse.time if p.lv_main == "fuse" else relay.time
    lv_name = p.F_LV if p.lv_main == "fuse" else f"ממסר {p.R_curve} (I_s {p.R_Is:g} A)"
    warnings: list[dict[str, Any]] = [
        {
            "code": "assumed_network",
            "message": "נתוני הרשת מוערכים; עקומות הנתיכים מהספרייה הסטנדרטית של pandapower",
        }
    ]
    params: list[Param] = []

    # 1. inrush
    i_inrush = p.k_inrush * In_mv
    t_melt, why = mv_min.time(i_inrush)
    # below the catalogue: does not melt within its longest listed time — that is a pass
    inrush_ok = i_inrush < mv_min.i_lo if t_melt is None else t_melt > p.t_inrush
    params.append(
        Param(
            "t_melt_inrush",
            f"זמן התכה מזערי של {p.F_MV} בזרם הזינוק (נדרש > {p.t_inrush:g} s)",
            t_melt,
            "s",
            f"I = k·In_MV = {p.k_inrush:g}·{In_mv:.1f} = {i_inrush:.0f} A",
            "analytic",
            undefined_reason=why,
        )
    )
    if not inrush_ok:
        warnings.append(
            {
                "code": "inrush_blows_fuse",
                "message": f"{p.F_MV} עלול להישרף בחיבור השנאי: זרם זינוק {i_inrush:.0f} A "
                f"מתיך אותו אחרי {t_melt:.3g} s, פחות מ-{p.t_inrush:g} s",
            }
        )

    # 2. MV back-up of B1
    rows_backup = []
    for label, i_lv, factor in (
        ("קצר תלת-פאזי ב-B1 (מרבי)", pmax.Ik3["B1"] * 1e3, ratio),
        ("קצר תלת-פאזי ב-B1 (מזערי)", pmin.Ik3["B1"] * 1e3, ratio),
        ("קצר פאזה-אדמה ב-B1 (מזערי)", pmin.Ik1["B1"] * 1e3, ratio / math.sqrt(3)),
    ):
        i_mv = i_lv * factor
        tt, why = mv_tot.time(i_mv)
        rows_backup.append({"fault": label, "I_lv": i_lv, "I_mv": i_mv, "t": tt, "note": why or ""})
        if tt is None and i_mv < mv_tot.i_lo:
            warnings.append(
                {
                    "code": "no_mv_backup",
                    "message": f"{label}: {p.F_MV} רואה רק {i_mv:.0f} A ואינו מגבה את הלוח הראשי "
                    "(בשנאי Dyn תקלה לאדמה במ״נ מגיעה למ״ג מוקטנת פי √3 נוסף)",
                }
            )
    # 3. selectivity, scanning every current up to the maximum fault below the downstream device
    pairs = (
        (
            "LV ← MV",
            lv_name,
            p.F_MV,
            lv_main,
            _fuse_timer(mv_min, ratio),
            pmax.Ik3["B1"] * 1e3,
        ),
        ("Q1 ← LV", "Q1", lv_name, q1, lv_main, pmax.Ik3["B2"] * 1e3),
    )
    rows_sel = []
    for key, down_n, up_n, down, up, i_max in pairs:
        need = 0.0 if p.lv_main == "fuse" else case.cti  # fuse/breaker pairs: any margin > 0
        worst: tuple[float, float] | None = None  # (margin, current)
        first_fail: float | None = None
        start = 1.05 * (q1_in if key.startswith("Q1") else spec.I_n_lv)
        for i in log_grid(start, i_max, 400):
            td, _ = down(i)
            tu, _ = up(i)
            if td is None or tu is None:
                continue  # one of them does not act at this current, or is off its catalogue
            margin = tu - td
            if worst is None or margin < worst[0]:
                worst = (margin, i)
            if margin <= need and first_fail is None:
                first_fail = i
        ok = first_fail is None
        rows_sel.append(
            {
                "pair": f"{down_n} ← {up_n}",
                "I_max": i_max,
                "need": need,
                "margin": None if worst is None else worst[0],
                "at": None if worst is None else worst[1],
                "I_fail": first_fail,
                "verdict": "סלקטיבי" if ok else "לא סלקטיבי",
            }
        )
        if not ok:
            warnings.append(
                {
                    "code": "not_selective",
                    "message": f"{down_n} ← {up_n}: מ-{first_fail:.0f} A המרווח קטן מ-{need:g} s",
                }
            )

    # time–current curves, all on the LV current axis
    grid = log_grid(0.95 * p.k_t * q1_in, 2 * pmax.Ik3["B1"] * 1e3, 260)
    tcc = []
    for i in grid:
        r: dict[str, Any] = {"I": i}
        for k, timer in (
            ("q1", q1),
            ("lv", lv_main),
            ("mv_min", _fuse_timer(mv_min, ratio)),
            ("mv_tot", _fuse_timer(mv_tot, ratio)),
        ):
            tt, _ = timer(i)
            r[k] = tt if tt is not None and 1e-3 <= tt <= 1e4 else None
        tcc.append(r)
    params.append(
        Param("In_mv", "זרם נקוב של השנאי בצד מ״ג", In_mv, "A", "S_n/(√3·U1)", "analytic")
    )
    return Outcome(
        status="success_with_warnings" if len(warnings) > 1 else "success",
        warnings=warnings,
        result={
            "tables": [
                {
                    "id": "selectivity",
                    "title_he": "סלקטיביות (סריקה עד זרם הקצר המרבי מתחת להתקן התחתון)",
                    "columns": [
                        col("pair", "תחתון ← עליון", ""),
                        col("I_max", "קצר מרבי", "A"),
                        col("need", "מרווח נדרש", "s"),
                        col("margin", "מרווח מזערי", "s"),
                        col("at", "בזרם", "A"),
                        col("I_fail", "כשל מ-", "A"),
                        col("verdict", "תוצאה", ""),
                    ],
                    "rows": rows_sel,
                },
                {
                    "id": "backup",
                    "title_he": f"גיבוי: {p.F_MV} מנתק קצר בלוח הראשי",
                    "columns": [
                        col("fault", "תקלה", ""),
                        col("I_lv", "זרם במ״נ", "A"),
                        col("I_mv", "זרם בנתיך מ״ג", "A"),
                        col("t", "זמן ניתוק כולל", "s"),
                        col("note", "הערה", ""),
                    ],
                    "rows": rows_backup,
                },
                {
                    "id": "tcc",
                    "title_he": "אופייני זמן–זרם (כולם על ציר הזרם במ״נ)",
                    "columns": [
                        col("I", "I (מ״נ)", "A"),
                        col("q1", "Q1", "s"),
                        col("lv", "ראשי מ״נ", "s"),
                        col("mv_min", "מ״ג התכה", "s"),
                        col("mv_tot", "מ״ג ניתוק", "s"),
                    ],
                    "rows": tcc,
                },
            ],
            "parameters": [x.to_json() for x in params],
            "curves": [
                {
                    "id": "tcc",
                    "title_he": f"תיאום הגנות: Q1, {lv_name}, {p.F_MV}",
                    "x": "I",
                    "y": "q1",
                    "y2": "lv",
                    "y3": "mv_min",
                    "y_more": ["mv_tot"],
                    "table": "tcc",
                    "log": True,
                    "y_label": "זמן [s]",
                }
            ],
        },
    )
