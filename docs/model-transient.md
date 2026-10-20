# Time-domain engine (transients)

The steady-state phasor MNA answers "where does the machine settle". The transient engine answers
"how does it get there". The two share the spec and are tested against each other: every
transient must end on the steady-state solver's operating point.

Plan, from the broad review of 2026-10-20. The equations and test scenarios come from the
Modelica Standard Library (BSD-3) and motulator (MIT); the solver is SciPy `solve_ivp` (Radau).

| Step | Transient | Status |
|---|---|---|
| T1.1 | Induction motor, direct-on-line start (5th-order dq, synchronous frame) | **done** |
| T1.2 | Star-delta start, wound-rotor starter steps (event-segmented integration) | **done** |
| T1.3 | DC machine: start through a starter, shunt-generator voltage build-up (using the fitted OCC) | |
| T1.4 | Transformer energisation and inrush (saturation curve + remanence, switching angle) | |
| T1.5 | Synchronous machine: sudden 3-phase short circuit (checked against the analytic IEEE 115 envelope), synchronisation | |
| T1.6 | Inverter-fed motor (average model, V/f ramp) | |

## T1.1 — induction motor, direct-on-line start

`vel/engine/transient/induction.py`, study `dol_start` (experiment 2).

* **States:** ψs, ψr (space vectors, amplitude-invariant, referred to the stator) and ω_m.
* **Reactances:** X1, X2', Xm from the spec at f_n, converted with L = X/ω_n.
* **Load:**
  * brake torque × tanh(ω_m/ω_ε), so it acts against rotation and vanishes at standstill;
  * friction and windage M_fw ∝ n, the same law as the steady-state model.
* **Supply:** ideal, switched on at a chosen phase angle of v_a. The angle sets the DC offset
  of the currents.
* **Not modelled:**
  * iron loss (the study reports its effect on the steady state: +0.26 % current for the
    assumed motor);
  * saturation of the leakage paths at starting current;
  * deep-bar effect;
  * supply impedance.
* **Inertia J is not on the nameplate.** It defaults to 0.003 kg·m² (assumed) and the run
  warns about it. J sets the starting time, not the starting current.

Tests (`test_transient_induction.py`):

* **TI1:** Y and Δ, loaded and unloaded. The final speed is within 0.01 rpm of the phasor
  solver, and the RMS line current within 0.01 %. The instantaneous current at the end is a
  sinusoid of that RMS.
* **TI2:** with the rotor held by a huge J, the current equals the phasor solver's
  locked-rotor current (0.1 %).
* **TI3:** the switching angle changes the peak but not the RMS inrush. The peak lies between
  √2 and 2√2 times the locked-rotor RMS.
* **TI4:** the study and the API. A too-short run warns `not_settled` instead of reporting an
  unsettled "final" speed.

None of these is a validation against a measured start. The MSL `AIMC_DOL` reference result
(18.5 kW motor with published parameters) is the next external check.

## T1.2 — star-delta and the rotor starter

**Event-segmented integration.** A start is now a list of segments, integrated one after
another with the states carried over. Each segment has its own:

* winding voltage and phase, or "stator open";
* connection (for line currents);
* added rotor resistance.

The solver therefore never steps across a switching instant.

**Star-delta, open transition.**

* **Sequence:** Y until t_switch → dead time with the stator open → Δ.
* **During the dead time:** i_s = 0, and the rotor flux turns with the rotor and decays with
  Lr/R2'. On reclosing, the stator flux is the one this rotor flux induces. That is why the
  reclosing spike, and a short braking torque, depend on the dead time and on the angle at
  the changeover.
* **Supply voltage:** the default is the rated WINDING voltage, because star-delta needs a
  machine whose delta voltage equals the supply voltage. A higher supply warns
  `winding_overvoltage`.
* **Δ convention:** winding U1–U2 sits across L1–L2, i.e. +30° to L1–N.
* **Early changeover:** a changeover below 90 % of the star speed warns `early_changeover`.

**Rotor starter (wound rotor, experiment 4).**

* **Steps:** R_st per phase until time t, written as R@t.
* **Referred resistance:** each step adds k²·R_st to R2'.
* **Default steps:**
  1. the resistance that puts the pull-out torque at standstill (R2' + k²R_st = X1 + X2');
  2. half of it;
  3. rings shorted.
* **Inertia:** J is assumed to be 0.01 kg·m².

**Tests.**

* **TI5:** in star the line current is a third of a direct delta start (2 %); the motor
  settles on the phasor solver's Δ point (0.01 rpm, 0.01 %); no current flows during the
  dead time, and the motor coasts.
* **TI6:** the warnings for early changeover, winding overvoltage and a bad schedule.
* **TW1:**
  * the starter lowers the standstill current and raises the torque;
  * the current equals the phasor solver's locked rotor with the starter (1e-5), after the
    rotor-flux transient has decayed;
  * with a finite J the slowly creeping rotor biases that comparison by ≈ 0.5 %, so the test
    holds the rotor with J = 1e9.
* **TW2:** the stepped start settles on the phasor point; two switching events are listed.
