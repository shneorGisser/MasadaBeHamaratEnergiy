# Network module — load flow and IEC 60909 short circuit (N1)

The module places the lab in its supply network. It shows where the bench voltage, the voltage
drop and the fault-loop impedance measured in experiment 8 come from.

The module is an extension and is not one of the manual's experiments. **Every value in it is
assumed.** Every run says so with the `assumed_network` warning.

## Topology (fixed, radial)

    MV grid (S''k) ─ T (Dyn) ─ B1 main LV board ─ C1 ─ B2 lab board ─ C2 ─ B3 bench
                                                          load            load

The spec is made of flat sections — grid, transformer, two cables and loads — so it fits the
existing spec form. A general network editor (arbitrary buses, meshed networks) is a later
step.

**Preset `typical_substation`:**

| Element | Value |
|---|---|
| Grid | 22 kV, S''k = 250/150 MVA, R/X = 0.1 |
| Transformer | 630 kVA, uk = 6 %, P_cu = 6.5 kW |
| C1 | 4×150 mm² Al, 80 m |
| C2 | 4×16 mm² Cu, 30 m |
| Loads | 40 kW (pf 0.9) at B2 and 5 kW (pf 0.85) at B3 |

The cable zero-sequence impedance is taken as Z0' = 4·Z1' (assumed).

## Two engines

Every study is solved by two independent engines, and the largest relative difference between
them is reported as `engines_dev`:

* **pandapower** (BSD-3-Clause), the general engine. Its results are the ones shown.
* **Our own solver** (`vel/engine/network/direct.py`). It is about 150 lines that follow the
  textbook equations.

A difference above 1e-6 raises the `engines_disagree` warning. For the preset the difference is
about 1e-13 for the load flow and 1e-16 for the short circuit.

**Load flow.**

* Per unit, with S_base = 1 MVA. The slack bus is B0.
* The transformer is a T model, the same model pandapower uses by default.
* Loads draw constant power.
* The solution is a nodal fixed-point iteration.
* Transformer loading follows pandapower's definition: the larger apparent power of the two
  sides, divided by S_n.

**Short circuit (IEC 60909-0).**

* The equivalent voltage source is c·U_n/√3.
* c factors:
  * LV: c_max = 1.10 (+10 % tolerance) and c_min = 0.95;
  * MV: c_max = 1.10 and c_min = 1.00.
* The transformer correction is K_T = 0.95·c_max/(1 + 0.6·x_T).
* For the minimum currents the cables are taken at 80 °C (factor 1.24).
* Peak current: κ by method C. For a radial feeder this equals the R/X of the fault path.
* Thermal current: I_th = I''k·√(m + n), with n = 1.
* Single-phase-to-earth fault: I''k1 = √3·c·U_n/|2Z1 + Z0|. The Dyn transformer isolates the
  MV zero sequence.
* Loop impedance: Z_loop = |2Z1 + Z0|/3. This is the value a loop tester would show at B2 and
  B3, and it can be compared with experiment 8.

**Where the two engines' conventions differ, and the choice made here:**

* **c_min in LV.** pandapower uses 0.90 with a +10 % tolerance setting. IEC 60909-0:2016
  Table 1 gives 0.95. The minimum case is therefore run in pandapower with
  `lv_tol_percent = 6`, whose c_min is 0.95. c_max does not enter the minimum case.
* **K_T in the minimum case.** pandapower applies K_T only to the maximum case, and our solver
  follows it. Whether the standard also asks for K_T in the minimum case has not been
  verified against the standard's text. It moves I''k,min by about 1 %.

## Studies

* **`load_flow`**
  * Bus voltages, voltage drop, branch currents and loading, and losses.
  * A sweep of load multiples, with curves of voltage and losses against load.
  * Warnings:
    * `voltage_drop`: more than 4 % at the bench (IEC 60364-5-52, Annex G);
    * `overload`;
    * `no_convergence`.
  * Measurement table: line voltage at each bus.
* **`short_circuit`**
  * I''k3 maximum and minimum, i_p, I_th, I''k1 maximum and minimum, R/X and Z_loop for every
    bus.
  * Measurement table: Z_loop from a loop tester.

The run view draws a **single-line diagram** annotated with the results of the run: voltages
and loading for a load flow, I''k3 and I''k1,min for a short circuit.

## Tests (`test_network.py`)

* **N1, N2:** the two engines agree to 1e-9 or better, for loads ×0, ×1 and ×4 and for both
  short-circuit cases.
* **N3:** I''k3 and i_p at B1 equal a hand calculation written out in the test.
* **N4:** the physics has the right direction:
  * voltage falls as load rises;
  * I''k falls along the feeder;
  * the minimum case is below the maximum case;
  * I''k1 > I''k3 at the Dyn terminals.
* **N5:** the warnings and invalid input are handled.
* **N6:** the API end to end.
* **E2E N1.**

## Not modelled

* Motor contribution to the short-circuit current.
* Harmonics.
* Unbalanced loads.
* The transformer tap changer.
* Fault resistance.
* The PE conductor separately from the cable's Z0.

## Next (N2)

Protection and TCC: the breaker and fuse curves of the installation module on log-log axes,
the selectivity check between C1 and C2, and the minimum fault current against the
magnetic-release threshold.

## N2 — protection: time–current curves, disconnection and selectivity

Study `protection` (`vel/experiments/network/protection.py`).

**Breakers.** Thermal-magnetic breakers sit at the head of each zone:

* Q1 at B1, feeding C1;
* Q2 at B2, feeding C2;
* Q3, the bench outlet's breaker, at B3.

They use the breaker model of experiment 8, `mcb_trip`: a first-order bimetal tripping at
k_t², and a magnetic release at k_m·I_n after t_mag. In the spec section `protection`:

* Q3 = C16 with τ = 48.7 s, the value fitted in experiment 8;
* Q1 = 250 A and Q2 = 63 A, with assumed τ.

**Checks.** The fault currents come from the IEC 60909 study, and pandapower is checked against
our solver in every run.

* **Disconnection (IEC 60364-4-41, TN system).** The minimum earth-fault current at the end of
  each zone must trip that zone's breaker in time:
  * Q1, for the zone ending at B2, within 5 s;
  * Q2, for the zone ending at B3, within 5 s;
  * Q3, at B3, within t_disc = 0.4 s.
* **Overload.** I_n ≤ I_z of the protected cable.
* **Selectivity.**
  * The fault is placed just below the downstream breaker. That gives Q3/Q2 at the maximum
    I''k3 of B3, and Q2/Q1 at the maximum I''k3 of B2.
  * The limit is the first current at which the upstream breaker does not trip later than the
    downstream one (with an optional margin). It is found by a scan and then bisection.
  * In this model two magnetic releases trip in the same t_mag, so selectivity ends exactly at
    the upstream magnetic threshold (630 A and 2500 A for the preset). This is the "partial
    selectivity" of manufacturers' tables.
  * Real breakers can be selective beyond that threshold through current limitation or energy
    selectivity. That needs the manufacturers' tables, which are not modelled. The run states
    this in its warning.

**Outputs.**

* A zones table: disconnection time against the required time, I_z, and I''k3 at the breaker's
  location (the breaking capacity it needs).
* A selectivity table.
* Time–current curves of the three breakers on log-log axes.

**Tests.**

* **N7:** the selectivity limit equals k_m·I_n of the upstream breaker. Below that threshold
  the pair is selective over the whole range.
* **N8:** for the preset, every zone disconnects in time and both pairs are partially
  selective. With a 2 km bench cable and Q2 = 100 A, both `disconnection_fails` and
  `overload_unprotected` are raised. The curves fall with current and end at t_mag.
