# Engineering model — three-phase transformer (experiment 1)

Model version: `mna-phasor-1.0+xfmr-T-sat-1.0`

## Governing equations
* Sinusoidal steady state at one frequency f; all quantities are RMS phasors.
* Network: complex Modified Nodal Analysis `A·x = z` (`backend/vel/engine/mna.py`), unknowns = node
  voltages + currents of voltage-type branches (sources, ammeters, ideal-transformer primaries, pins).
* Each limb: T-equivalent — `R1 + jX1` → magnetizing branch `R_Fe ∥ jX_m(|E1|)` → ideal transformer
  `k = n1/n2 = U1_winding/U2_winding` → `jX2 + R2`. Reactances are given at f_n and scale with f/f_n.
* Saturation: `X_m(E) = X_m,unsat / (1 + c·(E/E_ref)^n)`, `E_ref = U1_winding·f/f_n` (flux ∝ E/f).
  Solved by damped fixed-point iteration on |E1|, tolerance 1e-11 relative, max 300 iterations.
* Instruments are ideal (zero-impedance ammeters, infinite-impedance voltmeters / voltage coils).
  Wattmeter: `P = Re(V·I*)`, `cos φ = P/|V·I*|`.
* DC study (f = 0): each winding is its resistance only (inductances shorted, no transfer).

## Inputs and units
Nameplate (S_n [VA], U1n/U2n line [V], f_n [Hz], rated connections) and per-winding equivalent
circuit [Ω]. Validation: all values finite and in range; X_m at rated voltage ≥ 5·|R1+jX1|.

## Validity range / out of scope
| Phenomenon | Status |
|---|---|
| No-load, short-circuit, R/L/C load steady state | modelled |
| Vector groups from wiring topology | modelled |
| Saturation of the magnetization curve (fundamental-equivalent RMS) | modelled (parametric) |
| Harmonics of magnetizing current, true-RMS vs average-responding meter readings | **not modelled** |
| Inrush, transients, switching | **not modelled** |
| Magnetic coupling between limbs of a 3-limb core, zero-sequence flux paths, middle-limb asymmetry | **not modelled** (bank model) |
| Temperature dependence of winding resistance | **not modelled** |
| Instrument accuracy class, loading, bandwidth | **not modelled** |
| Insulation test | parameter readout only (no physics) |

## Parameter extraction (identical for simulated and measured data)
Consistent (star-equivalent, P = total three-phase power, U, I = line quantities):
`Y_m = √3·I0/U_L`, `g_m = P0/U_L²`, `b_m = √(Y_m² − g_m²)`;
`Z_k = U_k/(√3·I_k)`, `r_k = P_k/(3·I_k²)`, `x_k = √(Z_k² − r_k²)`.
The lab-manual formulas are also reported verbatim; with line voltage and total power they give
`r_k/Z_k = √3·cos φ_k`, so `x_k` is undefined when `cos φ_k > 0.577` (shown as undefined, never NaN).

## Validation results (see docs/test-log.md)
R1 ideal ratios (≤1e-9), R2 current ratio and power (≤1e-6, bound from the 1e9 Ω magnetizing branch),
R3 energy conservation over 60 random parameter/load sets (≤1e-9), R4 textbook extraction (≤0.5 %),
R5 simulate→extract round trip (≤2 %), R7 capacitive voltage rise, R8 ngspice agreement (≤1e-8),
R9 invalid circuits rejected with explicit statuses.
