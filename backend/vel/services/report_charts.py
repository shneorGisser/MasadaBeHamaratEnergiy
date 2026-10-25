"""Charts for the Word report: each curve of a section, drawn from the report's own tables
(simulation as lines, measurements as markers) — the same data as the HTML report and the
MATLAB appendix, nothing recomputed.

matplotlib (Agg, no display) with DejaVu Sans, which has Hebrew glyphs. matplotlib lays text
out left to right, so Hebrew runs are put into visual order here (the same approach as the
DXF export); mixed runs of Latin, digits and units keep their own order."""

from __future__ import annotations

import io
import re
from typing import Any

SIM = "#1f6fb2"
MEAS = "#a2462e"
EXTRA = ("#b07a1f", "#4b6b2f")
GROUPS = ("#1f6fb2", "#b07a1f", "#4b6b2f", "#7a3e8f", "#a2462e", "#2f7f7a")
_HEB = re.compile(r"[\u0590-\u05FF]")
RLM = "\u200f"


def visual(s: str) -> str:
    """Hebrew labels: matplotlib ≥ 3.11 lays text out with the Unicode bidi algorithm, which
    takes the paragraph direction from the first strong character — so a label that starts
    with a Latin symbol ("i קו L1 [A]") would be laid out left to right. A leading RIGHT-TO-LEFT
    MARK makes every Hebrew label a right-to-left paragraph; nothing else is reordered here."""
    return RLM + s if _HEB.search(s) else s


def _label(cols: list[dict[str, Any]], key: str) -> str:
    c = next((c for c in cols if c["key"] == key), None)
    if not c:
        return key
    return str(c["label_he"]) + (f" [{c['unit']}]" if c.get("unit") else "")


def _xy(rows: list[dict[str, Any]], xk: str, yk: str) -> tuple[list[float], list[float]]:
    pts = [
        (float(r[xk]), float(r[yk]))
        for r in rows
        if isinstance(r.get(xk), (int, float)) and isinstance(r.get(yk), (int, float))
    ]
    pts.sort()
    return [p[0] for p in pts], [p[1] for p in pts]


def render_curve(
    curve: dict[str, Any], table: dict[str, Any], measured: list[dict[str, Any]] | None = None
) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "DejaVu Sans"
    cols = table["columns"]
    rows = table["rows"]
    xk, yk = curve["x"], curve["y"]
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=150)
    try:
        group = curve.get("group")
        if group:
            keys: list[Any] = []
            for r in rows:
                if r.get(group) not in keys:
                    keys.append(r.get(group))
            for i, k in enumerate(keys):
                x, y = _xy([r for r in rows if r.get(group) == k], xk, yk)
                name = f"{_label(cols, group).split(' [')[0]} = {k}"
                ax.plot(x, y, "-o", ms=2.5, lw=1.4, color=GROUPS[i % 6], label=visual(name))
        else:
            x, y = _xy(rows, xk, yk)
            many = len(x) > 200
            name = _label(cols, yk).split(" [")[0]
            style = "-" if many else "-o"
            ax.plot(x, y, style, ms=2.5, lw=1.2, color=SIM, label=visual(name))
        for i, extra in enumerate((curve.get("y2"), curve.get("y3"))):
            if extra:
                x, y = _xy(rows, xk, extra)
                # one extra series = a reference (dashed); two = three phases (solid)
                ls = "--" if not curve.get("y3") else "-"
                name = _label(cols, extra).split(" [")[0]
                ax.plot(x, y, ls, lw=1.2, color=EXTRA[i], label=visual(name))
        if measured:
            x, y = _xy(measured, xk, yk)
            if x:
                ax.plot(x, y, "s", ms=5, color=MEAS, label=visual("מדידה"))
        if curve.get("log"):
            ax.set_xscale("log")
            ax.set_yscale("log")
        ax.set_title(visual(curve.get("title_he", "")), fontsize=10)
        ax.set_xlabel(visual(_label(cols, xk)), fontsize=9)
        ylab = _label(cols, yk)
        if curve.get("y3"):  # three traces of one quantity: name them all, one unit
            names = [_label(cols, k).split(" [")[0] for k in (yk, curve["y2"], curve["y3"])]
            unit = ylab[len(ylab.split(" [")[0]) :]
            ylab = ", ".join(names) + unit
        ax.set_ylabel(visual(ylab), fontsize=9)
        ax.grid(True, which="both", lw=0.4, alpha=0.5)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=7.5, loc="best")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)


LONG_TABLE = 60  # longer tables (time traces) are printed folded; the chart carries them
FOLDED = 15


def section_charts(sec: dict[str, Any]) -> list[tuple[str, bytes | None, str]]:
    """(title, png or None, error) for every curve of a report section's run, measured points
    overlaid — shared by the HTML/PDF and the Word report."""
    res = (sec.get("run") or {}).get("result") or {}
    tables = {t.get("id"): t for t in res.get("tables", [])}
    measured = (sec.get("measurements") or {}).get("rows")
    out: list[tuple[str, bytes | None, str]] = []
    for curve in res.get("curves", []):
        tb = tables.get(curve.get("table")) if curve.get("table") else None
        tb = tb or (res.get("tables") or [None])[0]
        if not tb:
            continue
        try:
            out.append((curve.get("title_he", ""), render_curve(curve, tb, measured), ""))
        except Exception as exc:  # noqa: BLE001 — a missing chart is reported, not fatal
            out.append((curve.get("title_he", ""), None, str(exc)))
    return out
