"""Equipment specification for experiment 4: slip-ring (wound-rotor) induction machine.

Per-phase T-equivalent with the rotor NOT referred: stator R1 + jX1, magnetizing branch
R_fe ‖ jXm across E1, an ideal transformer E1 = k·E2 (k = stator/rotor effective turns ratio,
per phase), and the actual rotor winding R2 + jX2 (X2 at rated frequency) to the slip rings.
The rotor is star-connected inside the machine; only R1, R2, R3 are accessible. Stator values
are per winding; rotor values per rotor phase.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Provenance = Literal["assumed", "nameplate", "measured", "fitted"]


class WoundNameplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    P_n: float = Field(gt=0, le=1e6)
    U_n: float = Field(gt=0, le=1e5, description="stator line voltage [V]")
    I_n: float = Field(gt=0, le=1e4)
    f_n: float = Field(gt=0, le=1000)
    n_n: float = Field(gt=0, le=1e5)
    poles: Literal[2, 4, 6, 8, 10, 12] = 4
    connection: Literal["Y", "D"] = "Y"
    cos_phi_n: float | None = Field(default=None, gt=0, le=1)
    U2_n: float = Field(gt=0, le=1e5, description="rotor standstill open-circuit line voltage")
    I2_n: float = Field(gt=0, le=1e4, description="rated rotor current [A]")

    @model_validator(mode="after")
    def _below_sync(self) -> WoundNameplate:
        ns = 120 * self.f_n / self.poles
        if self.n_n >= ns:
            raise ValueError(f"rated speed {self.n_n:g} rpm must be below {ns:g} rpm")
        return self


class WoundECM(BaseModel):
    model_config = ConfigDict(extra="forbid")
    R1: float = Field(gt=0, le=1e5)
    X1: float = Field(ge=0, le=1e5)
    R2: float = Field(gt=0, le=1e5, description="rotor phase resistance (actual) [Ω]")
    X2: float = Field(ge=0, le=1e5, description="rotor phase leakage reactance at f_n [Ω]")
    k: float = Field(gt=0, le=1e3, description="stator/rotor effective turns ratio")
    R_fe: float = Field(gt=0, le=1e9)
    Xm: float = Field(gt=0, le=1e9)
    P_fw_n: float = Field(ge=0, le=1e5, description="friction + windage at rated speed [W]")


class WoundInsulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_frame_Mohm: float = Field(gt=0, le=1e6)
    V_frame_Mohm: float = Field(gt=0, le=1e6)
    W_frame_Mohm: float = Field(gt=0, le=1e6)
    rotor_frame_Mohm: float = Field(gt=0, le=1e6)


class WoundSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    provenance: Provenance
    provenance_note: str = Field(default="", max_length=2000)
    nameplate: WoundNameplate
    ecm: WoundECM
    insulation: WoundInsulation

    @property
    def n_sync(self) -> float:
        return 120 * self.nameplate.f_n / self.nameplate.poles

    @property
    def slip_n(self) -> float:
        return (self.n_sync - self.nameplate.n_n) / self.n_sync

    @property
    def M_n(self) -> float:
        return self.nameplate.P_n / (2 * math.pi * self.nameplate.n_n / 60)

    @property
    def U_winding(self) -> float:
        n = self.nameplate
        return n.U_n if n.connection == "D" else n.U_n / math.sqrt(3)

    @property
    def R2_referred(self) -> float:
        return self.ecm.k**2 * self.ecm.R2

    @property
    def X2_referred(self) -> float:
        return self.ecm.k**2 * self.ecm.X2


def nameplate_fit() -> WoundSpec:
    """Fitted to the nameplate photographed in the lab (the same slip-ring machine as
    experiment 3), plus two measurements from the student's experiment-3 report.

    Inputs: 400 V Y, 0.83 A, cos φ 0.70, 0.27 kW at 1360 rpm, 50 Hz, 4 poles; rotor 107 V at
    standstill; stator R1 = 33.3 Ω (table 6.2); X1 + Xm = 674 Ω (the synchronous reactance of
    experiment 3 — same magnetic circuit). Least squares with X1 = X2' gives R2' = 21.53 Ω,
    X1 = X2' = 77.0 Ω, Xm = 597 Ω, R_fe = 20.0 kΩ, P_fw = 28.7 W, matching I, cos φ and P2
    to < 1e-8. The effective ratio k = 3.3027 is chosen so that the MODEL's open-rotor voltage
    at 400 V is the plate's 107 V (the plate value includes the stator drop of the magnetizing
    current; 400/107 = 3.738 would give 94.5 V). R2 = R2'/k², X2 = X2'/k².

    KNOWN INCONSISTENCIES (not hidden): the model then needs 2.28 A in the rotor at rated
    load, the plate says 1.7 A — no T-equivalent satisfies all plate values together (best
    compromise misses several by 8–11 %); and R2 = 1.97 Ω vs the 6.4 Ω measured between
    F1–F2 in experiment 3 (two rotor phases in series would be 3.9 Ω). Experiment 4's own DC,
    no-load and locked-rotor tests settle this.
    """
    k = 3.3027
    return WoundSpec(
        provenance="fitted",
        provenance_note=(
            "הותאם לשלט שצולם (אותה מכונה כמו בניסוי 3), ל-R1 = 33.3 Ω ול-X1+Xm = 674 Ω מניסוי 3. "
            "תואם בדיוק זרם, cos φ, הספק ומתח רוטור פתוח נקובים; אינו תואם את זרם הרוטור שבשלט "
            "(2.3 A מול 1.7 A) — "
            "יש לעדכן לאחר ניסויי DC, ריקם וקצר"
        ),
        nameplate=WoundNameplate(
            P_n=270,
            U_n=400,
            I_n=0.83,
            f_n=50,
            n_n=1360,
            poles=4,
            connection="Y",
            cos_phi_n=0.70,
            U2_n=107,
            I2_n=1.7,
        ),
        ecm=WoundECM(
            R1=33.3,
            X1=77.0,
            R2=round(21.53 / k**2, 4),
            X2=round(77.0 / k**2, 4),
            k=round(k, 5),
            R_fe=20025.0,
            Xm=597.0,
            P_fw_n=28.7,
        ),
        insulation=WoundInsulation(
            U_frame_Mohm=1000, V_frame_Mohm=1000, W_frame_Mohm=1000, rotor_frame_Mohm=831
        ),
    )


PRESETS = {
    "nameplate_fit": (
        "מותאם לשלט 0.27 kW / 400 V / 1360 סל״ד ולמדידות ניסוי 3 (לא מאומת)",
        nameplate_fit,
    ),
}
