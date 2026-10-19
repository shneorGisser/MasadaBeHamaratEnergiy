"""R8 — cross-validation of the phasor solver against ngspice (independent MNA implementation).

Observed agreement: ≤ 1e-8 relative on every reading; the residual comes from the 1e13 Ω
`rshunt` that SPICE needs to give galvanically isolated secondaries a DC path.

The CircuitModel is translated to a SPICE netlist by the code below (separate from
vel.engine.netlist), solved with `ngspice -b` AC analysis at 50 Hz, and every instrument
reading is compared. Only linear cases (sat_c = 0): SPICE AC analysis cannot represent the
amplitude-dependent magnetizing reactance.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.helpers import CB, spec, yy_with_load
from vel.engine.circuit import CircuitModel
from vel.engine.simulate import operating_point
from vel.experiments.transformer3ph.spec import TransformerSpec

pytestmark = pytest.mark.ngspice
NGSPICE = shutil.which("ngspice")
if NGSPICE is None:
    pytest.skip("ngspice not installed — cross-validation NOT executed", allow_module_level=True)

F = 50.0
W = 2 * math.pi * F


def to_spice(c: CircuitModel, s: TransformerSpec) -> tuple[str, dict[str, Any]]:
    parent: dict[str, str] = {}

    def find(k: str) -> str:
        parent.setdefault(k, k)
        while parent[k] != k:
            k = parent[k]
        return k

    for w in c.wires:
        ra, rb = find(w.a.key()), find(w.b.key())
        if ra != rb:
            parent[rb] = ra
    for comp in c.components:
        if comp.type == "switch3" and comp.params.get("closed", True):
            for k in (1, 2, 3):
                ra, rb = find(f"{comp.id}.i{k}"), find(f"{comp.id}.o{k}")
                if ra != rb:
                    parent[rb] = ra
    gnd: str | None = None
    for comp in c.components:
        if comp.type == "source3":
            gnd = find(f"{comp.id}.N")
    names: dict[str, str] = {}

    def n(cid: str, t: str) -> str:
        r = find(f"{cid}.{t}")
        if r == gnd:
            return "0"
        return names.setdefault(r, f"n{len(names) + 1}")

    lines = ["* crossval", ".options rshunt=1e13"]
    probes: dict[str, Any] = {}
    e = s.ecm
    k = s.turns_ratio
    for comp in c.components:
        cid, p = comp.id, comp.params
        if comp.type == "source3":
            uph = float(p["U_line"]) / math.sqrt(3)
            for t, ang in (("L1", 0), ("L2", -120), ("L3", 120)):
                lines.append(f"V{cid}{t} {n(cid, t)} {n(cid, 'N')} AC {uph} {ang}")
        elif comp.type == "transformer3":
            for P, sl in (("A", "a"), ("B", "b"), ("C", "c")):
                p1, p2, s1, s2 = (
                    n(cid, f"{P}1"),
                    n(cid, f"{P}2"),
                    n(cid, f"{sl}1"),
                    n(cid, f"{sl}2"),
                )
                m, e1, e2, mm, sx = (f"{cid}{P}{x}" for x in ("m", "e1", "e2", "mm", "sx"))
                lines += [
                    f"R1{cid}{P} {p1} {m} {e.R1}",
                    f"L1{cid}{P} {m} {e1} {e.X1 / W}",
                    f"RFE{cid}{P} {e1} {p2} {e.R_fe}",
                    f"LM{cid}{P} {e1} {p2} {e.Xm_unsat / W}",
                    # ideal transformer: V(e2,s2) = V(e1,p2)/k ; I_primary = I_secondary / k
                    f"E{cid}{P} {e2} {sx} {e1} {p2} {1 / k}",
                    f"VS{cid}{P} {sx} {s2} 0",
                    f"F{cid}{P} {e1} {p2} VS{cid}{P} {-1 / k}",
                    f"R2{cid}{P} {e2} {mm} {e.R2}",
                    f"L2{cid}{P} {mm} {s1} {e.X2 / W}",
                ]
        elif comp.type == "load3":
            kind, conn, val = p["kind"], p.get("connection", "Y"), float(p["value"])
            el = {"R": "R", "L": "L", "C": "C"}[kind]
            if conn == "Y":
                star = f"{cid}star"
                for t in ("1", "2", "3"):
                    lines.append(f"{el}{cid}{t} {n(cid, t)} {star} {val}")
            else:
                for a, b in (("1", "2"), ("2", "3"), ("3", "1")):
                    lines.append(f"{el}{cid}{a}{b} {n(cid, a)} {n(cid, b)} {val}")
        elif comp.type == "ammeter":
            lines.append(f"VAM{cid} {n(cid, 'p')} {n(cid, 'n')} 0")
            probes[cid] = ("I", f"VAM{cid}")
        elif comp.type == "voltmeter":
            probes[cid] = ("U", n(cid, "p"), n(cid, "n"))
        elif comp.type == "wattmeter":
            lines.append(f"VWM{cid} {n(cid, 'Ip')} {n(cid, 'In')} 0")
            probes[cid] = ("P", f"VWM{cid}", n(cid, "Vp"), n(cid, "Vn"))
    return "\n".join(lines), probes


def run_spice(netlist: str, probes: dict[str, Any], tmp: Path) -> dict[str, dict[str, float]]:
    exprs: list[tuple[str, str, str]] = []
    for cid, pr in probes.items():
        if pr[0] == "I":
            exprs.append((cid, "I", f"i({pr[1]})"))
        elif pr[0] == "U":
            a, b = pr[1], pr[2]
            exprs.append((cid, "U", f"v({a})-v({b})" if b != "0" else f"v({a})"))
        else:
            a, b = pr[2], pr[3]
            exprs.append((cid, "Pi", f"i({pr[1]})"))
            exprs.append((cid, "Pv", f"v({a})-v({b})" if b != "0" else f"v({a})"))
    ctrl = ["set numdgt=15", "ac lin 1 50 50"]
    for idx, (_, _, ex) in enumerate(exprs):
        ctrl.append(f"let r{idx} = real({ex})")
        ctrl.append(f"let i{idx} = imag({ex})")
        ctrl.append(f"print r{idx} i{idx}")
    deck = netlist + "\n.control\n" + "\n".join(ctrl) + "\nquit\n.endc\n.end\n"
    f = tmp / "deck.cir"
    f.write_text(deck)
    out = subprocess.run(
        [NGSPICE or "ngspice", "-b", str(f)], capture_output=True, text=True, timeout=60
    )
    parts: dict[tuple[str, int], float] = {}
    for line in out.stdout.splitlines():
        m = re.match(r"([ri])(\d+) = ([-+0-9.eE]+)$", line.strip())
        if m:
            parts[(m.group(1), int(m.group(2)))] = float(m.group(3))
    vals = {
        i: complex(parts[("r", i)], parts[("i", i)])
        for i in range(len(exprs))
        if ("r", i) in parts and ("i", i) in parts
    }
    assert len(vals) == len(exprs), out.stdout + out.stderr
    res: dict[str, dict[str, float]] = {}
    cache: dict[tuple[str, str], complex] = {}
    for idx, (cid, q, _) in enumerate(exprs):
        cache[(cid, q)] = vals[idx]
    for cid, pr in probes.items():
        if pr[0] == "I":
            res[cid] = {"I": abs(cache[(cid, "I")])}
        elif pr[0] == "U":
            res[cid] = {"U": abs(cache[(cid, "U")])}
        else:
            i, v = cache[(cid, "Pi")], cache[(cid, "Pv")]
            # SPICE current through a V source flows + → − inside the source (into the + node)
            s_ = v * i.conjugate()
            res[cid] = {"P": s_.real, "U": abs(v), "I": abs(i)}
    return res


def _with_load(b: CB, kind: str, conn: str, val: float) -> CB:
    b.add("L", "load3", kind=kind, connection=conn, value=val)
    b.wire("T.a1", "A2m.p").wire("A2m.n", "L.1").wire("T.b1", "L.2").wire("T.c1", "L.3")
    return b


CASES = [
    ("Yy no-load", lambda: yy_with_load(None)),
    ("Yy R-load", lambda: yy_with_load(18.0)),
    ("Yd L-load delta", lambda: _with_load(yy_with_load(None, secondary_conn="D"), "L", "D", 0.08)),
    ("Yy C-load star", lambda: _with_load(yy_with_load(None), "C", "Y", 80e-6)),
    (
        "Yd R-load star 300V",
        lambda: _with_load(yy_with_load(None, U=300, secondary_conn="D"), "R", "Y", 9.0),
    ),
]


@pytest.mark.parametrize("name,make", CASES, ids=[c[0] for c in CASES])
def test_R8_matches_ngspice(name: str, make: Any, tmp_path: Path) -> None:
    s = spec(sat_c=0.0, Xm_unsat=650.0)
    model = make().model()
    ours = operating_point(model, s)
    deck, probes = to_spice(model, s)
    theirs = run_spice(deck, probes, tmp_path)
    compared = 0
    for cid, q in theirs.items():
        for key, val in q.items():
            mine = ours.readings[cid][key]
            assert mine is not None, (cid, key)
            assert mine == pytest.approx(val, rel=1e-8, abs=1e-9), (name, cid, key, mine, val)
            compared += 1
    assert compared >= 6
