# Time-domain engine (transients)

The steady-state phasor MNA answers "where does the machine settle". The transient engine answers
"how does it get there". The two share the spec and are tested against each other: every
transient must end on the steady-state solver's operating point.

Plan, from the broad review of 2026-10-20. The equations and test scenarios come from the
Modelica Standard Library (BSD-3) and motulator (MIT); the solver is SciPy `solve_ivp` (Radau).

| Step | Transient | Status |
|---|---|---|
| T1.1 | Induction motor, direct-on-line start (5th-order dq, synchronous frame) | **done** |
| T1.2 | Star-delta start, wound-rotor starter steps (event-segmented integration) | next |
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
