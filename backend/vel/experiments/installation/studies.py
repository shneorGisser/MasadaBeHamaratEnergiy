"""Study definitions of experiment 8 (testing an electrical installation). None of them has a
circuit to edit: the tester's readings follow from closed-form models (vel.engine.installation), and each
study states the acceptance criterion it applies and where that criterion comes from."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vel.engine import installation as ph
from vel.experiments.common import Outcome, Param, StudyDef, col
from vel.experiments.installation.spec import K_INST, K_INST_LOW, InstallSpec

MODEL_VERSION = "install-1.0"

# trip-time limits (IEC 61008-1 / 61009-1) [s]: general type at IΔn and at 5·IΔn; type S at IΔn
RCD_T1_GENERAL = 0.300
RCD_T5_GENERAL = 0.040
RCD_T1_S = (0.130, 0.500)

SRC_REG22 = "תקנות החשמל (הארקות ואמצעי הגנה בפני חשמול), תקנה 22 — ניתוק תוך 5 s"
SRC_60898 = "IEC 60898-1: שחרור מגנטי < 0.1 s ב-5/10/20·In (B/C/D); 1–60 s ב-2.55·In מקור"
SRC_61008 = "IEC 61008-1: לא מנתק ב-½IΔn; ≤ 300 ms ב-IΔn; ≤ 40 ms ב-5·IΔn (סוג S: 130–500 ms)"
SRC_TT = "IEC 60364-4-41 (411.5.3): R_A·IΔn ≤ 50 V במערכת TT"
SRC_INS = "IEC 60364-6: ≥ 1 MΩ במתח בדיקה 500 V למעגלים עד 500 V (ערך הספק במפרט)"
# the manual accepts a spread of "10–15 %" in 0.4–0.6·r13; the stricter end is applied
PLATEAU_MAX = 0.10
SRC_PE = "חוברת הניסוי: התנגדות מוליך מאריק מותרת ≈ 0.05 Ω"


def _status(w: list[dict[str, Any]]) -> Literal["success", "success_with_warnings"]:
    return "success_with_warnings" if w else "success"


def _ok(v: bool) -> str:
    return "עומד" if v else "לא עומד"


def _result(
    tables: list[dict[str, Any]],
    params: list[Param],
    curves: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> Outcome:
    return Outcome(
        status=_status(warnings),
        warnings=warnings,
        result={"tables": tables, "parameters": [p.to_json() for p in params], "curves": curves},
    )


# --------------------------------------------------------------------------- cases


class NoCase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class McbPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    In: float = Field(gt=0, le=1000)
    I: float = Field(gt=0, le=1e5)  # noqa: E741 — the column key of the measurement table


class McbCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[McbPoint] = Field(min_length=1, max_length=40)
    theta0: float = Field(default=0.0, ge=0, le=4, description="initial bimetal state [In²]")


class RcdCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    multiples: list[float] = Field(min_length=1, max_length=12)

    @field_validator("multiples")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x > 20 for x in v):
            raise ValueError("multiples must be within (0, 20]")
        return v


class InsulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_test: float = Field(default=500.0, gt=0, le=5000)
    t_read: float = Field(default=60.0, gt=0, le=3600, description="reading time [s]")
    guard: bool = False


class EarthCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    r13: float = Field(gt=0, le=1000, description="current electrode distance [m]")
    fractions: list[float] = Field(min_length=2, max_length=20)

    @field_validator("fractions")
    @classmethod
    def _v(cls, v: list[float]) -> list[float]:
        if any((not math.isfinite(x)) or x <= 0 or x >= 1 for x in v):
            raise ValueError("fractions of r13 must be within (0, 1)")
        return v


class ContinuityCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_test: float = Field(default=10.0, gt=0, le=100)
    R_extra: float = Field(default=0.0, ge=0, le=100, description="loose terminal [Ω]")


# --------------------------------------------------------------------------- 1. grid voltages


def run_grid_voltages(spec: InstallSpec, case: NoCase) -> Outcome:
    v = ph.voltages(spec)
    rows = [{"pair": k, "U": v[k]} for k in (*ph.LN_PAIRS, *ph.LL_PAIRS)]
    ln = [v[k] for k in ph.LN_PAIRS]
    avg = sum(ln) / 3
    unb = max(abs(x - avg) for x in ln) / avg
    u0 = spec.network.U0
    w: list[dict[str, Any]] = []
    for k in ph.LN_PAIRS:
        if abs(v[k] / u0 - 1) > 0.10:
            w.append(
                {
                    "code": "voltage_out_of_band",
                    "message": f"{k} = {v[k]:.1f} V מחוץ ל-{u0:g} V ±10 %",
                }
            )
    params = [
        Param("unbalance", "חוסר סימטריה (סטייה מרבית מהממוצע)", unb, "", "max|U−Ū|/Ū", "analytic"),
        Param(
            "ratio_LL_LN",
            "יחס U_קו / U_פאזה (ממוצע)",
            sum(v[k] for k in ph.LL_PAIRS) / 3 / avg,
            "",
            "√3 ברשת סימטרית",
            "analytic",
        ),
    ]
    tables = [
        {
            "id": "readings",
            "title_he": "מתחי רשת המעבדה",
            "columns": [col("pair", "בין", ""), col("U", "U", "V")],
            "rows": rows,
        }
    ]
    return _result(tables, params, [], w)


# --------------------------------------------------------------------------- 2. fault loop


def run_fault_loop(spec: InstallSpec, case: NoCase) -> Outcome:
    n = spec.network
    rows = []
    for loop in ph.LOOPS:
        z = ph.loop_impedance(spec, loop)
        zm = ph.z_max(spec, loop)
        ipf = ph.loop_voltage(spec, loop) / z
        rows.append(
            {
                "loop": loop,
                "Z": z,
                "I_pf": ipf,
                "Z_max": zm,
                "verdict": _ok(z <= zm),
            }
        )
    k5 = ph.mcb_current_for_time(spec.mcb, n.t_disc)
    params = [
        Param(
            "Z_max",
            f"Z מרבי ל-{n.curve_prot}{n.In_prot:g} (L-N, L-PE)",
            spec.Z_max,
            "Ω",
            f"U0/({K_INST[n.curve_prot]:g}·In)",
            "analytic",
            note=SRC_REG22,
        ),
        Param(
            "I_5s_thermal",
            f"זרם לניתוק תרמי ב-{n.t_disc:g} s לפי מודל המא״ז",
            k5 * n.In_prot,
            "A",
            "In·k_t/√(1−e^(−t/τ))",
            "analytic",
            note="מידע בלבד: הקריטריון בחוברת משתמש בזרם השחרור המגנטי",
        ),
    ]
    w = [
        {
            "code": "loop_too_high",
            "message": f"לולאה {r['loop']}: Z = {r['Z']:.3g} Ω > "
            f"{r['Z_max']:.3g} Ω — ההגנה לא תנתק תוך {n.t_disc:g} s",
        }
        for r in rows
        if float(r["Z"]) > float(r["Z_max"])  # type: ignore[arg-type]
    ]
    tables = [
        {
            "id": "loops",
            "title_he": "עכבת לולאת התקלה וזרם הקצר הצפוי",
            "columns": [
                col("loop", "לולאה", ""),
                col("Z", "Z", "Ω"),
                col("I_pf", "I קצר צפוי", "A"),
                col("Z_max", "Z מרבי מותר", "Ω"),
                col("verdict", "תקנה 22", ""),
            ],
            "rows": rows,
        }
    ]
    return _result(tables, params, [], w)


# --------------------------------------------------------------------------- 3. MCB


MODE_HE = {"thermal": "תרמי", "magnetic": "מגנטי", "none": "לא מנתק"}


def _tc_rows(spec: InstallSpec) -> list[dict[str, Any]]:
    out = []
    lo, hi, steps = math.log(1.05 * spec.mcb.k_t), math.log(30.0), 60
    for i in range(steps + 1):
        k = math.exp(lo + (hi - lo) * i / steps)
        t, mode = ph.mcb_trip(spec.mcb, 1.0, k)
        out.append({"k": k, "t": t, "mode": MODE_HE[mode]})
    return out


def run_mcb(spec: InstallSpec, case: McbCase) -> Outcome:
    m = spec.mcb
    rows: list[dict[str, Any]] = []
    for p in case.points:
        t, mode = ph.mcb_trip(m, p.In, p.I, case.theta0)
        rows.append({"In": p.In, "I": p.I, "k": p.I / p.In, "t": t, "mode": MODE_HE[mode]})
    w: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        if r["mode"] == MODE_HE["none"]:
            w.append(
                {
                    "code": "no_trip",
                    "row": i,
                    "message": f"שורה {i + 1}: k = {r['k']:.2f} "
                    f"< k_t = {m.k_t:g} — המא״ז אינו מנתק",
                }
            )
    t255, _ = ph.mcb_trip(m, 1.0, 2.55)
    params = [
        Param(
            "t_255",
            "זמן ניתוק ב-2.55·In מקור",
            t255,
            "s",
            "τ·ln(k²/(k²−k_t²))",
            "analytic",
            note=SRC_60898,
        ),
        Param("k_m", "סף השחרור המגנטי", m.k_m, "×In", "מפרט", "manual"),
    ]
    if t255 is not None and not 1.0 < t255 < 60.0:
        w.append(
            {
                "code": "curve_outside_standard",
                "message": f"ב-2.55·In המודל נותן {t255:.3g} s — מחוץ לתחום 1–60 s של IEC 60898-1",
            }
        )
    if not K_INST_LOW[m.curve] <= m.k_m <= K_INST[m.curve]:
        w.append(
            {
                "code": "magnetic_outside_class",
                "message": f"k_m = {m.k_m:g} מחוץ לתחום "
                f"{K_INST_LOW[m.curve]:g}–{K_INST[m.curve]:g}·In של אופיין {m.curve}",
            }
        )
    cols = [
        col("In", "In", "A"),
        col("I", "I", "A"),
        col("k", "I/In", ""),
        col("t", "זמן ניתוק", "s"),
        col("mode", "מנגנון", ""),
    ]
    tables = [
        {
            "id": "trips",
            "title_he": "בדיקת מא״ז: זמן ניתוק בזרם קבוע",
            "columns": cols,
            "rows": rows,
        },
        {
            "id": "tc",
            "title_he": f"אופיין זמן–זרם (אופיין {m.curve}, מקור)",
            "columns": [col("k", "I/In", ""), col("t", "t", "s"), col("mode", "מנגנון", "")],
            "rows": _tc_rows(spec),
        },
    ]
    curves = [
        {"id": "t_k", "title_he": "זמן ניתוק כתלות ב-I/In", "x": "k", "y": "t", "log": True},
        {
            "id": "tc",
            "title_he": "אופיין זמן–זרם של המודל",
            "x": "k",
            "y": "t",
            "table": "tc",
            "log": True,
        },
    ]
    return _result(tables, params, curves, w)


# --------------------------------------------------------------------------- 4. RCD


def _rcd_limits(spec: InstallSpec, mult: float) -> tuple[str, bool | None]:
    """(criterion text, verdict) for one test multiple, or (text, None) when none applies."""
    r = spec.rcd
    t = ph.rcd_trip(r, mult * r.I_dn)
    s_type = r.t_delay > 0
    if abs(mult - 0.5) < 1e-9:
        return "לא מנתק", t is None
    if abs(mult - 1.0) < 1e-9:
        if s_type:
            lo, hi = RCD_T1_S
            return f"{lo * 1000:g}–{hi * 1000:g} ms", t is not None and lo <= t <= hi
        return f"≤ {RCD_T1_GENERAL * 1000:g} ms", t is not None and t <= RCD_T1_GENERAL
    if abs(mult - 5.0) < 1e-9 and not s_type:
        return f"≤ {RCD_T5_GENERAL * 1000:g} ms", t is not None and t <= RCD_T5_GENERAL
    return "—", None


def run_rcd(spec: InstallSpec, case: RcdCase) -> Outcome:
    r = spec.rcd
    rows = []
    for k in case.multiples:
        t = ph.rcd_trip(r, k * r.I_dn)
        crit, ok = _rcd_limits(spec, k)
        rows.append(
            {
                "mult": k,
                "I": k * r.I_dn * 1000,
                "t": t * 1000 if t is not None else None,
                "limit": crit,
                "verdict": "—" if ok is None else _ok(ok),
            }
        )
    u0, rg = spec.network.U0, spec.R_g
    # the manual's point: the toroid sees I_L + I_N only, so a person between L and N is invisible
    scen = [
        ("אדם בין פאזה להארקה (דרך הקרקע)", u0 / (r.R_body + rg), u0 / (r.R_body + rg)),
        ("אדם בין פאזה לאפס (מבודד מהקרקע)", u0 / r.R_body, 0.0),
        ("קצר פאזה–אפס (מנתק המא״ז, לא מפסק הפחת)", u0 / ph.loop_impedance(spec, "L1-N"), 0.0),
    ]
    rows2 = []
    for name, i_body, i_res in scen:
        t = ph.rcd_trip(r, i_res)
        rows2.append(
            {
                "scenario": name,
                "I_loop": i_body * 1000,
                "I_res": i_res * 1000,
                "trips": "מנתק" if t is not None else "לא מנתק",
                "t": t * 1000 if t is not None else None,
            }
        )
    w = [
        {"code": "rcd_fails", "row": i, "message": f"{x['mult']:g}·IΔn: {x['limit']} — לא מתקיים"}
        for i, x in enumerate(rows)
        if x["verdict"] == "לא עומד"
    ]
    params = [
        Param(
            "I_trip",
            "זרם הניתוק בפועל (בדיקת רמפה)",
            r.k_trip * r.I_dn * 1000,
            "mA",
            "k_trip·IΔn",
            "manual",
            note="חייב להיות בין ½IΔn ל-IΔn (IEC 61008-1)",
        ),
        Param("U_c", "מתח מגע ב-IΔn", r.I_dn * rg, "V", "IΔn·R_g", "analytic", note=SRC_TT),
    ]
    if not 0.5 <= r.k_trip <= 1.0:
        w.append(
            {
                "code": "trip_current_outside",
                "message": f"זרם הניתוק {r.k_trip:g}·IΔn מחוץ לתחום ½–1·IΔn",
            }
        )
    tables = [
        {
            "id": "trip_times",
            "title_he": f"מפסק מגן (פחת) IΔn = {r.I_dn * 1000:g} mA: זמני ניתוק",
            "columns": [
                col("mult", "כפולה של IΔn", ""),
                col("I", "זרם דלף", "mA"),
                col("t", "זמן ניתוק", "ms"),
                col("limit", "דרישה", ""),
                col("verdict", "תוצאה", ""),
            ],
            "rows": rows,
        },
        {
            "id": "principle",
            "title_he": "עקרון הטורואיד: מה המפסק רואה",
            "columns": [
                col("scenario", "מקרה", ""),
                col("I_loop", "זרם במסלול", "mA"),
                col("I_res", "זרם שיורי (I_L + I_N)", "mA"),
                col("trips", "המפסק", ""),
                col("t", "זמן", "ms"),
            ],
            "rows": rows2,
        },
    ]
    return _result(tables, params, [], w)


# --------------------------------------------------------------------------- 5. insulation

INS_PAIRS = (("R_pf", "ראשוני – ערכה"), ("R_sf", "משני – ערכה"), ("R_ps", "ראשוני – משני"))


def run_insulation(spec: InstallSpec, case: InsulationCase) -> Outcome:
    s = spec.insulation
    c, r_s, r_su = s.C_nF * 1e-9, s.R_s_kohm * 1e3, s.R_su * 1e6
    rows = []
    w: list[dict[str, Any]] = []
    for key, label in INS_PAIRS:
        r_app, u_t = ph.megger_reading(
            getattr(s, key) * 1e6, r_su, c, r_s, case.U_test, case.t_read, case.guard
        )
        shown = min(r_app / 1e6, s.display_max)
        if r_app / 1e6 > s.display_max:
            w.append(
                {
                    "code": "display_limit",
                    "message": f"{label}: {r_app / 1e6:.4g} MΩ מעל גבול "
                    f"התצוגה — המכשיר מראה {s.display_max:g}",
                }
            )
        # the manual's table has a column per phase; the model has one value per winding pair
        rows.append(
            {
                "pair": label,
                "ph1": shown,
                "ph2": shown,
                "ph3": shown,
                "R_min": s.R_min,
                "verdict": _ok(shown >= s.R_min),
            }
        )
    curve_rows = []
    lo, hi = math.log(1e-5), math.log(max(case.t_read, 1e-3))
    for i in range(41):
        t = math.exp(lo + (hi - lo) * i / 40)
        r0, _ = ph.megger_reading(s.R_pf * 1e6, r_su, c, r_s, case.U_test, t, False)
        r1, _ = ph.megger_reading(s.R_pf * 1e6, r_su, c, r_s, case.U_test, t, True)
        curve_rows.append({"t": t, "R_noguard": r0 / 1e6, "R_guard": r1 / 1e6})
    r_p = 1 / (1 / (s.R_pf * 1e6) + 1 / r_su)
    tau = c * r_s * r_p / (r_s + r_p)
    params = [
        Param(
            "tau",
            "קבוע הזמן של הטעינה",
            tau,
            "s",
            "C·(R_s ‖ R_p)",
            "analytic",
            note="בבידוד אחיד הזרם הקיבולי דועך תוך מילי-שניות (חוברת, איור 5.2)",
        ),
        Param("R_min", "ערך מינימלי מותר", s.R_min, "MΩ", "מפרט", "manual", note=SRC_INS),
    ]
    tables = [
        {
            "id": "readings",
            "title_he": f"התנגדות בידוד ({case.U_test:g} V, קריאה אחרי {case.t_read:g} s"
            + (", עם Guard)" if case.guard else ", ללא Guard)"),
            "columns": [
                col("pair", "ליפוף", ""),
                col("ph1", "פזה 1", "MΩ"),
                col("ph2", "פזה 2", "MΩ"),
                col("ph3", "פזה 3", "MΩ"),
                col("R_min", "מותרת", "MΩ"),
                col("verdict", "תוצאה", ""),
            ],
            "rows": rows,
        },
        {
            "id": "charging",
            "title_he": "קריאת המגר בזמן הטעינה (ראשוני – ערכה)",
            "columns": [
                col("t", "t", "s"),
                col("R_noguard", "ללא Guard", "MΩ"),
                col("R_guard", "עם Guard", "MΩ"),
            ],
            "rows": curve_rows,
        },
    ]
    curves = [
        {
            "id": "charging",
            "title_he": "R נראה = f(t)",
            "x": "t",
            "y": "R_noguard",
            "y2": "R_guard",
            "table": "charging",
            "log": True,
        }
    ]
    return _result(tables, params, curves, w)


# --------------------------------------------------------------------------- 6. earth resistance


def run_earth(spec: InstallSpec, case: EarthCase) -> Outcome:
    rows = [
        {"frac": f, "x": f * case.r13, "R": ph.fall_of_potential(spec, case.r13, f * case.r13)}
        for f in sorted(case.fractions)
    ]
    r62 = ph.fall_of_potential(spec, case.r13, 0.618 * case.r13)
    mid = [ph.fall_of_potential(spec, case.r13, f * case.r13) for f in (0.4, 0.5, 0.6)]
    spread = (max(mid) - min(mid)) / r62
    d = spec.earth.rod_L  # "diagonal" of a single-rod earth system: its length
    w: list[dict[str, Any]] = []
    if case.r13 < max(5 * d, 50.0):
        w.append(
            {
                "code": "electrode_too_close",
                "message": f"r1-3 = {case.r13:g} m קטן מ-"
                f"max(5D, 50 m) = {max(5 * d, 50.0):g} m שבחוברת",
            }
        )
    if spread > PLATEAU_MAX:
        w.append(
            {
                "code": "no_plateau",
                "message": f"בתחום 0.4–0.6·r1-3 הערכים שונים ב-"
                f"{spread:.0%} (> {PLATEAU_MAX:.0%}) — יש להרחיק את אלקטרודת הזרם או לחזור "
                "בכיוון אחר",
            }
        )
    u_c = spec.rcd.I_dn * r62
    params = [
        Param("R_062", "התנגדות ההארקה ב-0.62·r1-3", r62, "Ω", "U/I", "analytic"),
        Param(
            "R_g", "התנגדות האלקטרודה (מודל)", spec.R_g, "Ω", "ρ/(2πL)·(ln(8L/d) − 1)", "analytic"
        ),
        Param(
            "spread",
            "פיזור בתחום 0.4–0.6·r1-3",
            spread,
            "",
            "(max−min)/R(0.62)",
            "analytic",
            note="החוברת: עד 10–15 % (נבדק מול 10 %)",
        ),
        Param("U_touch", "מתח מגע ב-IΔn (TT)", u_c, "V", "IΔn·R_g", "analytic", note=SRC_TT),
    ]
    if u_c > spec.earth.U_touch_max:
        w.append(
            {
                "code": "touch_voltage",
                "message": f"IΔn·R_g = {u_c:.3g} V > {spec.earth.U_touch_max:g} V",
            }
        )
    tables = [
        {
            "id": "profile",
            "title_he": f"שיטת נפילת המתח: R כתלות במיקום אלקטרודת המתח (r1-3 = {case.r13:g} m)",
            "columns": [
                col("frac", "x / r1-3", ""),
                col("x", "r1-2", "m"),
                col("R", "R = U/I", "Ω"),
            ],
            "rows": rows,
        }
    ]
    curves = [{"id": "profile", "title_he": "R = f(r1-2)", "x": "x", "y": "R"}]
    return _result(tables, params, curves, w)


# --------------------------------------------------------------------------- 7. continuity


def run_continuity(spec: InstallSpec, case: ContinuityCase) -> Outcome:
    r = spec.R_pe + case.R_extra
    e = spec.earth
    rows = [
        {
            "U": case.I_test * r,
            "I": case.I_test,
            "R": r,
            "R_max": e.R_pe_max,
            "verdict": _ok(r <= e.R_pe_max),
        }
    ]
    w = (
        []
        if r <= e.R_pe_max
        else [
            {
                "code": "continuity_fails",
                "message": f"R = {r:.3g} Ω > {e.R_pe_max:g} Ω — חיבור רופף או מוליך ארוך/דק",
            }
        ]
    )
    params = [
        Param("R_pe", "התנגדות מוליך ההארקה", r, "Ω", "ρ_Cu·L/A + R_מגע", "analytic", note=SRC_PE)
    ]
    tables = [
        {
            "id": "continuity",
            "title_he": "רציפות מוליך ההארקה (אמפרמטר–וולטמטר)",
            "columns": [
                col("U", "U", "V"),
                col("I", "I", "A"),
                col("R", "R = U/I", "Ω"),
                col("R_max", "מותר", "Ω"),
                col("verdict", "תוצאה", ""),
            ],
            "rows": rows,
        }
    ]
    return _result(tables, params, [], w)


# --------------------------------------------------------------------------- registry

# 2025 report, "בדיקת מא״ז" (page 10): breaker rating, current, time to trip
MCB_2025 = [(1, 4.9), (1, 3.3), (3, 18.4), (3, 12.7), (3, 8.3), (6, 45), (6, 41), (6, 38), (6, 18)]

STUDIES: dict[str, StudyDef] = {
    s.kind: s
    for s in [
        StudyDef(
            "grid_voltages",
            "מתחי רשת המעבדה",
            "חוברת עמ׳ 5",
            NoCase,
            lambda spec: {},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "fault_loop",
            "עכבת לולאת התקלה",
            "חוברת עמ׳ 1–5, איור 3",
            NoCase,
            lambda spec: {},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "mcb_trip",
            "בדיקת מא״ז: אופיין זמן–זרם",
            "דוח 2025 עמ׳ 10; איור 3",
            McbCase,
            lambda spec: {"points": [{"In": a, "I": b} for a, b in MCB_2025], "theta0": 0.0},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "rcd",
            "מפסק מגן (פחת)",
            "חוברת עמ׳ 7–9",
            RcdCase,
            lambda spec: {"multiples": [0.5, 1.0, 2.0, 5.0]},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "insulation",
            "התנגדות בידוד (מגר)",
            "חוברת עמ׳ 9–10, איורים 5, 5.2",
            InsulationCase,
            lambda spec: {"U_test": 500.0, "t_read": 60.0, "guard": False},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "earth",
            "התנגדות הארקה (שיטת 62 %)",
            "חוברת עמ׳ 12–15, איורים 6.2–6.4",
            EarthCase,
            lambda spec: {"r13": 50.0, "fractions": [0.2, 0.3, 0.4, 0.5, 0.6, 0.62, 0.7, 0.8]},
            None,
            editable_circuit=False,
        ),
        StudyDef(
            "continuity",
            "רציפות מוליך ההארקה",
            "חוברת עמ׳ 16–17, איור 6.6",
            ContinuityCase,
            lambda spec: {"I_test": 10.0, "R_extra": 0.0},
            None,
            editable_circuit=False,
        ),
    ]
}

_RUN = {
    "grid_voltages": run_grid_voltages,
    "fault_loop": run_fault_loop,
    "mcb_trip": run_mcb,
    "rcd": run_rcd,
    "insulation": run_insulation,
    "earth": run_earth,
    "continuity": run_continuity,
}


def execute(kind: str, spec: InstallSpec, circuit_doc: Any, case_doc: dict[str, Any]) -> Outcome:
    sd = STUDIES.get(kind)
    if sd is None:
        return Outcome(status="unsupported", error={"message": f"unknown study {kind}"})
    try:
        case = sd.case_model.model_validate(case_doc or {})
    except Exception as exc:
        return Outcome(
            status="invalid_input", error={"message": "פרמטרי הניסוי שגויים", "details": str(exc)}
        )
    out: Outcome = _RUN[kind](spec, case)  # type: ignore[operator]
    return out
