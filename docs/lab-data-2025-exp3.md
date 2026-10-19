# Experiment 3: the 2025 report, a second data set for the same machine

The 2025 report (`ניסוי 3_251109`) has the same tables as your 2026 report, measured on the same
machine. Its stator resistances are 33.3, 34.5 and 35.7 Ω, compared with 33.3 Ω in 2026. These
measurements were not used in the fit, so they serve as an **independent check**.

| Table | 2025 values |
|---|---|
| 6.2 | F1–F2 = 7 Ω, from one point at 2 V / 0.27 A (2026: 6.3–6.4 Ω) |
| 6.3 OCC, rising | If 0 … 0.91 A → Ef 4.9 … 226 V |
| 6.4 short circuits | Ik(3) up to 0.8 A at If = 1.8 A. Ik(2) up to 0.7 A at 1.15 A. Ik(1) up to 0.83 A at 0.9 A |
| 6.5 R/L/C load | Recorded |
| 6.6 regulation | Recorded |
| 6.6b ZPF | 6 points, If 0.93 → 0.35 A, U1 173 → 53 V, I1 = 0.1 A |

## Result

* **OCC: the 2026 fit agrees with the 2025 data without any change.** From If = 0.17 A upwards the
  difference is at most 6 V. Below that (22.3 V at 0.09 A, model 29.8 V) the remanence and
  hysteresis region differs. Test G13 checks this. It is a real validation, because these points
  were not used in the fit.
* **Short circuits: every 2025 current is ≈ 1.85× the 2026 model's.** This holds for all 16
  points of all three fault types. The ratios Ik(2)/Ik(3) ≈ 1.48 and Ik(1)/Ik(3) ≈ 2.07 match the
  model's 1.41 and 2.09. One common factor of 0.5375 on all reactances fits every point within
  0.05 A, mostly within 0.02 A. That gives **Xs = 362 Ω**. The fit is in
  `scripts/fit_synchronous_2025.py` and the result is the `report_2025` preset.
* **This connects to the 2026 data.** In 2026, two Ik(3) points were flagged as outliers
  (If = 1.0 and 1.3 A, giving 390 and 355 Ω). They are exactly the 2025 value. So two
  measurements over two years give Xs ≈ 360 Ω, and the rest of the 2026 table gives 674 Ω.

## What remains contradictory

The plate gives a rated field current of 4.0 A at cos φ = 1. With Xs = 674 Ω the model needs about
3.7 A, which agrees with the plate. With Xs = 362 Ω it needs about 2 A. So the two candidates
stand like this:

* **Xs = 674 Ω** is supported by the nameplate and most of the 2026 short-circuit table.
* **Xs ≈ 360 Ω** is supported by the 2025 short circuits and two 2026 points.

The **default stays `lab_2026`**. The cheapest way to decide is to repeat the three-phase short
circuit at If = 0.6 / 1.0 / 1.6 A with a known ammeter range. The two candidates predict
0.14 / 0.24 / 0.38 A and 0.25 / 0.44 / 0.71 A respectively.
