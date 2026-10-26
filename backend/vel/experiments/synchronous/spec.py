"""Equipment specification for experiment 3: three-phase synchronous machine.

Model (steady state, cylindrical rotor, MMF method with saturation — "ASA/Potier" form):

* Open-circuit characteristic per winding at rated speed, as a function of the resultant MMF
  expressed in field amperes:  E(F) = a·F / (1 + (|F|/I_s)^m)^(1/m).
  Remanence is an MMF offset on the field axis: F_field = I_f + F_res, so reversing I_f first
  weakens the residual voltage, as in the lab.
* Air-gap EMF E_r = (n/n_n)·E(|F_r|) at 90° behind F_r, with F_r = F_field·e^{jθ} + k_a·I₁
  (I₁ = positive-sequence armature current, generator convention). Unsaturated this is
  E_r = E_f − j·(a·k_a)·I₁, i.e. X_s = X_l + a·k_a.
* Behind E_r: the winding impedance matrix built from the sequence impedances
  Z₁ = R_a + jX_l, Z₂ = R_a + jX₂, Z₀ = R_a + jX₀ (per winding), so unbalanced faults
  (line–line, line–neutral) are represented with their own sequence impedances.

All impedances are PER WINDING (between U1–U2 etc.) at rated frequency.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vel.experiments.thermal import Thermal

Provenance = Literal["assumed", "nameplate", "measured", "fitted"]


class SyncNameplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    P_n: float = Field(gt=0, le=1e7, description="rated power [W]")
    U_n: float = Field(gt=0, le=1e5, description="rated line voltage [V]")
    I_n: float = Field(gt=0, le=1e4, description="rated line current [A]")
    f_n: float = Field(gt=0, le=1000)
    poles: Literal[2, 4, 6, 8, 10, 12] = 4
    connection: Literal["Y", "D"] = "Y"
    cos_phi_n: float | None = Field(default=None, gt=0, le=1)
    If_n: float = Field(gt=0, le=1000, description="rated field current [A]")

    @property
    def n_sync(self) -> float:
        return 120 * self.f_n / self.poles


class SyncECM(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Ra: float = Field(ge=0, le=1e5, description="armature winding resistance [Ω]")
    Xl: float = Field(gt=0, le=1e5, description="leakage (Potier) reactance [Ω]")
    k_a: float = Field(ge=0, le=1e4, description="armature reaction [field A per armature A]")
    X2: float = Field(gt=0, le=1e5, description="negative-sequence reactance [Ω]")
    X0: float = Field(gt=0, le=1e5, description="zero-sequence reactance [Ω]")
    R_f: float = Field(gt=0, le=1e5, description="field winding resistance [Ω]")
    P_fw: float = Field(ge=0, le=1e6, description="friction + windage at synchronous speed [W]")


class OpenCircuitCurve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: float = Field(gt=0, le=1e6, description="air-gap line slope [V per field A, per winding]")
    I_s: float = Field(gt=0, le=1e4, description="saturation knee [field A]")
    m: float = Field(ge=1, le=50, description="knee sharpness")
    F_res: float = Field(ge=0, le=100, description="remanence as field-current offset [A]")
    F_h: float = Field(
        default=0.0,
        ge=0,
        le=10,
        description="hysteresis: largest MMF shift of the descending branch [field A]",
    )

    def emf(self, f_field: float) -> float:
        """Per-winding EMF magnitude at rated speed for a resultant MMF of |f_field| field A."""
        x = abs(f_field)
        return float(self.a * x / (1 + (x / self.I_s) ** self.m) ** (1 / self.m))

    def descending_shift(self, i_f: float, i_f_max: float) -> float:
        """MMF shift of the descending branch at i_f, coming down from i_f_max: zero at both
        ends (it starts at the turning point and returns to the remanence) and largest half
        way — δ = 4·F_h·x·(1 − x), x = i_f / i_f_max. A one-parameter shape, fitted to the
        2025 DC-machine table; it is not a magnetic hysteresis model (no minor loops)."""
        if self.F_h <= 0 or i_f_max <= 0:
            return 0.0
        x = min(max(i_f / i_f_max, 0.0), 1.0)
        return 4 * self.F_h * x * (1 - x)

    def d_emf(self, f_field: float) -> float:
        x = abs(f_field)
        u = 1 + (x / self.I_s) ** self.m
        return float(self.a * u ** (-1 / self.m - 1))


class SyncInsulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_frame_Mohm: float = Field(gt=0, le=1e6)
    V_frame_Mohm: float = Field(gt=0, le=1e6)
    W_frame_Mohm: float = Field(gt=0, le=1e6)
    F_frame_Mohm: float = Field(gt=0, le=1e6)
    stator_rotor_Mohm: float = Field(gt=0, le=1e6)


class SyncSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    provenance: Provenance
    provenance_note: str = Field(default="", max_length=2000)
    nameplate: SyncNameplate
    ecm: SyncECM
    thermal: Thermal = Field(default_factory=Thermal)
    occ: OpenCircuitCurve
    insulation: SyncInsulation

    @property
    def U_winding(self) -> float:
        n = self.nameplate
        return n.U_n if n.connection == "D" else n.U_n / math.sqrt(3)

    @property
    def I_winding(self) -> float:
        n = self.nameplate
        return n.I_n / math.sqrt(3) if n.connection == "D" else n.I_n

    @property
    def Xs_unsat(self) -> float:
        return self.ecm.Xl + self.occ.a * self.ecm.k_a

    @property
    def Z_base(self) -> float:
        return self.U_winding / self.I_winding

    def line_factor(self) -> float:
        """Line voltage / winding voltage for the nameplate connection."""
        return math.sqrt(3) if self.nameplate.connection == "Y" else 1.0


def fitted_lab_machine() -> SyncSpec:
    """Fitted to the student's own 2026 measurements (experiment 3 report draft) and the
    nameplate photograph. UNVERIFIED assumptions, stated:

    * Nameplate (photo): Y/Δ 400/230 V, 0.83/1.44 A, 0.27 kW, 1360/1500 rpm, cos φ 0.7/1.0,
      rotor ~107 V/1.7 A, =20 V/4.0 A → slip-ring machine, run here as synchronous (1500 rpm,
      DC field 4 A rated). Connection assumed Y and the U1 voltmeter LINE-TO-LINE (the only
      reading under which the short-circuit data give a plausible X_s ≈ 2.4 pu).
    * OCC (table 6.3, ascending, 11 points) fitted with rms error 0.45 V per winding:
      a = 156.36 V/A, I_s = 1.510 A, m = 2.524, F_res = 0.0201 A.
    * DC resistances (table 6.2): stator 33.3 Ω per winding (8/16/20 V points), field
      ≈ 6.4 Ω (the 8 V point, 7.5 Ω, is inconsistent with the other two and not used).
    * Short circuit (table 6.4) against the air-gap line E = a·(I_f + F_res): |Z₁| = 675 Ω
      (±2 %) from Ik(3) at I_f = 0.4–0.8 A (the 1.0 and 1.3 A readings give 390/355 Ω — not
      linear, not used); |Z₁+Z₂| = 827 Ω (±1.2 %) from all Ik(2) points; |Z₁+Z₂+Z₀| = 967 Ω
      (±1.1 %) from all Ik(1) points. → X_s = 674 Ω (2.4 pu), X₂ = 151 Ω, X₀ = 137 Ω.
    * X_l (Potier) is NOT measured (the zero-power-factor table is still empty): 0.12 pu
      assumed. k_a = (X_s − X_l)/a. Friction/windage assumed.
    """
    a = 156.36
    xs = 674.0
    xl = 33.0
    return SyncSpec(
        provenance="fitted",
        provenance_note=(
            "הותאם למדידות הסטודנט (ניסוי 3, 2026) ולשלט: עקומת ריקם (11 נק׳), התנגדויות DC, "
            "קצר תלת/דו/חד-פזי. הנחות: חיבור Y ומד המתח U1 קווי; X_l משוער (אין עדיין "
            "אופיין הגבי); שתי קריאות Ik(3) ב-If=1.0/1.3 A אינן עקביות ולא שימשו"
        ),
        nameplate=SyncNameplate(
            P_n=270, U_n=400, I_n=0.83, f_n=50, poles=4, connection="Y", cos_phi_n=1.0, If_n=4.0
        ),
        ecm=SyncECM(
            Ra=33.3, Xl=xl, k_a=round((xs - xl) / a, 4), X2=151.0, X0=137.0, R_f=6.4, P_fw=15.0
        ),
        occ=OpenCircuitCurve(a=a, I_s=1.510, m=2.524, F_res=0.0201),
        insulation=SyncInsulation(
            U_frame_Mohm=1000,
            V_frame_Mohm=1000,
            W_frame_Mohm=1000,
            F_frame_Mohm=831,
            stator_rotor_Mohm=1000,
        ),
    )


REPORT_2025_SCALE = 0.5375


def report_2025_machine() -> SyncSpec:
    """The 2026 fit with every reactance (X_l, k_a, X2, X0) × 0.5375, fitted to the 2025 report's
    short-circuit table (scripts/fit_synchronous_2025.py, docs/lab-data-2025-exp3.md).

    The 2025 OCC agrees with the 2026 fit without any change (independent check); all 16 of
    the 2025 fault currents are ≈ 1.85× the 2026 model's with the same Ik(2)/Ik(3) and
    Ik(1)/Ik(3) ratios, so one factor fits them all within 0.05 A. Xs = 362 Ω — which is what
    the two 2026 Ik(3) points flagged as outliers (If = 1.0, 1.3 A) also give. It conflicts with
    the plate's 4 A rated field current, which supports Xs ≈ 674 Ω."""
    base = fitted_lab_machine()
    e, lam = base.ecm, REPORT_2025_SCALE
    return base.model_copy(
        update={
            "provenance_note": (
                "כמו ההתאמה ל-2026, עם כל ההיגבים × 0.5375 לפי טבלת הקצרים של דוח 2025 "
                "(Xs = 362 Ω). אופיין הריקם של 2025 תואם ללא שינוי; סותר את זרם העירור שבשלט"
            ),
            "ecm": e.model_copy(
                update={
                    "Xl": e.Xl * lam,
                    "k_a": e.k_a * lam,
                    "X2": e.X2 * lam,
                    "X0": e.X0 * lam,
                }
            ),
        }
    )


PRESETS = {
    "lab_2026": (
        "מותאם למדידות שלך (ניסוי 3, 2026) ולשלט 400 V / 0.27 kW (לא מאומת)",
        fitted_lab_machine,
    ),
    "report_2025": (
        "כמו 2026, היגבים לפי קצרי דוח 2025 (Xs = 362 Ω) — סותר את עירור השלט",
        report_2025_machine,
    ),
}
