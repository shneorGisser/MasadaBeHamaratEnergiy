"""Winding temperature: copper resistance at the operating temperature.

    R(T) = R(T_ref) · (235 + T) / (235 + T_ref)        (copper, IEC 60034-1 / IEC 60076-1)

Every machine spec carries `thermal`: T_ref, the temperature at which its resistances hold (the
cold DC-resistance measurement, normally the lab's ambient), and T_op, the winding temperature
during the load tests. With T_op = T_ref (the default) nothing changes — every stored spec and
every run made before this existed reproduces unchanged.

The correction is applied once, where a study is executed (services.runs.execute_snapshot and
the live operating point), to the copper resistances of the equivalent circuit. Studies done
on a cold machine — the DC-resistance and insulation measurements — keep T_ref.
NOT modelled: the temperature rise itself (T_op is an input, from a thermometer or the
resistance method), the iron and brush drop's temperature dependence, aluminium windings.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

K_CU = 235.0  # °C, inferred zero-resistance temperature of copper

# copper resistances in each experiment's equivalent circuit
COPPER: dict[str, tuple[str, ...]] = {
    "transformer3ph": ("R1", "R2"),
    "induction_motor": ("R1", "R2p"),
    "synchronous": ("Ra", "R_f"),
    "wound_rotor": ("R1", "R2"),
    "dc_motor": ("R_a", "R_f", "R_s"),
    "dc_generator": ("R_a", "R_f", "R_s"),
}
COLD_STUDIES = frozenset({"dc_resistance", "insulation"})


class Thermal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    T_ref: float = Field(default=20.0, ge=-40, le=200, description="°C at which R values hold")
    T_op: float = Field(default=20.0, ge=-40, le=250, description="winding °C in the load tests")

    @property
    def factor(self) -> float:
        return (K_CU + self.T_op) / (K_CU + self.T_ref)


def at_operating_temperature(
    experiment_id: str, spec: Any, study_kind: str
) -> tuple[Any, dict[str, Any] | None]:
    """The spec with its copper resistances at T_op, and the warning that says so (None when
    nothing changed)."""
    th = getattr(spec, "thermal", None)
    fields = COPPER.get(experiment_id)
    if th is None or not fields or study_kind in COLD_STUDIES or th.T_op == th.T_ref:
        return spec, None
    k = th.factor
    ecm = spec.ecm.model_copy(update={f: getattr(spec.ecm, f) * k for f in fields})
    warning = {
        "code": "winding_temperature",
        "message": f"התנגדויות הליפופים ({', '.join(fields)}) תוקנו מ-{th.T_ref:g} °C ל-"
        f"{th.T_op:g} °C: פי {k:.4f} (נחושת, (235 + T)/(235 + T_ref))",
    }
    return spec.model_copy(update={"ecm": ecm}), warning
