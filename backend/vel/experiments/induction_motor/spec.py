"""Equipment specification for experiment 2: three-phase squirrel-cage induction motor.

Equivalent-circuit values are PER WINDING (between U1–U2, V1–V2, W1–W2), referred to the
stator, at rated frequency f_n. A per-winding definition is independent of how the windings
are connected on the terminal board (Y or Δ), so the same spec works for either connection.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vel.experiments.thermal import Thermal

Provenance = Literal["assumed", "nameplate", "measured", "fitted"]


class MotorNameplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    P_n: float = Field(gt=0, le=1e6, description="rated shaft power [W]")
    U_n: float = Field(gt=0, le=1e5, description="rated line voltage [V]")
    I_n: float = Field(gt=0, le=1e4, description="rated line current [A]")
    f_n: float = Field(gt=0, le=1000, description="rated frequency [Hz]")
    n_n: float = Field(gt=0, le=1e5, description="rated speed [rpm]")
    poles: Literal[2, 4, 6, 8, 10, 12] = 4
    connection: Literal["Y", "D"] = "Y"
    cos_phi_n: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def _below_sync(self) -> MotorNameplate:
        ns = 120 * self.f_n / self.poles
        if self.n_n >= ns:
            raise ValueError(
                f"rated speed {self.n_n:g} rpm must be below synchronous speed {ns:g} rpm "
                f"({self.poles} poles, {self.f_n:g} Hz)"
            )
        return self


class MotorECM(BaseModel):
    model_config = ConfigDict(extra="forbid")
    R1: float = Field(gt=0, le=1e5, description="stator winding resistance [Ω]")
    X1: float = Field(ge=0, le=1e5, description="stator leakage reactance at f_n [Ω]")
    R2p: float = Field(gt=0, le=1e5, description="rotor resistance referred to stator [Ω]")
    X2p: float = Field(ge=0, le=1e5, description="rotor leakage reactance referred, at f_n [Ω]")
    R_fe: float = Field(gt=0, le=1e9, description="core-loss resistance [Ω]")
    Xm: float = Field(gt=0, le=1e9, description="magnetizing reactance at f_n [Ω]")
    P_fw_n: float = Field(
        ge=0, le=1e5, description="friction + windage loss at rated speed [W]; ∝ n²"
    )


class MotorInsulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_frame_Mohm: float = Field(gt=0, le=1e6)
    V_frame_Mohm: float = Field(gt=0, le=1e6)
    W_frame_Mohm: float = Field(gt=0, le=1e6)


class MotorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    provenance: Provenance
    provenance_note: str = Field(default="", max_length=2000)
    nameplate: MotorNameplate
    ecm: MotorECM
    thermal: Thermal = Field(default_factory=Thermal)
    insulation: MotorInsulation

    @property
    def n_sync(self) -> float:
        return 120 * self.nameplate.f_n / self.nameplate.poles

    @property
    def slip_n(self) -> float:
        return (self.n_sync - self.nameplate.n_n) / self.n_sync

    @property
    def M_n(self) -> float:
        """Rated shaft torque [N·m] = P_n / ω_n (the manual's M_n = 9.55·P_n/n_n)."""
        return self.nameplate.P_n / (2 * math.pi * self.nameplate.n_n / 60)

    @property
    def U_winding(self) -> float:
        n = self.nameplate
        return n.U_n if n.connection == "D" else n.U_n / math.sqrt(3)

    @property
    def I_winding(self) -> float:
        n = self.nameplate
        return n.I_n / math.sqrt(3) if n.connection == "D" else n.I_n


def assumed_lab_motor() -> MotorSpec:
    """Placeholder until the lab nameplate is known. A typical 0.37 kW, 4-pole educational
    motor. The equivalent circuit was sized so that it is self-consistent with the nameplate:
    at 1380 rpm it delivers ≈ 380 W at ≈ 1.02 A, cos φ ≈ 0.80, η ≈ 0.71; I_start ≈ 4·I_n,
    M_start ≈ 2.1·M_n, M_max ≈ 2.5·M_n at s ≈ 0.49 (small motors have large R2')."""
    return MotorSpec(
        provenance="assumed",
        provenance_note=(
            "ערכים מוערכים למנוע השראה טיפוסי של מעבדה (0.37 kW, 4 קטבים, 380 V בכוכב). "
            "אינם נתוני השלט של המנוע במעבדה — יש להחליף לאחר צילום השלט."
        ),
        nameplate=MotorNameplate(
            P_n=370, U_n=380, I_n=1.02, f_n=50, n_n=1380, poles=4, connection="Y", cos_phi_n=0.80
        ),
        ecm=MotorECM(R1=24, X1=17, R2p=20, X2p=17, R_fe=3300, Xm=330, P_fw_n=14),
        insulation=MotorInsulation(U_frame_Mohm=500, V_frame_Mohm=500, W_frame_Mohm=500),
    )


PRESETS = {
    "assumed_037kw": (
        "ערכים מוערכים: מנוע 0.37 kW, 380 V Y, 1380 סל״ד (ללא מקור)",
        assumed_lab_motor,
    ),
}
