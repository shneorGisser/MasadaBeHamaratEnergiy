"""Derived quantities and parameter extraction from a table of readings.

Used for BOTH simulated and measured tables, so a measured table goes through exactly the same
equations as a simulated one (no duplicated engineering logic).
"""

from __future__ import annotations

import math
from typing import Any

from vel.experiments.transformer3ph import analysis
from vel.experiments.transformer3ph.spec import TransformerSpec

Row = dict[str, Any]


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def _times3(v: Any) -> float | None:
    x = _num(v)
    return 3 * x if x is not None else None


def _nearest(rows: list[Row], key: str, target: float, needed: tuple[str, ...]) -> int | None:
    cands = [
        i for i, r in enumerate(rows) if all(_num(r.get(k)) is not None for k in (key, *needed))
    ]
    if not cands:
        return None
    return min(cands, key=lambda i: abs(float(rows[i][key]) - target))


def no_load(
    rows: list[Row], spec: TransformerSpec
) -> tuple[list[Row], list[analysis.Param], dict[str, Any], list[dict[str, Any]]]:
    out = [{**r, "P0": _times3(r.get("P_W"))} for r in rows]
    warnings: list[dict[str, Any]] = []
    U1n = spec.nameplate.U1n
    needed = ("U1L", "I0", "P0", "U1ph", "U2ph", "U2L")
    idx = _nearest(out, "U1L", U1n, needed[1:])
    if idx is None:
        warnings.append(
            {"code": "insufficient_data", "message": "אין שורה מלאה לחישוב פרמטרי הריקם"}
        )
        return out, [], {}, warnings
    r = out[idx]
    if abs(float(r["U1L"]) - U1n) > 0.02 * U1n:
        warnings.append(
            {
                "code": "rated_point_missing",
                "message": f"אין מדידה ב-Un = {U1n:g} V (±2%); "
                f"הפרמטרים חושבו ב-{float(r['U1L']):.4g} V",
            }
        )
    params = analysis.no_load_parameters(r["U1L"], r["I0"], r["P0"], r["U1ph"], r["U2ph"], r["U2L"])
    return out, params, {"row": idx, "U1L": r["U1L"]}, warnings


def short_circuit(
    rows: list[Row], spec: TransformerSpec
) -> tuple[list[Row], list[analysis.Param], dict[str, Any], list[dict[str, Any]]]:
    out = [{**r, "P_k": _times3(r.get("P_W"))} for r in rows]
    warnings: list[dict[str, Any]] = []
    I1n = spec.I1n_line
    idx = _nearest(out, "I1k", I1n, ("U_k", "P_k"))
    if idx is None:
        warnings.append(
            {"code": "insufficient_data", "message": "אין שורה מלאה לחישוב פרמטרי הקצר"}
        )
        return out, [], {}, warnings
    r = out[idx]
    if abs(float(r["I1k"]) - I1n) > 0.05 * I1n:
        warnings.append(
            {
                "code": "rated_point_missing",
                "message": f"הנקודה הקרובה ל-I1n היא {float(r['I1k']):.4g} A; "
                "u_k מוקטן לזרם הנומינלי",
            }
        )
    params = analysis.short_circuit_parameters(
        r["U_k"], r["I1k"], r["P_k"], spec.nameplate.U1n, I1n
    )
    return out, params, {"row": idx, "I1k": r["I1k"]}, warnings


def load(rows: list[Row], spec: TransformerSpec) -> list[Row]:
    I2n = spec.I2n_line
    out: list[Row] = []
    for r in rows:
        p1, p2 = _times3(r.get("P1_W")), _times3(r.get("P2_W"))
        i2 = _num(r.get("I2"))
        out.append(
            {
                **r,
                "P1": p1,
                "P2": p2,
                "beta": (i2 / I2n) if i2 is not None else None,
                "eta": (p2 / p1) if (p1 and p2 is not None) else None,
            }
        )

    # regulation relative to the no-load row (I2 ≈ 0), if one exists
    def is_no_load(r: Row) -> bool:
        i2 = _num(r.get("I2"))
        return i2 is not None and abs(i2) < 1e-6 and _num(r.get("U2L")) is not None

    nl = next((r for r in out if is_no_load(r)), None)
    u20 = _num(nl.get("U2L")) if nl else None
    for r in out:
        u2 = _num(r.get("U2L"))
        r["dU_pct"] = 100 * (u20 - u2) / u20 if (u20 and u2 is not None) else None
    return out


def vector_group(rows: list[Row]) -> list[analysis.Param]:
    r = rows[0] if rows else {}
    vals = [_num(r.get(k)) for k in ("U_aAB", "U_aAb", "U_Bb")]
    if any(v is None for v in vals):
        return [analysis.Param("theta", "זווית", None, "°", "", "manual", "חסרות מדידות")]
    a, b, c = vals
    assert a is not None and b is not None and c is not None
    return analysis.vector_group_parameters(a, b, c)


def dc_resistance(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    out = []
    for r in rows:
        u, i = _num(r.get("U")), _num(r.get("I"))
        out.append({**r, "R": (u / i) if (u is not None and i) else None})
    groups: dict[str, list[float]] = {}
    for r in out:
        if r.get("R") is not None:
            groups.setdefault(str(r.get("winding")), []).append(float(r["R"]))
    summary = [{"winding": w, "R_avg": sum(v) / len(v), "n": len(v)} for w, v in groups.items()]
    return out, summary


def plausibility(kind: str, rows: list[Row], spec: TransformerSpec) -> list[dict[str, Any]]:
    """Physical sanity checks on a (measured) table. They do not change any value; they point
    the student to entries that cannot all be right (typo, wrong unit, line/phase confusion)."""
    s3 = math.sqrt(3)
    out: list[dict[str, Any]] = []
    # (P column, voltage expression, current column, pf column) — wattmeter on one phase
    triples: dict[str, list[tuple[str, Any, str, str | None]]] = {
        "no_load": [("P_W", lambda r: r.get("U1ph"), "I0", "pf")],
        "short_circuit": [
            (
                "P_W",
                lambda r: (_num(r.get("U_k")) or 0) / s3 if _num(r.get("U_k")) else None,
                "I1k",
                "pf",
            )
        ],
        "load": [
            (
                "P1_W",
                lambda r: (_num(r.get("U1L")) or 0) / s3 if _num(r.get("U1L")) else None,
                "I1",
                "pf1",
            ),
            ("P2_W", lambda r: r.get("U2ph"), "I2", "pf2"),
        ],
    }
    for i, r in enumerate(rows):
        for pkey in ("pf", "pf1", "pf2"):
            v = _num(r.get(pkey))
            if v is not None and not (0 <= v <= 1):
                out.append(
                    {
                        "code": "pf_range",
                        "row": i,
                        "column": pkey,
                        "message": f"שורה {i + 1}: {pkey} = {v:g} מחוץ ל-[0, 1]",
                    }
                )
        for pkey, ufn, ikey, pfkey in triples.get(kind, []):
            p, u, cur = _num(r.get(pkey)), _num(ufn(r)), _num(r.get(ikey))
            if p is None or u is None or cur is None or u * cur <= 0:
                continue
            s = u * cur
            if abs(p) > 1.05 * s:
                out.append(
                    {
                        "code": "power_exceeds_apparent",
                        "row": i,
                        "column": pkey,
                        "message": f"שורה {i + 1}: {pkey} = {p:.4g} W גדול מ-U·I = {s:.4g} VA — "
                        "בלתי אפשרי פיזיקלית (טעות הקלדה, יחידה, או מתח קווי/פאזי?)",
                    }
                )
            pf = _num(r.get(pfkey)) if pfkey else None
            if pf is not None and abs(pf - p / s) > 0.1:
                out.append(
                    {
                        "code": "pf_inconsistent",
                        "row": i,
                        "column": pfkey,
                        "message": f"שורה {i + 1}: cos φ = {pf:g} אבל P/(U·I) = {p / s:.3f} "
                        "(U פאזי). "
                        "ייתכן שנרשם מתח פאזי במקום קווי או להפך",
                    }
                )
        if kind == "short_circuit":
            i1, i2 = _num(r.get("I1k")), _num(r.get("I2k"))
            if i1 and i2:
                expected = (
                    spec.turns_ratio if spec.nameplate.secondary == spec.nameplate.primary else None
                )
                if expected and abs(i2 / i1 - expected) > 0.15 * expected:
                    out.append(
                        {
                            "code": "current_ratio",
                            "row": i,
                            "message": f"שורה {i + 1}: I2k/I1k = {i2 / i1:.3f}, "
                            f"צפוי ≈ {expected:.3f}",
                        }
                    )
    return out
