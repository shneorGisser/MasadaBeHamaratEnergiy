# Experiment 4: the 2025 report (wound-rotor machine)

The 2025 report of experiment 4 (`ניסוי 4_251130`) is **filled in with measurements**. It was not
used when experiment 4 was first built, which relied on the 2026 nameplate only. It was found
during the completeness audit after experiments 5–6. Recorded values:

| Table | Content |
|---|---|
| 4.1 insulation | 999 MΩ for every winding |
| 4.4 no-load | U1 = 220 / 180 / 150 / 100 V ("380" crossed out). I0 = 0.44 / 0.31 / 0.25 / 0.18 A. P0 = 19 / 14 / 11 / 9 W |
| 4.5 locked rotor | Uk = 90 / 100 / 115 / 130 V. Ik = 0.78 / 0.90 / 1.03 / 1.24 A. Pk = 42 / 53 / 71 / 94 W. cos φ written 0.58–0.60 |
| 4.6 load, 230 V | M = 0 – 0.6 N·m. I1 = 0.48 → 0.51 A. P1 = 29 → 58 W. n = 1467 → 1427 rpm |
| 4.7 load with starter "intermediate" (R not recorded) | M = 0 – 0.5 N·m. n = 1453 → 1389 rpm |
| 5.1 regulator | U2 at 0–360° in 45° steps: 45.3, 72.7, 71.2, 37.6, 57, 78, 56.5, 46, 74.3 V |
| Generator (fig. 4-8) | n = 1431 → 1734 rpm. P = −40 → +24.4 W. I = 0.2 → 0.64 A. M = 0 → 1.63 N·m |
| Inverter | Only 50 and 60 Hz rows filled, with V_out ≈ 460 V |

## Interpretation and its contradictions

* **Connection.**
  * At 220–230 V, the currents fit a Δ-connected stator (230 V Δ = 400 V Y per winding).
  * With Y, the model's no-load current would be half of the measured value.
* **Wattmeter.** The P column is **not used consistently**:
  * In 4.4 and 4.6 it has to be a one-phase reading (P1 = 3·P). Otherwise table 4.6 has a
    shaft output of 0.6 N·m × 1427 rpm = 90 W above an input of 58 W.
  * In 4.5, the same reading would give a resistance above the impedance (cos φ > 1). The
    written cos φ = P/(U·I) fits neither reading. Only Ik is fitted there.
* **Speed and nameplate.** The speeds of 4.6 imply a large rotor resistance. The fitted
  R2 = 6.37 Ω per phase agrees with the 6.4 Ω measured between F1–F2 in experiment 3 (2026),
  if that was one rotor phase. But it contradicts the plate:
  * the model reaches rated torque at ≈ 1100 rpm, against 1360 rpm on the plate;
  * X1 + Xm = 1077 Ω, against 674 Ω from experiment 3's synchronous reactance.
* **Regulator.** U2(α) is not periodic in 180° mechanical, as a 4-pole machine requires: 0°, 180°
  and 360° give 45, 57 and 74 V. It looks like a measurement or reading problem, for example
  rotor play or a misread angle scale.
* **Generator.** The wattmeter sign is reversed: it is negative while motoring below 1500 rpm. At
  ≈ 1700 rpm and 1.5 N·m the reading is 23 W per phase, where the fitted model gives ≈ 58 W.
  The magnitudes disagree even though the torque–speed relation agrees (model 1.67 N·m at
  1700 rpm). The brake/servo torque reading probably includes something the wattmeter does not
  see. Not resolved.

## What was done

* A preset **`report_2025`** in `wound_rotor/spec.py`, made by `scripts/fit_wound_rotor_2025.py`:
  * R1 and k kept; X1 = X2' = 86.3 Ω, R2' = 69.5 Ω, Xm = 991 Ω, R_fe = 2.16 kΩ, P_fw = 6.4 W;
  * rms 3.3 in tolerance units of 0.01 A, 1 W and 5 rpm; the worst points are about 0.07 A,
    5 W and 40 rpm off.
* Test W10 reproduces it. That test is a fit regression, not validation.
* The **default stays the nameplate fit**, because it agrees with the 2026 nameplate and with
  experiment 3.
* Neither parameter set is consistent with every source. The 2026 group's own DC, no-load and
  locked-rotor tables will decide, and the measurement-vs-simulation comparison is built for
  exactly that.
