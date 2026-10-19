"""Explicit unit conversion for entered measurements.

Each table column has a canonical unit (the one shown in the column header). An entered value
is converted to that canonical unit; incompatible units (e.g. mA for a voltage column) are
rejected, never silently coerced.
"""

from __future__ import annotations

import math

DIMENSIONS: dict[str, dict[str, float]] = {
    "voltage": {"V": 1.0, "mV": 1e-3, "kV": 1e3},
    "current": {"A": 1.0, "mA": 1e-3, "µA": 1e-6, "kA": 1e3},
    "power": {"W": 1.0, "mW": 1e-3, "kW": 1e3},
    "resistance": {"Ω": 1.0, "mΩ": 1e-3, "kΩ": 1e3, "MΩ": 1e6},
    "dimensionless": {"": 1.0},
    "angle": {"°": 1.0},
    "speed": {"rpm": 1.0, "rps": 60.0},
    "torque": {"N·m": 1.0, "mN·m": 1e-3},
    "frequency": {"Hz": 1.0},
}

UNIT_DIMENSION: dict[str, str] = {u: d for d, units in DIMENSIONS.items() for u in units}


class UnitError(ValueError):
    pass


def dimension_of(unit: str) -> str:
    try:
        return UNIT_DIMENSION[unit]
    except KeyError as exc:
        raise UnitError(f"unknown unit {unit!r}") from exc


def convert(value: float, from_unit: str, to_unit: str) -> float:
    if not math.isfinite(value):
        raise UnitError("value must be a finite number")
    d_from, d_to = dimension_of(from_unit), dimension_of(to_unit)
    if d_from != d_to:
        raise UnitError(f"cannot convert {from_unit!r} ({d_from}) to {to_unit!r} ({d_to})")
    table = DIMENSIONS[d_from]
    return value * table[from_unit] / table[to_unit]


def units_for(canonical: str) -> list[str]:
    return list(DIMENSIONS[dimension_of(canonical)])
