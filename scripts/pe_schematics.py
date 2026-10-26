"""Schematics of the power-electronics bench (frontend/public/pe/*.svg), drawn with Schemdraw
(MIT, https://github.com/cdelker/schemdraw).

Why static drawings: the bench's circuits are fixed topologies with parameters, so a drawing
per topology, generated from code and checked by eye once, is clearer than the editable
schematic of the machine experiments. The node names in the drawings (p, m, a, b, c, out, sw)
are the node names of the netlists in frontend/src/powerelec/circuits.ts, so the student can
read the netlist against the picture.

Run from the repository root:  .venv/bin/python scripts/pe_schematics.py [--png]
"""

from __future__ import annotations

import sys
from pathlib import Path

import schemdraw
import schemdraw.elements as elm

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "pe"
FONT = 13


def _save(d: schemdraw.Drawing, name: str, png: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d.save(str(OUT / f"{name}.svg"))
    if png:
        d.save(f"/tmp/pe-{name}.png", dpi=150)


def b2(png: bool) -> None:
    """Single-phase bridge. The source sits inside the bridge, between the two leg midpoints,
    so the drawing is planar (no crossings)."""
    with schemdraw.Drawing(show=False, fontsize=FONT, unit=2.6) as d:
        # left leg: T1 (s1 → p) above, T4 (m → s1) below
        top_l = elm.Dot().label("p", loc="left")
        elm.SCR().down().reverse().label("T1 / D1", loc="bottom")
        s1 = elm.Dot().label("s1", loc="left", ofst=(-0.1, 0))
        elm.SCR().down().reverse().label("T4 / D4", loc="bottom")
        bot_l = elm.Dot().label("m", loc="left")
        # right leg, 5 units to the right: T3 (0 → p) above, T2 (m → 0) below
        elm.Line().at(top_l.center).right().length(5)
        top_r = elm.Dot()
        elm.SCR().down().reverse().label("T3 / D3", loc="top")
        s2 = elm.Dot().label("0", loc="right")
        elm.SCR().down().reverse().label("T2 / D2", loc="top")
        bot_r = elm.Dot()
        elm.Line().at(bot_l.center).to(bot_r.center)
        # the source between the midpoints
        elm.Line().at(s1.center).right().length(1.2)
        elm.SourceSin().right().length(2.6).label("$v_s$", loc="top")
        elm.Line().right().to(s2.center)
        # load on the right of the rails: R, L, current probe
        elm.Line().at(top_r.center).right().length(2.5)
        r = elm.Resistor().down().label("R", loc="bottom")
        elm.CurrentLabel(top=False, length=1.0).at(r).label("$i_d$")
        elm.Inductor2().down().label("L", loc="bottom")
        elm.Line().left().to(bot_r.center)
    _save(d, "b2", png)


def b6(png: bool) -> None:
    """Three-phase bridge. Each phase rises from its source below the bridge beside its leg and
    turns into the leg midpoint; it crosses only the m rail (no dot = not connected)."""
    with schemdraw.Drawing(show=False, fontsize=FONT, unit=2.4) as d:
        x0, gap, y_top, y_bot = 3.0, 3.6, 2.4, -2.4
        legs = []
        for k, (up, lo) in enumerate((("T1", "T4"), ("T3", "T6"), ("T5", "T2"))):
            x = x0 + gap * k
            top = elm.Dot().at((x, y_top))
            elm.SCR().down().reverse().label(up, loc="bottom")
            mid = elm.Dot()
            elm.SCR().down().reverse().label(lo, loc="bottom")
            bot = elm.Dot().at((x, y_bot))
            legs.append((top, mid, bot))
        elm.Line().at((legs[0][0].center[0] - 1.6, y_top)).to(legs[2][0].center)
        elm.Line().at((legs[0][2].center[0] - 1.6, y_bot)).to(legs[2][2].center)
        elm.Label().at((legs[0][0].center[0] - 1.9, y_top)).label("p")
        elm.Label().at((legs[0][2].center[0] - 1.9, y_bot)).label("m")
        for k, name in enumerate("abc"):
            mid = legs[k][1].center
            xs = mid[0] - 1.6
            src = elm.SourceSin().up().at((xs, -7.6)).length(1.9).label(f"$v_{name}$", loc="bottom", fontsize=11)
            elm.Inductor2(loops=2).up().length(1.5).label("$L_s$", loc="bottom", fontsize=11)
            elm.Line().up().to((xs, mid[1]))
            elm.Line().right().to(mid)
            elm.Label().at((xs + 0.35, mid[1] + 0.3)).label(name)
            _ = src
        # star point of the source
        elm.Line().at((legs[0][1].center[0] - 1.6, -7.6)).to((legs[2][1].center[0] - 1.6, -7.6))
        elm.Dot().at((legs[1][1].center[0] - 1.6, -7.6))
        elm.Label().at((legs[2][1].center[0] - 1.2, -7.6)).label("N")
        # load
        top_r = legs[2][0].center
        elm.Line().at(top_r).right().length(2.4)
        elm.Resistor().down().length(2.4).label("R", loc="bottom")
        elm.Inductor2().down().length(2.4).label("L", loc="bottom")
        elm.Line().left().to(legs[2][2].center)
    _save(d, "b6", png)


def buck(png: bool) -> None:
    with schemdraw.Drawing(show=False, fontsize=FONT, unit=2.6) as d:
        vin = elm.SourceV().up().label("$V_{in}$", loc="bottom")
        elm.Line().right().length(1)
        elm.Switch(action="close").right().label("S (D, $f_s$)", loc="top")
        sw = elm.Dot().label("sw", loc="top")
        elm.Inductor2().right().label("L", loc="top")
        out = elm.Dot().label("out", loc="top")
        elm.Line().right().length(1.5)
        elm.Resistor().down().label("R", loc="bottom")
        elm.Line().left().length(1.5)
        g_out = elm.Dot()
        elm.Capacitor().up().at(g_out.center).to(out.center).label("C", loc="top")
        elm.Line().left().at(g_out.center).to((sw.center[0], g_out.center[1]))
        g_sw = elm.Dot()
        elm.Diode().up().at(g_sw.center).to(sw.center).label("D", loc="bottom")
        elm.Line().left().at(g_sw.center).to(vin.start)
        elm.Ground().at(vin.start)
    _save(d, "buck", png)


def boost(png: bool) -> None:
    with schemdraw.Drawing(show=False, fontsize=FONT, unit=2.6) as d:
        vin = elm.SourceV().up().label("$V_{in}$", loc="bottom")
        elm.Line().right().length(1)
        elm.Inductor2().right().label("L", loc="top")
        sw = elm.Dot().label("sw", loc="top")
        elm.Diode().right().label("D", loc="top")
        out = elm.Dot().label("out", loc="top")
        elm.Line().right().length(1.5)
        elm.Resistor().down().label("R", loc="bottom")
        elm.Line().left().length(1.5)
        g_out = elm.Dot()
        elm.Capacitor().up().at(g_out.center).to(out.center).label("C", loc="top")
        elm.Line().left().at(g_out.center).to((sw.center[0], g_out.center[1]))
        g_sw = elm.Dot()
        elm.Switch(action="close").up().at(g_sw.center).to(sw.center).label("S (D, $f_s$)", loc="bottom")
        elm.Line().left().at(g_sw.center).to(vin.start)
        elm.Ground().at(vin.start)
    _save(d, "boost", png)


def _sw_diode(d: schemdraw.Drawing, top: tuple[float, float], bottom: tuple[float, float], name: str, left: bool) -> None:
    """A switch with its antiparallel diode, between two points on a vertical line."""
    # the label goes on the side away from the diode
    elm.Switch(action="close").at(top).to(bottom).label(name, loc="bottom" if left else "top")
    dx = -0.9 if left else 0.9
    elm.Line().at(top).to((top[0] + dx, top[1]))
    elm.Dot().at((top[0] + dx, top[1]))
    elm.Diode().at((bottom[0] + dx, bottom[1])).to((top[0] + dx, top[1]))
    elm.Dot().at((bottom[0] + dx, bottom[1]))
    elm.Line().at((bottom[0] + dx, bottom[1])).to(bottom)


def hbridge(png: bool) -> None:
    with schemdraw.Drawing(show=False, fontsize=FONT, unit=2.6) as d:
        xl, xr, yt, ym, yb = 3.0, 9.0, 4.0, 0.0, -4.0
        vdc = elm.SourceV().up().at((0, -2.0)).to((0, 2.0)).label("$V_{dc}$", loc="bottom")
        elm.Line().at((0, 2.0)).to((0, yt))
        elm.Line().at((0, yt)).to((xr, yt))
        elm.Line().at((0, -2.0)).to((0, yb))
        elm.Line().at((0, yb)).to((xr, yb))
        # the antiparallel diodes sit on the outer side of each leg, away from the load
        for x, (u, lo), left in ((xl, ("S1", "S2"), True), (xr, ("S3", "S4"), False)):
            elm.Dot().at((x, yt))
            _sw_diode(d, (x, yt), (x, ym), u, left=left)
            elm.Dot().at((x, ym))
            _sw_diode(d, (x, ym), (x, yb), lo, left=left)
            elm.Dot().at((x, yb))
        elm.Label().at((xl - 0.35, ym + 0.35)).label("a")
        elm.Label().at((xr + 0.35, ym + 0.35)).label("b")
        elm.Line().at((xl, ym)).to((xl + 1.0, ym))
        elm.Resistor().right().length(2.0).label("R", loc="top")
        elm.Inductor2().right().length(2.0).label("L", loc="top")
        elm.Line().to((xr, ym))
        elm.Label().at((0.4 * (xl + xr) + 1.2, ym - 0.8)).label("$v_{ab}$, $i_o$")
        _ = vdc
    _save(d, "hbridge", png)


if __name__ == "__main__":
    png = "--png" in sys.argv
    for f in (b2, b6, buck, boost, hbridge):
        f(png)
    print("written:", sorted(p.name for p in OUT.glob("*.svg")))
