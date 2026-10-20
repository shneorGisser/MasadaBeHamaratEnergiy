"""Equipment specification for the network module: the lab's supply feeder.

A fixed radial topology — the one the lab actually hangs from — described by flat sections so
it fits the spec form:

    MV grid (S''k) ─ T (MV/LV, Dyn) ─ B1 main LV board ─ cable 1 ─ B2 lab board ─ cable 2 ─ B3 bench
                                                            load 2 at B2           load 3 at B3

None of it was measured: every value is assumed (a typical 22/0.4 kV, 630 kVA substation and
two cables). The preset says so and every run repeats it. See docs/model-network.md.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Provenance = Literal["assumed", "nameplate", "measured", "fitted"]

BUSES = ("B0", "B1", "B2", "B3")
BUS_LABELS = {
    "B0": "רשת מתח גבוה",
    "B1": "לוח ראשי מ״נ",
    "B2": "לוח המעבדה",
    "B3": "עמדת הניסוי",
}


class Grid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    U_n_kV: float = Field(gt=0, le=400, description="nominal voltage [kV]")
    Sk_max_MVA: float = Field(gt=0, le=1e5, description="S''k at maximum [MVA]")
    Sk_min_MVA: float = Field(gt=0, le=1e5, description="S''k at minimum [MVA]")
    RX: float = Field(ge=0, le=10, description="R/X of the grid")
    f: float = Field(default=50.0, gt=0, le=400)


class Transformer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    S_n_kVA: float = Field(gt=0, le=1e6)
    U1_kV: float = Field(gt=0, le=400)
    U2_V: float = Field(gt=0, le=1000, description="secondary line voltage [V]")
    uk: float = Field(gt=0, le=30, description="short-circuit voltage [%]")
    P_cu_kW: float = Field(ge=0, le=1e4, description="load (copper) loss at S_n [kW]")
    P_0_kW: float = Field(ge=0, le=1e4, description="no-load loss [kW]")
    i0: float = Field(ge=0, le=20, description="no-load current [%]")

    @property
    def ur(self) -> float:
        return 100 * self.P_cu_kW / self.S_n_kVA


class Cable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    L_m: float = Field(gt=0, le=1e5)
    r: float = Field(gt=0, le=100, description="R' at 20 °C [Ω/km]")
    x: float = Field(ge=0, le=100, description="X' [Ω/km]")
    r0_r: float = Field(default=4.0, gt=0, le=50, description="R0'/R' (zero sequence)")
    x0_x: float = Field(default=4.0, gt=0, le=50, description="X0'/X' (zero sequence)")
    I_max: float = Field(gt=0, le=1e5, description="current rating [A]")


class Loads(BaseModel):
    model_config = ConfigDict(extra="forbid")
    P2_kW: float = Field(ge=0, le=1e5)
    pf2: float = Field(gt=0, le=1)
    P3_kW: float = Field(ge=0, le=1e5)
    pf3: float = Field(gt=0, le=1)


class NetworkSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provenance: Provenance
    provenance_note: str = ""
    grid: Grid
    trafo: Transformer
    cable1: Cable
    cable2: Cable
    loads: Loads

    @property
    def I_n_lv(self) -> float:
        return self.trafo.S_n_kVA * 1e3 / (math.sqrt(3) * self.trafo.U2_V)


def typical_substation() -> NetworkSpec:
    return NetworkSpec(
        provenance="assumed",
        provenance_note=(
            "כל הערכים מוערכים: תחנת השנאה טיפוסית 22/0.4 kV, 630 kVA, uk = 6 %; רשת "
            "ההזנה S''k = 250/150 MVA; כבל ראשי 4×150 mm² אלומיניום 80 m וכבל לעמדה "
            "4×16 mm² נחושת 30 m; עומסים משוערים. לא נמדד דבר"
        ),
        grid=Grid(U_n_kV=22.0, Sk_max_MVA=250.0, Sk_min_MVA=150.0, RX=0.1),
        trafo=Transformer(
            S_n_kVA=630.0, U1_kV=22.0, U2_V=400.0, uk=6.0, P_cu_kW=6.5, P_0_kW=1.2, i0=0.3
        ),
        cable1=Cable(L_m=80.0, r=0.206, x=0.080, I_max=275.0),
        cable2=Cable(L_m=30.0, r=1.15, x=0.080, I_max=80.0),
        loads=Loads(P2_kW=40.0, pf2=0.9, P3_kW=5.0, pf3=0.85),
    )


PRESETS = {
    "typical_substation": ("הזנת המעבדה: תחנה טיפוסית 630 kVA (ערכים מוערכים)", typical_substation),
}
