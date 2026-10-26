# Experiment 8: testing an electrical installation

Module `installation` (`backend/vel/experiments/installation/`). Unlike experiments 1–6, there is
no circuit to edit. Each reading of the installation tester (MI 3125), the megger or the earth
tester comes from a closed-form model in `vel/engine/installation.py`. Each study names the acceptance criterion
it applies and where that criterion comes from.

## Data: the 2025 report

Most of the 2025 report is the manual itself. Only three tables are filled in by hand, and
they are transcribed in `vel/labdata` (`installation_2025`). The RCD, insulation, earth and
continuity tables are **empty**, so the spec values for those tests are assumed.

| Table | Values as written |
|---|---|
| Grid voltages (p. 5) | L1-N 234, L2-N 234, L3-N 235, L1-L2 405, L2-L3 407, L3-L1 405 V |
| Fault loop (p. 5) | L1-N **0**, L2-N **0**, L3-N **0**, L1-PE 0.16, L2-PE 0.16, L3-PE 0.15, L1-L2 0.12 (unit not written; Ω assumed) |
| MCB test (p. 10) | In = 1, 1, 3, 3, 3, 6, 6, 6, 6 A; I = 4.9, 3.3, 18.4, 12.7, 8.3, 45, 41, 38, 18 A; t = 2.57, 8.1, 2.8, 3.8, 9.8, 2.2, 1.81, 2.02, 12.5 s |

## Models and their basis

| Study | Model | Criterion |
|---|---|---|
| Grid voltages | Phasors U1..U3 at 120°; line voltage = \|Va − Vb\| | 230 V ±10 % (IEC 60038) |
| Fault loop | Series sums: L-N = Z_L + Z_N, L-PE = Z_L + Z_PE, L-L = 2·Z_L; I_pf = U/Z | Reg. 22, as in the manual: Z ≤ U0/(k·In) with k = 5 / 10 / 20 for B / C / D |
| MCB | Bimetal θ' = (k² − θ)/τ, trip at θ = k_t²; from cold t = τ·ln(k²/(k² − k_t²)); magnetic release at k_m | IEC 60898-1: no trip at 1.13·In; trip at 2.55·In in 1–60 s; magnetic < 0.1 s at 5/10/20·In |
| RCD | Trips when \|I_L + I_N\| ≥ k_trip·IΔn, after t0 + t1·(I_trip/I)² (+ type S delay) | IEC 61008-1: no trip at ½IΔn; ≤ 300 ms at IΔn; ≤ 40 ms at 5·IΔn (type S: 130–500 ms at IΔn) |
| Insulation | R_is ‖ R_su ‖ C (manual fig. 5.2), megger internal resistance R_s, display limit; the guard bypasses the surface current | ≥ R_min (default 1 MΩ: IEC 60364-6, 500 V) |
| Earth | Rod in uniform soil: R_g = ρ/(2πL)·(ln(8L/d) − 1) (Dwight). Profile R(x) = R_g − ρ/(2π·r13) − ρ/(2πL)·asinh(L/x) + ρ/(2π·(r13 − x)) | Manual: spread over 0.4–0.6·r13 ≤ 10–15 % (10 % applied); r13 ≥ 5D and ≥ 50 m; TT: R_A·IΔn ≤ 50 V (IEC 60364-4-41) |
| Continuity | ρ_Cu·L/A + contact resistance (+ "loose terminal") | Manual: ≈ 0.05 Ω |

**The 62 % rule follows from the profile.** Far from the rod, asinh(L/x) ≈ L/x, and at
x = 0.618·r13 the terms −1/x + 1/(r13 − x) cancel 1/r13, so R = R_g. Close to the rod the
line-source term does not cancel, and the rule drifts by ≈ 1 % at r13 = 2·L (test I7). That
drift is what the manual's "r13 ≫ D" requirement protects against.

## Fit and findings (preset `lab_2025`)

* **Supply voltages.** U1..U3 are the measured phase voltages. The line voltages are then a
  genuine prediction: 405.3 / 406.2 / 406.2 V against 405 / 407 / 405 V, all within 1.2 V,
  which is the reading resolution.
* **Fault loop.** Z_L = 0.06 Ω and Z_PE = 0.10 Ω, fitted to L-PE and L1-L2. That is 2
  parameters for 4 values, with a residual ≤ 0.01 Ω (the display resolution).
  * **L-N = 0 is impossible.** Every loop contains a phase conductor, and L1-L2 = 0.12 Ω, so
    every L-N loop must be at least 0.06 Ω. The check `loop_below_phase` flags it. Most
    likely the readings were not taken, or the instrument showed another quantity.
  * Z_N is therefore assumed equal to Z_L.
* **MCB.** One τ for all three ratings.
  * The geometric-mean fit gives **τ = 48.7 s** with **k_t = 1.3 assumed**. τ and k_t cannot
    be separated: every k_t in 1.13–1.45 fits equally well (log-sd 24 % each).
  * The scatter is ±24 % (rms of ln(t/t_model) < 0.3, test I3), and it shows no consistent
    trend with test order. The order in which the tests were actually run is not recorded,
    so a warm-breaker effect cannot be tested; θ0 is available as a case input.
  * **Curve class.** Type B is ruled out: it must trip magnetically in < 0.1 s at 5·In, but
    the 3 A unit took 2.8 s at 6.1·In and the 6 A unit 2.2 s at 7.5·In. The data fit C (or D).
  * C is the default, with k_m = 10 (the class bound). The data only show k_m > 7.5.
* **Not measured in 2025:**
  * the protecting MCB (C16 assumed);
  * the RCD (30 mA, trips at 0.8·IΔn, 22 ms at IΔn — assumed);
  * the insulation;
  * the earth (ρ = 100 Ω·m, 1.5 m rod → R_g = 59.6 Ω);
  * the earthing conductor.

## Not modelled

* Loop inductance and phase angles (the tester shows magnitudes).
* Thermal memory between consecutive tests (θ0 = 0 unless set).
* Manufacturing spread of breakers and RCDs.
* Non-uniform soil and buried metal.
* Mutual coupling of the auxiliary-electrode leads.
* Temperature and humidity dependence of insulation.
* The 2-line (two-ray) electrode layout of fig. 6.5: only the in-line method is simulated.
