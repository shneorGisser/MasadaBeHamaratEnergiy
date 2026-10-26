# Experiment 2: the bench sheet, 2026 (squirrel-cage induction motor)

Source: a photo of the measurement sheet lying on the bench, taken on 26.10.2026 with the
rest of the lab photos (see "Equipment" below). It was transcribed by hand from the photo.
The dataset is `induction_motor_2026` in `vel/labdata/datasets.py`.

## What the sheet records

| Table | As written |
|---|---|
| 4.4 no-load | U (phase) = 220 / 180.5 / 150.1 V ("380 = V_line" above). I0 = 0.446 / 0.321 / 0.26 A. P0 = 70 / 56 / 48 W. cos φ0 = 0.237 / 0.322 / 0.410, computed on the sheet as P0/(3·U·I0) |
| 4.5 locked rotor | Uk = 59.67 / 70.63 / 82.94 / 97.56 V. Ik = 0.488 / 0.606 / 0.707 / 0.866 A. Pk = 47 / 72 / 98 / 141 W. cos φk = 0.57 / 0.57 / 0.58 / 0.57 |
| 4.6 load (raised to 380 V) | I1 = 0.45 → 0.8 A. P1 = 34 / 63.1 / 78 / 90 / 115 / 140 W. n = 1450 → 1310 rpm. M = 0.3 / 0.8 / 1.02 / 1.24 / 1.6 / 1.976 N·m. cos φ written 0.45 → 0.8. P2, s and η are computed on the sheet |

## How it was read

* **No-load.** cos φ0 on the sheet is P0/(3·U·I0) with the phase voltage. So U is a phase
  value and P0 is the three-phase total. The study table wants a line voltage and a one-phase
  wattmeter reading (P0 = 3·P). It was entered as √3·U and P0/3.
  * Row 1 I0 is read as 0.446 and not 0.46. Only 0.446 gives the written 0.237.
* **Locked rotor.** The same reading is the only consistent one. With phase Uk and total Pk,
  cos φk = 0.54–0.56, close to the written 0.57. Every other combination gives cos φ > 1 or
  ≈ 0.93. It was entered the same way as the no-load table.
  * Row 1 Ik has a second number written over it. 0.488 was entered; 0.458 would give
    exactly 0.57. This is flagged as a row note.
  * The handwritten Zk / Rk / Xk on the right (for example Rk ≈ 22.6 Ω, Xk ≈ 63.4 Ω) do not
    follow from the table. The table itself gives Rk = Pk/(3·Ik²) ≈ 63–66 Ω. They were not
    entered.
* **Load.** η on the sheet is P2/(3·P1), for example 45.6/(3·34) = 44.7 %. So P1 is a
  one-phase reading. That matches the table's convention and was entered as written.
  * U1 is not in the table. It was entered as 380 V, per the instruction printed above it.
  * Row 5 η is written as ≈ 65.0 %. The computation gives 65.6 %.
* **Not entered.** Three handwritten lines under table 4.4 (V_L ≈ 343 / 300 / 173 V, …) are
  not legible enough.
* **Missing.** No speed at no-load, no DC resistance, no nameplate.
* **Open question.** The two wattmeter conventions differ: totals in 4.4/4.5, one phase in
  4.6. The photo cannot tell whether that comes from the meter (the Appli-com meter has a
  "3ph" mode) or from the hand computation.

## Calibration against the default machine (370 W, 380 V Y, 1.02 A, 1380 rpm)

| Set | Fitted (factor × default) | rms error before → after |
|---|---|---|
| no-load | Xm × 1.65, R_fe × 1.75, P_fw × 2.0 (R_fe and P_fw correlated, ρ = 0.95) | 34 % → 5.4 % |
| locked rotor | R2' × 2.75 (55 Ω), X1 = X2' × 2.84 (48 Ω) | 41 % → 2.3 % |
| load (alone) | R2' × 2.48 (50 Ω); P_fw poorly determined | 24 % → 13.6 % |

### Independent check

With only the no-load and locked-rotor fits applied, the model predicts the load test
(test C6):

| M [N·m] | P1 meas / model [W] | I1 [A] | cos φ | n [rpm] |
|---|---|---|---|---|
| 0.3 | 102 / 111 | 0.45 / 0.40 | 0.45 / 0.42 | 1450 / 1444 |
| 1.02 | 234 / 229 | 0.55 / 0.53 | 0.65 / 0.66 | 1400 / 1360 |
| 1.976 | 420 / 398 | 0.80 / 0.78 | 0.80 / 0.77 | 1310 / 1210 |

Input power, current and cos φ agree within about 10 %. The written cos φ column is therefore
a real reading, not a computation.

### Calibration per set: the slip gap

With the per-set calibration, the slip is over-predicted by up to about 50 %. The locked-rotor
test fixes only R1 + R2' together, and the per-set fits keep the default R1 = 24 Ω. Test C6
pins this (`max slip error > 30 %`), because it is a property of fitting one set at a time.

### Joint fit (all three tables together)

`scripts/fit_induction_2026.py` fits R1, X1 = X2', R2', Xm, R_fe and P_fw to the no-load,
locked-rotor and load tables at once. The load table's speeds then fix the R1/R2' split.

* Result, Y-equivalent per phase: R1 = 35.2 Ω, X1 = X2' = 49.4 Ω, R2' = 33.7 Ω, Xm = 488 Ω,
  R_fe = 14.3 kΩ, P_fw = 30.8 W.
* Per Δ winding the values are three times larger.
* rms residual: 1.8 tolerance units (0.01 A, 1 W, 5 rpm). Worst: 3.4.
* The sheet is internally consistent. With one machine it fits all 32 readings, slip included.
  The preset `ap3030_sheet_2026` carries this fit. Test: `test_ap3030_preset_reproduces_the_2026_sheet`.

## Nameplates (second batch of photos, 26.10.2026)

| Machine | Plate | Model |
|---|---|---|
| Appli-com AP-3030, "Three phase induction motor with squirrel-cage rotor" (bench labelled "Ind M cage") | 0.37 kW (0.5 HP), 380/660 V Δ/Y, 1.13/0.65 A, cos φ 0.67, 1400 rpm, 50 Hz, ins. B, IP44 | new preset `ap3030_sheet_2026` (plate + joint fit). The default stays the assumed motor until the question below is settled |
| Multifunction three-phase asynchronous/synchronous machine (slip-ring; K(F1), L, M(F2)), type 8-3017710-000-01-0 | Y/Δ 400/230 V, 0.83/1.44 A, 0.27 kW, cos φ 0.7/1.0, 1360/1500 rpm, 50 Hz; rotor U2 ≈ 107 V, I2 ≈ 1.1 A; DC excitation 20 V, 4.0 A; ins. B/F, IP20 | already in experiments 3 and 4 (270 W, 400 V Y, 0.83 A, 1360 rpm, If 4.0 A) — confirmed |
| Multifunction DC machine GNRDEC 71/2/L (Appli-com panel A1-A2, B2, C1, D1-D2-D3, E1/F1-E2/F2, thermal switch) | U_A 220 V, I_A 2.50 A, 2500 rpm, 0.37 kW, U_E 220 V, I_E 0.30 A, η 70 %, S1, ins. F, IP54 | already in experiments 5 and 6 (370 W, 220 V, 2.5 A, 2500 rpm, If 0.3 A) — confirmed |

### Which motor was the sheet measured on?

The joint fit is evaluated at each plate's own rated point:

| Hypothesis | Fitted machine at the plate's rated point | Plate |
|---|---|---|
| AP-3030, stator in Δ at 380 V | 1400 rpm: 158 W, 0.56 A, cos φ 0.66 | 370 W, 1.13 A, 0.67 |
| AP-3030, stator in Y at 380 V | evaluated at 660 V Y: 539 W, 0.98 A; the no-load current would exceed the rated 0.65 A | 370 W, 0.65 A |
| Multifunction machine, Y at 380 V | 400 V, 1360 rpm: 237 W, 0.70 A, cos φ 0.73 | 270 W, 0.83 A, 0.70 |

* **AP-3030 in Δ (the correct connection for 380 V):** the machine delivers only 43 % of the
  plate power at the plate speed.
* **AP-3030 in Y:** impossible for a real motor.
* **Multifunction machine:** within 12–16 %, which is ordinary for a plate against an
  equivalent circuit.

**This is open.** Either the sheet was measured on the multifunction machine (rotor shorted), or
the AP-3030 does not meet its plate. The answer decides the default motor of experiment 2.

## Equipment in the photos (26.10.2026)

| Item | Seen | Used in the model |
|---|---|---|
| Machine bench (Appli-com) | three-phase supply, IGBT bridge, frequency inverter (digital Hz), power meter 14 05 010 (V phase, I line, P1, "3ph" label), resistive load 0–100 %, capacitive load Δ/Y 230/400 V 17–136 var, brake control unit AP8500300 (torque N·m, speed rpm, four-quadrant LEDs) | the wattmeter convention above. On the 3D bench, the meters are drawn as Appli-com modules with a red readout, and the brake has a control unit showing M and n |
| Langlois HTN 450/8 variac | 400 V Y in, 0–450 V out, 50–400 Hz, 8 A, 6.24 kVA | `source3`, drawn on the 3D bench as the Langlois housing (ribs, handle, blue sockets) |
| Appli-com power-electronics racks | 3×45-0-45 V 2.5 A supply, SCR/diode half-bridges, 100 Ω 100 W loads, 50 mH chokes, PWM / six-pulse firing, ±15 V; 300 VA 380/220 V transformer | not modelled (no power-electronics experiment yet) |
| Metrel MD9040 True-RMS DMM | 10 A / 0.6 A / 1000 V CAT IV | ideal meter |
| Metrel MD9272 clamp | 100 A, 600 V CAT III | ideal meter |
| Metrel MI 3125 Eurotest COMBO | installation tester | experiment 8 (Z-LOOP, RCD) |
| Keysight DSOX1204G, DSOX2004A | 70 MHz, 2 GSa/s, 4 channels | the transient scope view |
| GW Instek GPS-2303 | 2 × 30 V 3 A DC supply | not modelled |
| ADVICE Electronics dual DC supply | 2 × 0–30 V, 0–3 A, analog meters, 5 V fixed 3 A | not modelled (seen with an opened DC motor) |
| Appli-com DC power supply 0–240 V / 8 A, field rheostat 820 Ω 0.8 A, lights load 200 W, resistive load 3 × 100 Ω 100 W | DC-machine bench (brake unit showing 0.692 N·m / 2250 rpm, supply 166 V / 1.53 A) | experiments 5–6 |
| ASEA Education "Regulating starter" | rotor starter rheostat, MAX … 0 | experiment 4 (R_ext) |
| Appli-com 300 VA three-phase transformer | primaries 380 V / 220 V, secondaries 2 × 110 V 0.7 A per phase, fuse 1 A | experiment 1; the 2025 preset uses 0.35 A per winding — not reconciled |
| Agilent DSO5012A | 100 MHz, 2 channels | the transient scope view |

Meter accuracy (class, digits) is still not modelled. Every simulated meter is ideal, as stated
in `vel/engine/netlist.py`.
