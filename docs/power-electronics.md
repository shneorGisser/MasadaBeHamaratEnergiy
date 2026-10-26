# Power-electronics bench (`/power-electronics`)

The lab's Appli-com racks hold rectifiers, choppers and inverters, but the machine experiments
never used them. The bench simulates them.

## Why ngspice in the browser, and not our MNA

Our solver works with phasors and saturation. A converter switches, so it needs a time-domain
SPICE with diodes and switches.

**eecircuit-engine** (MIT, ngspice compiled to WebAssembly) runs in a Web Worker:
* No server and no backend dependency.
* The ~20 MB engine is loaded only when the bench is first used.
* The UI does not freeze while it runs.

## Topologies

The theory for each is in `frontend/src/powerelec/circuits.ts`.

| Topology | Rack modules | Theory checked |
|---|---|---|
| B2 / B2C | 1 phase of 3×45-0-45 V, SCR/diode half bridges, 100 Ω, 50 mH | 0.9·V_s·cos α (continuous), (√2·V_s/π)(1 + cos α) (R load) |
| B6 / B6C | 3×45-0-45 V, SCR half bridges, six-pulse controller | 1.35·V_LL·cos α − 3ωL_s·I_d/π; 1.35·V_LL·[1 + cos(α+60°)] for an R load with α > 60°; ripple; THD 31.1 %; λ = 0.955·cos α (both indicative) |
| Buck | Buck switching power supply | D·V_in (CCM), DCM formula, ΔI_L, ΔV_o |
| Boost | Boost switching power supply | V_in/(1−D) (CCM), DCM formula, ΔI_L, ΔV_o |
| Full bridge, sine PWM | IGBT single-phase bridge, PWM controller | V₁ = m·V_dc/√2, I₁ = V₁/\|Z\|, RMS = V_dc |

## Models (stated on the page)

* **Ideal:** a diode with ≈ 0.04 V forward drop, and a switch with R_on = 1 mΩ. This is what the
  formulas assume. It is the mode the automatic theory checks run in.
* **Real:** a silicon diode (≈ 0.8–1 V at 1 A), and a switch with R_on = 50 mΩ.
* **Snubbers.** Every rectifier diode and thyristor has an R-C snubber (100 Ω, 0.1 µF), as drawn on
  the rack's modules. Without it, turn-off with source inductance cannot be integrated.
* **Thyristors.** A thyristor is a gated switch in series with a diode, fired with "long pulses".
  The pulse lasts 150° in B6, which is 30° beyond its 120° of conduction, so the outgoing device
  keeps its gate through the commutation overlap. Latching and holding current are not modelled.
* **Failures.** A run that stops early ("timestep too small") is reported as a failure, with the
  time it reached. It is never shown as a short result.

## Checks

* `src/powerelec/bench.test.ts` (Vitest, Node) runs 11 cases of the ideal models against the
  theory within each check's tolerance. Tolerances are 3 % for averages and 5–15 % for ripple.
* The B6 case with L_s = 5 mH checks the commutation-overlap drop.
* The real models must lower the output, by less than 25 %.
* B6 with a large L gives a line-current THD between 28 % and 32 % (theory: 31.1 %).
* E2E `P2` runs the bench in a real browser: B6C at α = 30° gives 91.1 V against the theoretical
  91.2 V. Buck then runs in the same worker.

## Schematics

`scripts/pe_schematics.py` draws them with **Schemdraw** (MIT) into `frontend/public/pe/*.svg`.
The node names in the drawings match the netlist, which the page shows and which runs unchanged
in LTspice or ngspice. In B6 the phase wires cross the m rail. This is unavoidable for a bridge
fed from outside, and a crossing without a dot is not a connection.
