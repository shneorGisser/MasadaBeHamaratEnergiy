"""What a student records in the lab for each study (mirrors the manual's tables)."""

from __future__ import annotations

from vel.experiments.common import MCol, MeasureDef
from vel.experiments.transformer3ph.studies import WINDINGS

__all__ = ["MCol", "MeasureDef", "MEASURE_DEFS"]

_DC_LABELS = tuple(f"{label} · נקודה {k}" for _, label in WINDINGS for k in (1, 2, 3))

MEASURE_DEFS: dict[str, MeasureDef] = {
    d.kind: d
    for d in [
        MeasureDef(
            "no_load",
            (
                MCol("U1L", "U1 קווי", "V"),
                MCol("U1ph", "U1 פאזי", "V"),
                MCol("U2L", "U2 קווי", "V"),
                MCol("U2ph", "U2 פאזי", "V"),
                MCol("I0", "I0", "A"),
                MCol("P_W", "קריאת מד ההספק", "W"),
                MCol("pf", "cos φ0", ""),
            ),
            "free",
            "U1L",
        ),
        MeasureDef(
            "short_circuit",
            (
                MCol("U_k", "Uk קווי", "V"),
                MCol("I1k", "I1k", "A"),
                MCol("I2k", "I2k", "A"),
                MCol("P_W", "קריאת מד ההספק", "W"),
                MCol("pf", "cos φk", ""),
            ),
            "free",
            "I1k",
        ),
        MeasureDef(
            "load",
            (
                MCol("U1L", "U1 קווי", "V"),
                MCol("I1", "I1", "A"),
                MCol("P1_W", "מד הספק ראשוני", "W"),
                MCol("pf1", "cos φ1", ""),
                MCol("U2L", "U2 קווי", "V"),
                MCol("U2ph", "U2 פאזי", "V"),
                MCol("I2", "I2", "A"),
                MCol("P2_W", "מד הספק משני", "W"),
                MCol("pf2", "cos φ2", ""),
            ),
            "free",
            "I2",
            condition_keys=("load_kind",),
        ),
        MeasureDef(
            "vector_group",
            (
                MCol("U_aAB", "U aA–B1", "V"),
                MCol("U_aAb", "U aA–b1", "V"),
                MCol("U_Bb", "U B1–b1", "V"),
            ),
            "fixed",
            "row",
            row_labels=("מדידה",),
            condition_keys=("variant",),
        ),
        MeasureDef(
            "dc_resistance",
            (MCol("I", "I", "A"), MCol("U", "U", "V")),
            "fixed",
            "row",
            row_labels=_DC_LABELS,
        ),
        MeasureDef(
            "insulation",
            (MCol("R_ins", "התנגדות בידוד", "MΩ"),),
            "fixed",
            "row",
            row_labels=("ראשוני – גרעין", "משני – גרעין", "ראשוני – משני"),
        ),
    ]
}
