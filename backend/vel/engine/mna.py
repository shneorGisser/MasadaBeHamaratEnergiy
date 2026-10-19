"""Complex Modified Nodal Analysis for sinusoidal steady state at one frequency.

Unknowns: node phasor voltages V_k, plus one current per voltage-type branch (voltage
sources, zero-volt ammeter branches, ideal-transformer primaries, and potential pins).

Sign conventions
  * KCL rows: sum of currents LEAVING the node through branches = 0.
  * VSource(a, b, v): V_a - V_b = v; its current unknown i flows from a, through the source,
    to b (so it leaves node a: +i in row a, -i in row b).
  * IdealTransformer(p1, p2, s1, s2, k): V_p1 - V_p2 = k (V_s1 - V_s2), k = n1/n2.
    Primary current i enters at p1 (row p1: +i, row p2: -i); the secondary winding then
    carries -k·i from s1 to s2 (row s1: -k·i, row s2: +k·i), i.e. k·i flows OUT of the dotted
    secondary terminal into the external circuit. Complex power is conserved exactly.
  * Pin(n): V_n = 0 (reference for one galvanically isolated group).

This module knows nothing about components or instruments; see netlist.py.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

CArray = npt.NDArray[np.complex128]

COND_LIMIT = 1e13


class SingularCircuitError(Exception):
    """The MNA matrix is singular: the circuit has no unique solution."""


class ConvergenceError(Exception):
    def __init__(self, message: str, iterations: int, residual: float) -> None:
        super().__init__(message)
        self.iterations = iterations
        self.residual = residual


@dataclass
class Admittance:
    a: int
    b: int
    y: complex
    name: str = ""


@dataclass
class NonlinearShunt:
    """Admittance that depends on the RMS magnitude of the voltage across it."""

    a: int
    b: int
    y_of_vmag: Callable[[float], complex]
    name: str = ""


@dataclass
class VSource:
    a: int
    b: int
    v: complex
    name: str


@dataclass
class IdealTransformer:
    p1: int
    p2: int
    s1: int
    s2: int
    k: float
    name: str


@dataclass
class Pin:
    node: int
    name: str


@dataclass
class Network:
    n_nodes: int
    admittances: list[Admittance] = field(default_factory=list)
    nonlinear: list[NonlinearShunt] = field(default_factory=list)
    vsources: list[VSource] = field(default_factory=list)
    transformers: list[IdealTransformer] = field(default_factory=list)
    pins: list[Pin] = field(default_factory=list)


@dataclass
class Solution:
    v: CArray  # node voltages
    branch_i: dict[str, complex]  # currents of voltage-type branches by name
    iterations: int
    cond: float

    def vdiff(self, a: int, b: int) -> complex:
        return complex(self.v[a] - self.v[b])


def _assemble(net: Network, ys_nl: list[complex]) -> tuple[CArray, CArray, list[str]]:
    n = net.n_nodes
    branch_names = (
        [s.name for s in net.vsources]
        + [t.name for t in net.transformers]
        + [p.name for p in net.pins]
    )
    m = len(branch_names)
    size = n + m
    A = np.zeros((size, size), dtype=np.complex128)
    z = np.zeros(size, dtype=np.complex128)

    def stamp_y(a: int, b: int, y: complex) -> None:
        A[a, a] += y
        A[b, b] += y
        A[a, b] -= y
        A[b, a] -= y

    for adm in net.admittances:
        stamp_y(adm.a, adm.b, adm.y)
    for nl, y in zip(net.nonlinear, ys_nl, strict=True):
        stamp_y(nl.a, nl.b, y)

    row = n
    for s in net.vsources:
        A[s.a, row] += 1
        A[s.b, row] -= 1
        A[row, s.a] += 1
        A[row, s.b] -= 1
        z[row] = s.v
        row += 1
    for t in net.transformers:
        A[t.p1, row] += 1
        A[t.p2, row] -= 1
        A[t.s1, row] -= t.k
        A[t.s2, row] += t.k
        A[row, t.p1] += 1
        A[row, t.p2] -= 1
        A[row, t.s1] -= t.k
        A[row, t.s2] += t.k
        row += 1
    for p in net.pins:
        A[p.node, row] += 1
        A[row, p.node] += 1
        row += 1
    return A, z, branch_names


def _linear_solve(A: CArray, z: CArray) -> tuple[CArray, float]:
    if A.shape[0] == 0:
        return np.zeros(0, dtype=np.complex128), 1.0
    cond = float(np.linalg.cond(A))
    if not np.isfinite(cond) or cond > COND_LIMIT:
        raise SingularCircuitError(f"MNA matrix is singular or ill-conditioned (cond={cond:.3g})")
    x = np.linalg.solve(A, z)
    return x.astype(np.complex128), cond


def solve(
    net: Network,
    *,
    tol: float = 1e-11,
    max_iter: int = 300,
) -> Solution:
    """Solve the network; nonlinear shunts are handled by damped fixed-point iteration on |V|.

    Each iteration solves the linear network with every nonlinear admittance frozen at its
    value for the previous |V| estimate. Convergence: max relative change of |V| over all
    nonlinear shunts < tol.
    """
    vmag = [0.0 for _ in net.nonlinear]
    ys = [nl.y_of_vmag(0.0) for nl in net.nonlinear]
    damping = 1.0
    last_change = float("inf")
    iterations = 0
    while True:
        A, z, names = _assemble(net, ys)
        x, cond = _linear_solve(A, z)
        iterations += 1
        v = x[: net.n_nodes]
        if not net.nonlinear:
            break
        new_vmag = [abs(complex(v[nl.a] - v[nl.b])) for nl in net.nonlinear]
        change = max(abs(nv - ov) / max(nv, 1e-12) for nv, ov in zip(new_vmag, vmag, strict=True))
        if change < tol:
            break
        if iterations >= max_iter:
            raise ConvergenceError(
                f"nonlinear iteration did not converge in {max_iter} iterations",
                iterations,
                change,
            )
        if change > last_change and damping > 1 / 64:
            damping /= 2
        last_change = change
        vmag = [ov + damping * (nv - ov) for nv, ov in zip(new_vmag, vmag, strict=True)]
        ys = [nl.y_of_vmag(m) for nl, m in zip(net.nonlinear, vmag, strict=True)]

    branch_i = {name: complex(x[net.n_nodes + i]) for i, name in enumerate(names)}
    return Solution(v=v.copy(), branch_i=branch_i, iterations=iterations, cond=cond)
