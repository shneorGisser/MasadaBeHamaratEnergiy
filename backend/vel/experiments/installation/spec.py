"""Equipment specification for experiment 8: testing an electrical installation.

The "equipment" is the lab's supply and its protective devices, a test object for the megger
and an earth electrode. Every parameter below is either measured (2025 report), fitted to it,
taken from a standard, or assumed; the preset's provenance note says which. See
docs/model-installation.md.

* Supply: three phase voltages U1..U3 (120° apart), per-conductor loop resistances: phase Z_L,
  neutral Z_N, protective conductor Z_PE. Loops are series sums (L–N = Z_L + Z_N, …).
* Miniature circuit breaker (IEC 60898-1 curves B/C/D): thermal release as a first-order
  bimetal, θ' = (k² − θ)/τ with k = I/In, trip when θ reaches k_t² (from cold:
  t = τ·ln(k²/(k² − k_t²))); magnetic release at k ≥ k_m after t_mag.
* RCD: trips when the residual current |I_L + I_N| (the toroid sees only the difference)
  reaches k_trip·IΔn, after t0 + t1·(I_trip/I)² (+ t_delay for a type S device).
* Insulation of the test object: R_is (volume) ‖ R_su (surface) ‖ C, megger with internal
  resistance R_s and a display limit; the guard terminal bypasses the surface current.
* Earth electrode: one driven rod in uniform soil (Dwight); for the potential profile of the
  fall-of-potential method it is replaced by the hemisphere with the same resistance.
* Earthing (protective) conductor: ρ_Cu·L/A plus a contact resistance.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Provenance = Literal["assumed", "nameplate", "measured", "fitted"]
Curve = Literal["B", "C", "D"]

RHO_CU = 0.0178  # Ω·mm²/m at 20 °C
# IEC 60898-1: instantaneous release must operate below 0.1 s at this multiple of In
K_INST = {"B": 5.0, "C": 10.0, "D": 20.0}
# … and must not operate within 0.1 s at this multiple
K_INST_LOW = {"B": 3.0, "C": 5.0, "D": 10.0}


class Network(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U0: float = Field(gt=0, le=1000, description="nominal phase-to-neutral voltage [V]")
    U1: float = Field(gt=0, le=1000, description="phase L1 to neutral, actual [V]")
    U2: float = Field(gt=0, le=1000, description="phase L2 to neutral, actual [V]")
    U3: float = Field(gt=0, le=1000, description="phase L3 to neutral, actual [V]")
    Z_L: float = Field(gt=0, le=100, description="phase conductor + source, per phase [Ω]")
    Z_N: float = Field(gt=0, le=100, description="neutral conductor [Ω]")
    Z_PE: float = Field(gt=0, le=1000, description="protective conductor path [Ω]")
    In_prot: float = Field(gt=0, le=1000, description="rated current of the protecting MCB [A]")
    curve_prot: Curve = Field(description="curve of the protecting MCB")
    t_disc: float = Field(default=5.0, gt=0, le=60, description="required disconnection [s]")


class Mcb(BaseModel):
    """The breakers under test (one model for every rating: τ and k_t do not depend on In)."""

    model_config = ConfigDict(extra="forbid")
    curve: Curve
    tau: float = Field(gt=0, le=1e4, description="thermal time constant [s]")
    k_t: float = Field(
        gt=1.0, le=2.0, description="thermal trip threshold [× In], between 1.13 and 1.45"
    )
    k_m: float = Field(gt=1.0, le=50, description="magnetic release threshold [× In]")
    t_mag: float = Field(default=0.01, gt=0, le=0.1, description="magnetic release time [s]")


class Rcd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    I_dn: float = Field(gt=0, le=5, description="rated residual current IΔn [A]")
    k_trip: float = Field(gt=0, le=2, description="actual trip current [× IΔn]")
    t0: float = Field(ge=0, le=1, description="mechanism time [s]")
    t1: float = Field(ge=0, le=1, description="extra time at the trip threshold [s]")
    t_delay: float = Field(default=0.0, ge=0, le=1, description="type S delay [s]")
    R_body: float = Field(default=1000.0, gt=0, le=1e6, description="body resistance [Ω]")


class Insulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    R_pf: float = Field(gt=0, le=1e6, description="primary–frame, volume [MΩ]")
    R_sf: float = Field(gt=0, le=1e6, description="secondary–frame, volume [MΩ]")
    R_ps: float = Field(gt=0, le=1e6, description="primary–secondary, volume [MΩ]")
    R_su: float = Field(gt=0, le=1e7, description="surface path of each pair [MΩ]")
    C_nF: float = Field(ge=0, le=1e6, description="capacitance of each pair [nF]")
    R_s_kohm: float = Field(gt=0, le=1e5, description="megger internal resistance [kΩ]")
    display_max: float = Field(gt=0, le=1e6, description="megger display limit [MΩ]")
    R_min: float = Field(gt=0, le=1e4, description="lowest acceptable value [MΩ]")


class Earth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rho: float = Field(gt=0, le=1e5, description="soil resistivity [Ω·m]")
    rod_L: float = Field(gt=0, le=100, description="rod length [m]")
    rod_d: float = Field(gt=0, le=1, description="rod diameter [m]")
    U_touch_max: float = Field(default=50.0, gt=0, le=1000, description="touch voltage [V]")
    pe_L: float = Field(gt=0, le=1e4, description="earthing conductor length [m]")
    pe_A: float = Field(gt=0, le=1e4, description="earthing conductor cross-section [mm²]")
    R_contact: float = Field(ge=0, le=100, description="terminal contact resistance [Ω]")
    R_pe_max: float = Field(gt=0, le=100, description="acceptable continuity resistance [Ω]")


class InstallSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provenance: Provenance
    provenance_note: str = ""
    network: Network
    mcb: Mcb
    rcd: Rcd
    insulation: Insulation
    earth: Earth

    # ------------------------------------------------------------------ derived quantities

    @property
    def R_g(self) -> float:
        """Driven rod in uniform soil (Dwight): ρ/(2πL)·(ln(8L/d) − 1)."""
        e = self.earth
        return e.rho / (2 * math.pi * e.rod_L) * (math.log(8 * e.rod_L / e.rod_d) - 1)

    @property
    def R_pe(self) -> float:
        e = self.earth
        return RHO_CU * e.pe_L / e.pe_A + e.R_contact

    @property
    def Z_max(self) -> float:
        """Largest L–PE loop that still trips the protecting MCB instantaneously (the manual:
        Z = 230/(5·In) for a type B)."""
        n = self.network
        return n.U0 / (K_INST[n.curve_prot] * n.In_prot)


def lab_2025() -> InstallSpec:
    """The lab supply as measured in the 2025 report of experiment 8 (voltages, loops) and the
    breakers' thermal model fitted to its MCB test; everything without data is assumed."""
    return InstallSpec(
        provenance="fitted",
        provenance_note=(
            "מתחי הפאזות נמדדו (דוח 2025). Z_L ו-Z_PE הותאמו ללולאות L-PE ו-L1-L2 של הדוח; Z_N "
            "מוערך (= Z_L) כי קריאות L-N בדוח (0) אינן אפשריות פיזיקלית. τ של המא״זים הותאם "
            "לבדיקת המא״ז בדוח עם k_t = 1.3 מוערך; אופיין C מוסק (B נשלל). המפסק המגן "
            "(C16), מפסק המגן לזרם דלף, הבידוד, ההארקה ומוליך ההארקה — מוערכים, ללא נתונים"
        ),
        network=Network(
            U0=230,
            U1=234,
            U2=234,
            U3=235,
            Z_L=0.06,
            Z_N=0.06,
            Z_PE=0.10,
            In_prot=16,
            curve_prot="C",
        ),
        mcb=Mcb(curve="C", tau=48.7, k_t=1.3, k_m=10.0),
        rcd=Rcd(I_dn=0.03, k_trip=0.8, t0=0.012, t1=0.015),
        insulation=Insulation(
            R_pf=500,
            R_sf=500,
            R_ps=800,
            R_su=5000,
            C_nF=2.0,
            R_s_kohm=500,
            display_max=999,
            R_min=1.0,
        ),
        earth=Earth(
            rho=100,
            rod_L=1.5,
            rod_d=0.016,
            pe_L=5,
            pe_A=16,
            R_contact=0.01,
            R_pe_max=0.05,
        ),
    )


def assumed_nominal() -> InstallSpec:
    """A textbook installation: 230/400 V, B16 protection, TN-C-S, no lab data at all."""
    return InstallSpec(
        provenance="assumed",
        provenance_note="מתקן טיפוסי 230/400 V עם מא״ז B16 — ערכים מוערכים בלבד, ללא מדידה",
        network=Network(
            U0=230,
            U1=230,
            U2=230,
            U3=230,
            Z_L=0.25,
            Z_N=0.25,
            Z_PE=0.35,
            In_prot=16,
            curve_prot="B",
        ),
        mcb=Mcb(curve="B", tau=40.0, k_t=1.3, k_m=4.0),
        rcd=Rcd(I_dn=0.03, k_trip=0.75, t0=0.015, t1=0.015),
        insulation=Insulation(
            R_pf=200,
            R_sf=200,
            R_ps=300,
            R_su=2000,
            C_nF=5.0,
            R_s_kohm=500,
            display_max=999,
            R_min=1.0,
        ),
        earth=Earth(
            rho=200,
            rod_L=1.5,
            rod_d=0.016,
            pe_L=10,
            pe_A=10,
            R_contact=0.01,
            R_pe_max=0.05,
        ),
    )


PRESETS = {
    "lab_2025": ("רשת המעבדה: מדידות + התאמה לדוח ניסוי 8 (2025)", lab_2025),
    "assumed_nominal": ("מתקן טיפוסי B16 (ערכים מוערכים, ללא מקור)", assumed_nominal),
}
