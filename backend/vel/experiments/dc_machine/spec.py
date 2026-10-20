"""Equipment specification for experiments 5 and 6: DC machine (shunt + series field).

Steady-state model, all quantities DC:
* Armature: A1 —R_a— (EMF E − brush drop) — A2. Brush drop U_b·tanh(I_a / 0.05 A), i.e. a
  constant ≈ U_b (the manual's "2 V·I_a" loss term) that changes sign smoothly with the current.
* Field MMF in shunt-field amperes: F = I_f + ρ_s·I_s − k_ar·|I_a| + F_res, where I_f flows
  F1→F2, I_s flows S1→S2 (so reversing S1–S2 turns a cumulative compound into a differential
  one), ρ_s = N_series/N_shunt, k_ar models the demagnetizing armature reaction, F_res the
  remanence (so a shunt generator can build up — or fail to).
* EMF at speed n: E = (n/n_ref)·OCC(F), OCC(F) = a·F/(1 + (|F|/I_s)^m)^(1/m) (odd in F).
* Electromagnetic torque M_em = E·I_a/ω; rotational losses P_rot(n) = P_rot_n·|n/n_n|^k_rot
  (k_rot = 1: a constant friction torque M_0 = P_rot_n/ω_n, which is what the lab data show).
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Provenance = Literal["assumed", "nameplate", "measured", "fitted"]


class DCNameplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    P_n: float = Field(gt=0, le=1e7, description="rated output [W]")
    U_n: float = Field(gt=0, le=1e5, description="rated armature voltage [V]")
    I_n: float = Field(gt=0, le=1e5, description="rated armature current [A]")
    n_n: float = Field(gt=0, le=1e5, description="rated speed [rpm]")
    If_n: float = Field(gt=0, le=1e3, description="rated shunt-field current [A]")
    n_max: float = Field(gt=0, le=1e5, description="maximum permitted speed [rpm]")


class DCECM(BaseModel):
    model_config = ConfigDict(extra="forbid")
    R_a: float = Field(gt=0, le=1e4, description="armature circuit resistance (incl. interpoles)")
    R_f: float = Field(gt=0, le=1e6, description="shunt-field winding resistance [Ω]")
    R_s: float = Field(gt=0, le=1e4, description="series-field winding resistance [Ω]")
    U_brush: float = Field(ge=0, le=20, description="total brush drop [V]")
    rho_s: float = Field(ge=0, le=10, description="series/shunt turns ratio")
    k_ar: float = Field(ge=0, le=1, description="armature reaction [field A per armature A]")
    P_rot_n: float = Field(ge=0, le=1e5, description="friction + windage + iron at n_n [W]")
    k_rot: float = Field(default=1.0, ge=1, le=3, description="P_rot ∝ |n|^k_rot")


class DCOcc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_ref: float = Field(gt=0, le=1e5, description="speed at which the OCC is defined [rpm]")
    a: float = Field(gt=0, le=1e7, description="air-gap line slope [V per field A]")
    I_s: float = Field(gt=0, le=1e3, description="saturation knee [field A]")
    m: float = Field(ge=1, le=50)
    F_res: float = Field(ge=-10, le=10, description="remanence as field-current offset [A]")
    F_h: float = Field(
        default=0.0,
        ge=0,
        le=10,
        description="hysteresis: largest MMF shift of the descending branch [field A]",
    )

    def emf(self, f: float) -> float:
        """Signed EMF at n_ref for a resultant MMF of f shunt-field amperes."""
        x = abs(f)
        mag = self.a * x / (1 + (x / self.I_s) ** self.m) ** (1 / self.m)
        return float(math.copysign(mag, f))

    def descending_shift(self, i_f: float, i_f_max: float) -> float:
        """MMF shift of the descending branch at i_f, coming down from i_f_max: zero at both
        ends (it starts at the turning point and returns to the remanence) and largest half
        way — δ = 4·F_h·x·(1 − x), x = i_f / i_f_max. A one-parameter shape, fitted to the
        2025 DC-machine table; it is not a magnetic hysteresis model (no minor loops)."""
        if self.F_h <= 0 or i_f_max <= 0:
            return 0.0
        x = min(max(i_f / i_f_max, 0.0), 1.0)
        return 4 * self.F_h * x * (1 - x)


class DCInsulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    armature_Mohm: float = Field(gt=0, le=1e6)
    shunt_Mohm: float = Field(gt=0, le=1e6)
    series_Mohm: float = Field(gt=0, le=1e6)


class DCSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    provenance: Provenance
    provenance_note: str = Field(default="", max_length=2000)
    nameplate: DCNameplate
    ecm: DCECM
    occ: DCOcc
    insulation: DCInsulation

    @property
    def M_n(self) -> float:
        return self.nameplate.P_n / (2 * math.pi * self.nameplate.n_n / 60)

    @property
    def k_phi_n(self) -> float:
        """E/ω at rated field (V·s/rad) on the OCC, without armature reaction."""
        e = self.occ.emf(self.nameplate.If_n + self.occ.F_res)
        return e / (2 * math.pi * self.occ.n_ref / 60)


def fitted_lab_dc_machine() -> DCSpec:
    """The lab's DC machine (same machine in experiments 5 and 6), nameplate from the 2025
    reports and parameters fitted by least squares to their measured tables (see
    docs/model-dc-machine.md): motor tables 5/2.3, 2.4, 2.5, 2.8 (speed within 20 rpm, torque
    within 0.05 N·m) and generator OCC 6/2.3 (within 3 V, at an implied ≈ 2550 rpm)."""
    return DCSpec(
        provenance="fitted",
        provenance_note=(
            "שלט: 220 V, 2.5 A, 2500 סל״ד, 370 W, עירור 220 V / 0.3 A. Ra, Rs, Rf נמדדו "
            "(ניסויים 5, 6 של 2025); עקומת הריקם, תגובת העוגן, יחס הליפוף הטורי וחיכוך "
            "הותאמו לטבלאות 5/2.3–2.8 ו-6/2.3. n_max = 3000 סל״ד מוערך (לא רשום בשלט)"
        ),
        nameplate=DCNameplate(P_n=370, U_n=220, I_n=2.5, n_n=2500, If_n=0.3, n_max=3000),
        ecm=DCECM(
            R_a=12.5,
            R_f=368.0,
            R_s=5.2,
            U_brush=2.0,
            rho_s=0.193,
            k_ar=0.0187,
            P_rot_n=63.9,
            k_rot=1.0,
        ),
        occ=DCOcc(n_ref=2000, a=612.0, I_s=0.2912, m=2.571, F_res=0.005, F_h=0.013),
        insulation=DCInsulation(armature_Mohm=462, shunt_Mohm=999, series_Mohm=999),
    )


def assumed_lab_dc_machine() -> DCSpec:
    """Placeholder until the DC machine's nameplate is known. Sized so that the manual's
    operating points are reachable and consistent: 240 V motor, ≈ 2390 rpm initial speed with a
    weakened field, 220 V separately/shunt-excited generator, armature current below 2 A for the
    resistance test. Values typical of a 0.3 kW educational machine — NOT measured."""
    return DCSpec(
        provenance="assumed",
        provenance_note=(
            "ערכים מוערכים למכונת זרם ישר טיפוסית של מעבדה (0.3 kW, 220 V, 2000 סל״ד). אינם "
            "נתוני המכונה במעבדה — יש להחליף לאחר צילום השלט ומדידת ההתנגדויות"
        ),
        nameplate=DCNameplate(P_n=300, U_n=220, I_n=1.8, n_n=2000, If_n=0.25, n_max=3000),
        ecm=DCECM(R_a=9.0, R_f=800.0, R_s=1.5, U_brush=2.0, rho_s=0.02, k_ar=0.006, P_rot_n=28.0),
        occ=DCOcc(n_ref=2000, a=1500.0, I_s=0.17, m=2.5, F_res=0.004),
        insulation=DCInsulation(armature_Mohm=500, shunt_Mohm=500, series_Mohm=500),
    )


PRESETS = {
    "lab_2025_fit": (
        "המכונה במעבדה: שלט + התאמה לדוחות ניסויים 5 ו-6 (2025)",
        fitted_lab_dc_machine,
    ),
    "assumed_03kw": (
        "ערכים מוערכים: מכונת DC ‏0.3 kW, ‏220 V, ‏2000 סל״ד (ללא מקור)",
        assumed_lab_dc_machine,
    ),
}
