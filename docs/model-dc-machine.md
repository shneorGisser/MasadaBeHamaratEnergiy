# DC machine model (experiments 5 and 6)

Experiments 5 (motor) and 6 (generator) use **one** machine — the same nameplate appears in both
2025 reports — so they share one spec (`backend/vel/experiments/dc_machine/spec.py`), one engine
(`engine/dcmachine.py`) and one component (`dcmachine`, terminals A1–A2 armature, F1–F2 shunt
field, S1–S2 series field).

## Equations

* Armature in the network: A1 —R_a— (source E_eff) — A2, with E_eff = E − U_b·tanh(I_a / 0.05 A).
  The brush drop is a nearly constant U_b (the manual's "2 V·I_a" loss) that changes sign smoothly.
* Field MMF in shunt-field amperes: F = I_f + ρ_s·I_s − k_ar·|I_a| + F_res.
  I_f flows F1→F2, I_s flows S1→S2, so swapping S1/S2 turns cumulative into differential.
* EMF: E = (n/n_ref)·OCC(F), OCC(F) = a·F / (1 + (|F|/I_s)^m)^(1/m) (odd in F).
* Torque: M_em = OCC(F)/ω_ref · I_a (generator convention). Rotational losses P_rot ∝ |n|^k_rot;
  k_rot = 1 means a constant friction torque, which is what the lab data show (see the fit).

## Solution method

The DC network is linear in E_eff, so every branch current is affine in it: I = β + α·E_eff (two
network solves). The machine then reduces to one scalar equation
g(E) = E − r·OCC(F(E)) + U_b·tanh(I_a(E)/I_b) = 0.

* A self-excited generator can have several roots (remanent point, built-up point, an unstable one
  between them). The physical one is where the field transient goes when the machine starts from
  its remanence, so the root is searched by marching from E₀ = r·OCC(F_res) in the direction of
  −g, and is then refined with the Illinois method. A wrongly connected field, or a field
  resistance above the critical one, therefore gives "no build-up" (with a warning), as in the lab.
* Speed mode ("servo drives"): n is given.
* Torque mode ("brake"): n follows from M_em(n) = M_fric(n) + M_load on the first stable crossing
  (scan up to 1.5·n_max, then Illinois). The direction of rotation follows the starting torque.
  * No crossing → **explicit** runaway error. This covers a shunt motor with an open field and an
    unloaded series motor.
  * A starting torque below the brake → stall. This is an error in runs, and a marked 0 rpm point
    on the live bench.
  * |n| > n_max is always an explicit error.

## Parameters (preset `lab_2025_fit`, the default)

| Quantity | Value | Source |
|---|---|---|
| Nameplate | 220 V, 2.5 A, 2500 rpm, 370 W; field 220 V / 0.3 A | 2025 reports, both experiments |
| R_a | 12.5 Ω | 6/2.2 (U/I and ohmmeter). 5/2.2 gives 13.5 Ω (U/I, includes brush drop) and 12.8 Ω (ohmmeter) |
| R_s | 5.2 Ω | 6/2.2: 5.0 Ω (U/I) and 5.2 Ω (ohmmeter); 5/2.2: 5.29 Ω and 5.4 Ω |
| R_f | 368 Ω | 6/2.2, ohmmeter |
| U_b | 2.0 V | the manual's value; fits as well as 0 V (rms 0.62 vs 0.59 in tolerance units) |
| OCC a, I_s, m, F_res | 612 V/A, 0.291 A, 2.57, 0.005 A at n_ref = 2000 rpm | least-squares fit, see below |
| k_ar | 0.0187 A/A | fit |
| ρ_s | 0.193 | fit (compound motor 5/2.8) |
| P_rot(n_n), k_rot | 63.9 W (M_0 = 0.244 N·m), 1 | fit |
| n_max | 3000 rpm | **assumed** (not on the plate) |
| Insulation | 462 / >999 / >999 MΩ | 6/2.1. 5/2.1 measured 789 MΩ on the armature |

**Fit.** The script is `scripts/fit_dc_machine.py` (needs scipy); tests D1–D3 reproduce it. It minimises:

* the speed error of tables 5/2.3, 2.4, 2.5 and 2.8, with a tolerance of 20 rpm;
* the torque error, with a tolerance of 0.05 N·m;
* the error of the generator OCC 6/2.3, with a tolerance of 3 V, scaled by an unknown speed ratio.

Every residual stays within 2 tolerances. The OCC table had no recorded speed, and the fit puts
it at **≈ 2550 rpm**. That is close to the 2500 rpm nameplate speed, and it is independent
evidence that the same machine and the same model explain both reports.

D1–D3 test the fit against the same data it was made from. They are **regressions, not validation.**

## Findings in the 2025 data (also flagged by the plausibility checks)

* **6/2.6 (shunt generator).** From column 5 onwards the "If" row rises to 1.7 A while "Ia"
  falls. The rows look swapped (V/If ≈ 450–490 Ω only if they are swapped back). The check
  `field_rises_with_load` flags this.
* **6/2.7 (compound generator).** Both series polarities give the same voltage within 1 V up to
  1.28 A. The compound motor (5/2.8) shows a strong series field (ρ_s ≈ 0.19), so the model
  predicts:
  * about 210 V cumulative at that current;
  * a collapse above ≈ 0.55 A differential.

  The 6/2.7 data therefore look as if the series winding was not actually in the circuit, or its
  polarity was not changed. The check `series_effect_missing` flags this.
* **5/2.6 ("60 % load").** The speed falls only 131 rpm over 0–30 Ω. That implies I_a ≈ 0.36 A,
  i.e. practically no load, not 60 %.
* **Field current 0.48 A at 174 V.** This needs a field circuit of 363 Ω < R_f = 368 Ω, a 1.4 %
  conflict (warm vs. cold winding, ammeter class). The study accepts targets up to 5 % above the
  maximum, with the rheostat at zero and an explicit `field_at_maximum` warning.
* **Generator speed.** It is not recorded in 6/2.4–2.7. 6/2.6 (220 V at If = 0.48 A, no load)
  implies ≈ 2800 rpm, which is the study default. The OCC table implies ≈ 2550 rpm.
* **No-load armature current.** The model gives 0.32 A at 2085 rpm; the lab measured 0.36 A at
  2058 rpm. This is the largest relative deviation (≈ 13 %). Rotational loss as a constant torque
  is only an approximation: the lab's no-load loss rises slightly with flux.

## Hysteresis (descending OCC branch)

The descending branch is the rising one with the MMF shifted by δ = 4·F_h·x·(1 − x), where
x = I_f / I_f,max and the turning point is the largest field current of the table.

* The shift is zero at both ends: the branch starts at the turning point and returns to the
  remanence.
* F_h = 0.013 A, fitted to the falling column of 6/2.3 at the implied 2550 rpm. The rms error
  of that column drops from 5.4 V to 1.6 V; test D13 checks it.
* It is a one-parameter shape, not a magnetic hysteresis model: there are no minor loops and
  no dependence on the previous excursion.
* For the synchronous machine the 2025 and 2026 tables do not resolve a hysteresis. The
  differences between the branches are ±2–6 V, in both directions. F_h therefore stays 0, and
  the run says so.

## Not modelled

* Commutation.
* Temperature.
* Transients: starting current, build-up time.
* Dependence of the iron loss on flux.
* Armature reaction as anything but a linear demagnetising MMF.

Compound generators use a **short shunt**: the field sits across the armature. This matches 6/2.7,
where both polarities start from the same no-load voltage.
