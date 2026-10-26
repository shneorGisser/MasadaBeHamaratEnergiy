"""Protective devices from pandapower's protection library, plus IEC 60255 inverse-time relays.

Why pandapower: its standard library carries real catalogue time–current curves (HV fuses,
Siemens NH fuses) and evaluates them the same way its protection module does (log–log PCHIP
through the catalogue points, ``LogSplineCharacteristic``). Using those objects — instead of
re-typing curve points — keeps our numbers identical to the library's and lets its updates
reach us.

Catalogue curves end where the catalogue ends. pandapower answers "∞" below the first point and
"0 s" above the last. We return None with a reason instead: an extrapolated or invented time is
a fabricated result.

The relay is IEC 60255-151 (= BS 142) inverse-time overcurrent, t = TMS·k/((I/I_s)^α − 1),
with the constants of pandapower's OCRelay (standard, very, extremely and long-time inverse).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import pandapower as pp
from pandapower.protection.protection_devices.fuse import Fuse

Curve = Literal["standard_inverse", "very_inverse", "extremely_inverse", "long_inverse"]
IDMT: dict[str, tuple[float, float]] = {  # (k, α), IEC 60255-151 table 1
    "standard_inverse": (0.14, 0.02),
    "very_inverse": (13.5, 1.0),
    "extremely_inverse": (80.0, 2.0),
    "long_inverse": (120.0, 1.0),
}


@lru_cache(maxsize=1)
def _fuse_library() -> dict[str, dict[str, Any]]:
    return dict(pp.create_empty_network().std_types["fuse"])


def fuse_types(prefix: str) -> list[str]:
    """Catalogue names, e.g. prefix 'HV ' or 'Siemens NH'."""
    return sorted(
        (k for k in _fuse_library() if k.startswith(prefix)),
        key=lambda k: float(_fuse_library()[k]["i_rated_a"]),
    )


@dataclass(frozen=True)
class FuseCurve:
    """One catalogue curve of a fuse (pre-arcing minimum, total clearing, or average)."""

    name: str
    kind: Literal["min", "total", "avg"]
    i_rated: float
    i_lo: float  # first catalogue point [A]
    i_hi: float  # last catalogue point [A]
    t_hi: float  # time at i_lo [s]
    t_lo: float  # time at i_hi [s]
    _net: object
    _index: int

    def time(self, current: float) -> tuple[float | None, str | None]:
        """Operating time [s] at `current` [A], or (None, reason)."""
        if current < self.i_lo:
            return None, f"מתחת לתחום הקטלוג ({self.i_lo:g} A, {self.t_hi:g} s): אינו נשרף בזמן הזה"
        if current > self.i_hi:
            return None, f"מעל לתחום הקטלוג ({self.i_hi:g} A): פחות מ-{self.t_lo:g} s"
        c = self._net.characteristic.at[self._index, "object"]  # type: ignore[attr-defined]
        return float(c(current)), None


@lru_cache(maxsize=64)
def fuse_curve(fuse_type: str, kind: Literal["min", "total", "avg"] = "total") -> FuseCurve:
    """The catalogue curve built by pandapower's own Fuse class. kind: 'min' = pre-arcing
    (melting) minimum, 'total' = total clearing; NH entries carry one average curve ('avg'),
    returned for any kind."""
    lib = _fuse_library()
    if fuse_type not in lib:
        raise KeyError(f"unknown fuse type {fuse_type!r}")
    data = lib[fuse_type]
    net = pp.create_empty_network()
    b0, b1 = pp.create_bus(net, 0.4), pp.create_bus(net, 0.4)
    sw = pp.create_switch(net, b0, b1, et="b")
    has_avg = data["t_avg"] not in (0, "0")
    curve_select = 1 if kind == "total" else 0
    if not has_avg and kind == "avg":
        raise ValueError(f"{fuse_type} has no average curve")
    f = Fuse(net, sw, fuse_type=fuse_type, curve_select=curve_select)
    key = "avg" if has_avg else ("total" if curve_select else "min")
    xs = [float(x) for x in data[f"x_{key}"]]
    ts = [float(t) for t in data[f"t_{key}"]]
    return FuseCurve(
        fuse_type,
        key,  # type: ignore[arg-type]
        float(data["i_rated_a"]),
        min(xs),
        max(xs),
        ts[0],
        ts[-1],
        net,
        int(f.characteristic_index),
    )


@dataclass(frozen=True)
class Relay:
    """Inverse-time overcurrent relay (IEC 60255-151) with an optional instantaneous stage."""

    I_s: float  # pick-up [A]
    tms: float
    curve: Curve = "standard_inverse"
    I_inst: float | None = None  # instantaneous stage [A]
    t_inst: float = 0.05

    def time(self, current: float) -> tuple[float | None, str | None]:
        if self.I_inst and current >= self.I_inst:
            return self.t_inst, None
        m = current / self.I_s
        if m <= 1.0:
            return None, f"מתחת לזרם ההתעוררות ({self.I_s:g} A)"
        k, a = IDMT[self.curve]
        return self.tms * k / (m**a - 1.0), None


def coordination_margin(
    t_down: float | None, t_up: float | None
) -> tuple[float | None, Literal["ok", "fail", "upstream_idle", "downstream_idle"]]:
    """Grading time t_up − t_down at one current."""
    if t_up is None:
        return None, "upstream_idle"
    if t_down is None:
        return None, "downstream_idle"
    return t_up - t_down, "ok" if t_up > t_down else "fail"


def log_grid(lo: float, hi: float, n: int = 200) -> list[float]:
    a, b = math.log10(lo), math.log10(hi)
    return [10 ** (a + (b - a) * i / (n - 1)) for i in range(n)]
