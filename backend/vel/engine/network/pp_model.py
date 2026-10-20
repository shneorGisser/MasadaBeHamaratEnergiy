"""pandapower model of the lab feeder: the general engine (BSD-3-Clause, pandapower.org).

The same data as `direct.py`, handed to pandapower: ext_grid → trafo (Dyn) → two lines →
loads. Short circuit: maximum case with lv_tol_percent = 10 (c_max = 1.10); minimum case with
lv_tol_percent = 6, the setting whose c_min (0.95) is the IEC 60909-0:2016 value — pandapower
pairs +10 % with c_min = 0.90. Line end temperature 80 °C for the minimum currents, transformer
correction K_T (pandapower: maximum case only), κ by method C."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any

from vel.experiments.network.spec import BUSES, NetworkSpec


def build(spec: NetworkSpec) -> Any:
    import pandapower as pp

    g, t = spec.grid, spec.trafo
    net = pp.create_empty_network(f_hz=g.f)
    b = [
        pp.create_bus(net, g.U_n_kV, name="B0"),
        pp.create_bus(net, t.U2_V / 1e3, name="B1"),
        pp.create_bus(net, t.U2_V / 1e3, name="B2"),
        pp.create_bus(net, t.U2_V / 1e3, name="B3"),
    ]
    pp.create_ext_grid(
        net,
        b[0],
        vm_pu=1.0,
        s_sc_max_mva=g.Sk_max_MVA,
        s_sc_min_mva=g.Sk_min_MVA,
        rx_max=g.RX,
        rx_min=g.RX,
        x0x_max=1.0,
        x0x_min=1.0,
        r0x0_max=g.RX,
        r0x0_min=g.RX,
    )
    pp.create_transformer_from_parameters(
        net,
        b[0],
        b[1],
        sn_mva=t.S_n_kVA / 1e3,
        vn_hv_kv=t.U1_kV,
        vn_lv_kv=t.U2_V / 1e3,
        vk_percent=t.uk,
        vkr_percent=t.ur,
        pfe_kw=t.P_0_kW,
        i0_percent=t.i0,
        vector_group="Dyn",
        vk0_percent=t.uk,
        vkr0_percent=t.ur,
        mag0_percent=100.0,
        mag0_rx=0.0,
        si0_hv_partial=0.9,
        name="T",
    )
    for k, (fb, tb, c) in enumerate(((b[1], b[2], spec.cable1), (b[2], b[3], spec.cable2))):
        pp.create_line_from_parameters(
            net,
            fb,
            tb,
            c.L_m / 1000,
            r_ohm_per_km=c.r,
            x_ohm_per_km=c.x,
            c_nf_per_km=0.0,
            max_i_ka=c.I_max / 1000,
            r0_ohm_per_km=c.r * c.r0_r,
            x0_ohm_per_km=c.x * c.x0_x,
            c0_nf_per_km=0.0,
            endtemp_degree=80.0,
            name=f"C{k + 1}",
        )
    lo = spec.loads
    for bus, p, pf in ((b[2], lo.P2_kW, lo.pf2), (b[3], lo.P3_kW, lo.pf3)):
        pp.create_load(net, bus, p_mw=p / 1e3, q_mvar=p / 1e3 * math.tan(math.acos(pf)))
    return net


@dataclass
class PpLoadFlow:
    U: dict[str, complex]
    I_branch: dict[str, float]
    loading: dict[str, float]
    P_loss_kW: float


def load_flow(spec: NetworkSpec) -> PpLoadFlow:
    import pandapower as pp

    net = build(spec)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pp.runpp(net, numba=False, tolerance_mva=1e-12, max_iteration=50)
    rb = net.res_bus
    u = {
        name: complex(
            rb.vm_pu[i] * math.cos(math.radians(rb.va_degree[i])),
            rb.vm_pu[i] * math.sin(math.radians(rb.va_degree[i])),
        )
        for i, name in enumerate(BUSES)
    }
    rl, rt = net.res_line, net.res_trafo
    return PpLoadFlow(
        U=u,
        I_branch={
            "T": float(rt.i_lv_ka[0]) * 1e3,
            "C1": float(rl.i_ka[0]) * 1e3,
            "C2": float(rl.i_ka[1]) * 1e3,
        },
        loading={
            "T": float(rt.loading_percent[0]),
            "C1": float(rl.loading_percent[0]),
            "C2": float(rl.loading_percent[1]),
        },
        P_loss_kW=float(rl.pl_mw.sum() + rt.pl_mw.sum()) * 1e3,
    )


@dataclass
class PpShortCircuit:
    Ik3: dict[str, float]
    ip: dict[str, float]
    Ith: dict[str, float]
    Ik1: dict[str, float]


def short_circuit(spec: NetworkSpec, case: str, tk: float = 1.0) -> PpShortCircuit:
    import pandapower.shortcircuit as sc

    net = build(spec)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tol = 10 if case == "max" else 6
        sc.calc_sc(net, case=case, fault="3ph", ip=True, ith=True, tk_s=tk, lv_tol_percent=tol)
        r3 = net.res_bus_sc.copy()
        sc.calc_sc(net, case=case, fault="1ph", lv_tol_percent=tol)
        r1 = net.res_bus_sc.copy()
    return PpShortCircuit(
        Ik3={b: float(r3.ikss_ka[i]) for i, b in enumerate(BUSES)},
        ip={b: float(r3.ip_ka[i]) for i, b in enumerate(BUSES)},
        Ith={b: float(r3.ith_ka[i]) for i, b in enumerate(BUSES)},
        Ik1={b: float(r1.ikss_ka[i]) for i, b in enumerate(BUSES)},
    )
