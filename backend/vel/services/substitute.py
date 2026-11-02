"""'Formula → numbers' for reports: the same substitution the app shows under each parameter
(frontend/src/components/substitute.ts), so the printed report carries the computation."""

from __future__ import annotations

import math
import re
from typing import Any

_BOUND = "A-Za-z0-9_"


def fmt(v: float, sig: int = 4) -> str:
    """The app's number format (frontend/src/format.ts)."""
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1e6 or a < 1e-3:
        return f"{v:.{sig - 1}e}".replace("e-0", "e-").replace("e+0", "e+").replace("e+", "e")
    digits = max(0, sig - 1 - math.floor(math.log10(a)))
    return f"{v:.{min(digits, 6)}f}"


def substitute(formula: str, inputs: dict[str, float] | None) -> str | None:
    if not inputs:
        return None
    slots: list[str] = []
    out = formula
    for k in sorted(inputs, key=len, reverse=True):
        pat = re.compile(rf"(?<![{_BOUND}]){re.escape(k)}(?![{_BOUND}])")
        if not pat.search(out):
            continue

        def put(_m: re.Match[str], k: str = k) -> str:
            slots.append(fmt(inputs[k]))
            return f"{len(slots) - 1}"

        out = pat.sub(put, out)
    if not slots:
        return None
    return re.sub(
        "(\\d+)",
        lambda m: f"({v})" if (v := slots[int(m.group(1))]).startswith("-") or "e" in v else v,
        out,
    )


def worked(p: dict[str, Any]) -> str:
    """Formula, then '= numbers = result unit' when the inputs were recorded."""
    f = str(p.get("formula", ""))
    sub = substitute(f, p.get("inputs"))
    if sub is None or p.get("value") is None:
        return f
    return f"{f}\n= {sub} = {fmt(float(p['value']))} {p.get('unit', '')}".rstrip()
