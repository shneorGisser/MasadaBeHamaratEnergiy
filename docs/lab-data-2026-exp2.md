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

### Known gap: slip

The slip is over-predicted by up to about 50 %. The locked-rotor test fixes R1 + R2' together.
The split between them comes from the default R1 = 24 Ω.

Trying R2' = 36 Ω and R1 = 43 Ω (the same sum) brings the slip within about 20 %. But it raises
P1 by up to 17 % and lowers η. No single split fits both. The reason could be a rotor resistance
that changes with speed (the rotor frequency at locked rotor is 50 Hz, and only a few Hz under
load), or an inconsistent sheet.

The way to settle it is a DC-resistance measurement of the stator (the `dc_resistance` study
already exists). The sheet has none. Test C6 pins the gap explicitly
(`max slip error > 30 %`), so it cannot silently disappear or grow unnoticed.

The real motor is clearly smaller than the default machine. At 1380 rpm it gives 179 W and
not 370 W. The nameplate photo is still needed.

## Equipment in the photos (26.10.2026)

| Item | Seen | Used in the model |
|---|---|---|
| Machine bench (Appli-com) | three-phase supply, IGBT bridge, frequency inverter (digital Hz), power meter 14 05 010 (V phase, I line, P1, "3ph" label), resistive load 0–100 %, capacitive load Δ/Y 230/400 V 17–136 var, brake control unit APB00300 (torque N·m, speed rpm, four-quadrant LEDs) | the wattmeter convention above. The brake unit is the source of M and n |
| Langlois HTN 450/8 variac | 400 V Y in, 0–450 V out, 50–400 Hz, 8 A, 6.24 kVA | `source3` (adjustable supply) |
| Appli-com power-electronics racks | 3×45-0-45 V 2.5 A supply, SCR/diode half-bridges, 100 Ω 100 W loads, 50 mH chokes, PWM / six-pulse firing, ±15 V; 300 VA 380/220 V transformer | not modelled (no power-electronics experiment yet) |
| Metrel MD9040 True-RMS DMM | 10 A / 0.6 A / 1000 V CAT IV | ideal meter |
| Metrel MD9272 clamp | 100 A, 600 V CAT III | ideal meter |
| Metrel MI 3125 Eurotest COMBO | installation tester | experiment 8 (Z-LOOP, RCD) |
| Keysight DSOX1204G, DSOX2004A | 70 MHz, 2 GSa/s, 4 channels | the transient scope view |
| GW Instek GPS-2303 | 2 × 30 V 3 A DC supply | not modelled |

Meter accuracy (class, digits) is still not modelled. Every simulated meter is ideal, as stated
in `vel/engine/netlist.py`.
