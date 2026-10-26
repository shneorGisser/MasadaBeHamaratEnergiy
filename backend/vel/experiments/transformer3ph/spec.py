"""Three-phase transformer specification (nameplate + per-winding equivalent circuit).

Model (per limb / per phase winding, T-equivalent, steady state at f):

    A1 ──R1──jX1──┬──────────┐        ┌──jX2──R2── a1
                  │          │  n1:n2 │
                R_Fe    jX_m(E1)   ideal
                  │          │        │
    A2 ───────────┴──────────┘        └─────────── a2

* Each limb is modelled as an independent single-phase transformer (a "bank" model).
  Magnetic coupling between limbs of a three-limb core is NOT modelled, so the
  middle-limb magnetizing-current asymmetry and zero-sequence flux paths are out of scope.
* X_m depends on the RMS winding EMF |E1| to represent saturation of the magnetization
  curve U = f(I0):   X_m(E) = X_m,unsat / (1 + c · (|E| / E_ref)^n)
  The magnetizing current is the *fundamental-equivalent* RMS value; harmonics of the real
  (distorted) magnetizing current are not represented.
* All impedances are in ohms of the physical winding they belong to (R2, X2 on the
  secondary winding), not referred values.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vel.experiments.thermal import Thermal

Connection = Literal["Y", "D"]
Provenance = Literal["assumed", "nameplate", "measured", "fitted"]


class Nameplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    S_n: float = Field(gt=0, le=1e7, description="Rated apparent power [VA]")
    U1n: float = Field(gt=0, le=1e5, description="Rated primary line voltage [V]")
    U2n: float = Field(gt=0, le=1e5, description="Rated secondary line voltage [V]")
    f_n: float = Field(gt=0, le=1000, description="Rated frequency [Hz]")
    primary: Connection = "Y"
    secondary: Connection = "Y"


class EquivalentCircuit(BaseModel):
    """Per-winding parameters [ohm]."""

    model_config = ConfigDict(extra="forbid")

    R1: float = Field(ge=0, le=1e6)
    X1: float = Field(ge=0, le=1e6)
    R2: float = Field(ge=0, le=1e6)
    X2: float = Field(ge=0, le=1e6)
    R_fe: float = Field(gt=0, le=1e9, description="Core-loss resistance, primary winding [ohm]")
    Xm_unsat: float = Field(gt=0, le=1e9, description="Unsaturated magnetizing reactance [ohm]")
    sat_c: float = Field(ge=0, le=1e3, description="Saturation strength c (0 = linear core)")
    sat_n: float = Field(ge=2, le=40, description="Saturation exponent n")


class Insulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_core_Mohm: float = Field(gt=0)
    secondary_core_Mohm: float = Field(gt=0)
    primary_secondary_Mohm: float = Field(gt=0)


class TransformerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    provenance: Provenance = "assumed"
    provenance_note: str = ""
    nameplate: Nameplate
    ecm: EquivalentCircuit
    thermal: Thermal = Field(default_factory=Thermal)
    insulation: Insulation

    # ---- derived quantities (pure functions of the spec) ----
    @property
    def U1_winding(self) -> float:
        n = self.nameplate
        return n.U1n / math.sqrt(3) if n.primary == "Y" else n.U1n

    @property
    def U2_winding(self) -> float:
        n = self.nameplate
        return n.U2n / math.sqrt(3) if n.secondary == "Y" else n.U2n

    @property
    def turns_ratio(self) -> float:
        """n1/n2 = rated winding-voltage ratio (no-load, ideal)."""
        return self.U1_winding / self.U2_winding

    @property
    def I1n_line(self) -> float:
        return self.nameplate.S_n / (math.sqrt(3) * self.nameplate.U1n)

    @property
    def I2n_line(self) -> float:
        return self.nameplate.S_n / (math.sqrt(3) * self.nameplate.U2n)

    @model_validator(mode="after")
    def _sanity(self) -> TransformerSpec:
        # Magnetizing branch must be much larger than series impedance, otherwise the T-model
        # parameters are physically implausible for a power transformer.
        z_series = math.hypot(self.ecm.R1, self.ecm.X1)
        xm_rated = self.ecm.Xm_unsat / (1 + self.ecm.sat_c)
        if z_series > 0 and xm_rated < 5 * z_series:
            raise ValueError(
                "Magnetizing reactance at rated voltage is less than 5× the primary series "
                "impedance; parameters are not plausible for a power transformer."
            )
        return self


def assumed_lab_transformer() -> TransformerSpec:
    """Placeholder parameter set until the real nameplate is available.

    Basis (all ASSUMED, typical of a small laboratory transformer):
      3 kVA, 380/220 V, Yy, 50 Hz, u_k = 5 %, P_k = 90 W, P_0 = 60 W, I_0 = 8 % of I_n.
    Derivation (per winding, primary Y: E_w = 219.4 V, base Z = 48.1 Ω):
      Z_k = 2.41 Ω, r_k = P_k/(3 I_1n²) = 1.44 Ω  → R1 = R2' = 0.72 Ω, X1 = X2' ≈ 0.97 Ω
      R2 = R2'/a², X2 = X2'/a² with a = 1.727
      R_Fe = E_w² / (P_0/3) ≈ 2400 Ω,  X_m(rated) ≈ 620 Ω → X_m,unsat = 1240 Ω with c = 1
    Note that cos φ_k = 0.60 > 0.577, so the lab manual's literal short-circuit formulas
    give an imaginary x_k for this transformer (see planning doc, section B).
    """
    return TransformerSpec(
        provenance="assumed",
        provenance_note=(
            "ערכים מוערכים לשנאי מעבדה טיפוסי 3 kVA, 380/220 V, Yy, עד לקבלת נתוני השלט"
        ),
        nameplate=Nameplate(S_n=3000, U1n=380, U2n=220, f_n=50, primary="Y", secondary="Y"),
        ecm=EquivalentCircuit(
            R1=0.72, X1=0.97, R2=0.24, X2=0.32, R_fe=2400, Xm_unsat=1240, sat_c=1.0, sat_n=8
        ),
        insulation=Insulation(
            primary_core_Mohm=500, secondary_core_Mohm=500, primary_secondary_Mohm=800
        ),
    )


def fitted_from_2025_report() -> TransformerSpec:
    """Parameters fitted to data transcribed from a previous year's student report (same course,
    same lab). The data is UNVERIFIED — use with caution.

    Source values (handwritten in the report):
      Nameplate: V_n = 220/110 V, I_n = 0.35/0.7 A, P_max = 500 VA.
        → per-winding 220 V / 110 V, ratio 2. 3·220·0.35 = 231 VA, which conflicts with the
          500 VA written on the nameplate line; S_n = 231 VA is used (consistent with I_n).
      Short circuit, last row (rated current): U_k = 21 V, I1k = 0.35 A, I2k = 0.7 A,
        P = 3.3 W, cos φ = 0.44. cos φ = P/(U·I) only holds if U_k is the PHASE voltage and P is
        the single-wattmeter reading → per phase: Z_k = 60.0 Ω, r_k = 26.94 Ω, x_k = 53.61 Ω
        (referred to the 220 V winding), split equally: R1 = 13.47, X1 = 26.81,
        R2 = 13.47/4 = 3.367, X2 = 26.81/4 = 6.70 Ω.
      Magnetizing branch: no no-load table was filled in. The capacitive-load rows with no recorded
        I2 (I1 ≈ 31.5 mA, P ≈ 1.7 W per phase, U1ph = 220 V) are used as an APPROXIMATE no-load
        point: R_Fe = 220²/1.7 ≈ 28.5 kΩ, X_m ≈ 7.20 kΩ at rated voltage. Saturation shape
        (c = 1, n = 8) is assumed, not measured.
      Insulation: every cell reads 999 MΩ — the megger's display limit, not a measured value.
    """
    s3 = math.sqrt(3)
    return TransformerSpec(
        provenance="fitted",
        provenance_note=(
            "הותאם לנתונים מדו״ח של סטודנט משנה קודמת (לא מאומת): 220/110 V, 0.35/0.7 A; "
            "ענף טורי מניסוי הקצר; ענף מגנוט משוער משורות העומס הקיבולי; צורת הרוויה מוערכת"
        ),
        nameplate=Nameplate(
            S_n=3 * 220 * 0.35, U1n=220 * s3, U2n=110 * s3, f_n=50, primary="Y", secondary="Y"
        ),
        ecm=EquivalentCircuit(
            R1=13.47, X1=26.81, R2=3.367, X2=6.70, R_fe=28470, Xm_unsat=14400, sat_c=1.0, sat_n=8
        ),
        insulation=Insulation(
            primary_core_Mohm=999, secondary_core_Mohm=999, primary_secondary_Mohm=999
        ),
    )


PRESETS = {
    "assumed_3kva": ("ערכים מוערכים: שנאי 3 kVA, 380/220 V (ללא מקור)", assumed_lab_transformer),
    "report_2025": (
        "מותאם לדו״ח סטודנט משנה קודמת: 220/110 V לליפוף, 231 VA (לא מאומת)",
        fitted_from_2025_report,
    ),
}
