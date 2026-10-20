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
| T1.3 | DC machine: start through a starter, shunt-generator voltage build-up (using the fitted OCC) | **done** |
| T1.4 | Transformer energisation and inrush (saturation curve + remanence, switching angle) | **done** |
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

## T1.3 — DC machine: shunt-generator build-up, shunt-motor start

`vel/engine/transient/dcmachine.py`; studies `buildup` (experiment 6) and `motor_start`
(experiment 5). Both use the fitted machine of the 2025 reports.

**Field inductance.** It follows the OCC: L_f(F) = L_f0·OCC'(F)/a. The field therefore gets
"faster" as it saturates.

**Assumed values (not on the nameplate):**

* L_f0 = 92 H (τ_f ≈ 0.25 s);
* L_a = 0.08 H;
* J = 0.003 kg·m².

The runs warn about them. They set the speed of the transient, not where it settles.

**Build-up.**

* Short-shunt, no load, servo speed. The circuit starts from the remanence.
* Built or not: the same criterion as the steady-state solver (resultant MMF ≥ 2·F_res).
* Just above the critical resistance the remanent voltage is amplified, but there is no
  build-up.
* The linear critical field-rheostat value is reported: (n/n_ref)·a − R_a − R_f.

**Motor start.**

* Armature starter in steps.
* The field is energised first by default. Optionally it is switched on together with the
  armature, and then it rises with τ_f.

**A model limit found in this step.** The steady-state armature-reaction term −k_ar·|I_a|
reversed the main flux when the field was still near zero at switch-on, and the motor turned
backwards for a few rpm.

* Physically, armature reaction is cross-magnetising: it weakens an existing field through
  saturation but cannot reverse it.
* The transient engine now caps the term at half the main-field MMF.
* At every steady operating point of the fit, k_ar·I_n ≈ 0.05 A ≪ I_f, so the cap is
  inactive there. The steady state is unchanged and the tests agree to 1e-6.

**Tests (`test_transient_dc.py`):**

* **TD1:** the build-up ends on the DC solver's voltage (1e-6) for four rheostat settings, and
  rises monotonically.
* **TD2:** the critical resistance separates build-up from none, and near it the build-up is
  > 2× slower.
* **TD3:**
  * the motor start ends on the DC solver's speed and current, with and without the starter
    and with the field switched on late;
  * the starter halves the inrush;
  * the speed never goes negative.
* **TD4:** the studies report their assumptions, and the engines agree.

## T1.4 — transformer energisation (inrush)

`vel/engine/transient/transformer.py`, study `inrush` (experiment 1). Per-limb bank model,
secondary open, states i_k (series current) and λ_k (limb flux).

* **Star primary without a neutral (the lab feed).** Σi = 0, so the star point is solved
  algebraically. A delta primary has each winding across its line voltage.
* **Magnetising curve.** i_m(λ) = λ/L_m0·(1 + c'·|λ/λ_n|^n), the same shape as the
  steady-state X_m(E). c' is chosen so that the fundamental at rated flux equals the
  steady-state magnetising current (the steady state is a describing function, the
  instantaneous curve is not).
* **Remanence.** The initial flux pattern is (+r, −r, 0)·λ_n on the single-valued curve, i.e.
  no hysteresis loop. With no hysteresis loss, the decay is somewhat slower than measured.

**A physical finding the tests pin down.** With a star primary WITHOUT a neutral, the
third-harmonic magnetising current cannot flow. The flux is then not sinusoidal, and the
fundamental of the no-load current is 3.7 % higher than the phasor model, which assumes
sinusoidal flux. With the neutral connected the two engines agree to 0.16 %; with a linear
core they agree exactly. The study reports this as `I0_check`.

**Tests (`test_transient_transformer.py`):**

* **TT1:** with a linear core, the no-load current equals the phasor model (1e-4).
* **TT2:** with the saturating core and a neutral, it agrees within 0.5 %; without a neutral
  it differs by more than 1 %.
* **TT3:**
  * switching phase A at its voltage peak gives no inrush (< 1.5× the steady no-load peak);
  * at the voltage zero the inrush is more than 5× larger;
  * remanence in the same direction adds more than another 50 %.
* **TT4:** the study: the default case (60 % remanence, switching at the zero) gives an inrush
  of about 13× the rated peak current and 99× the no-load peak, decaying within about 0.26 s.

There is no measured inrush yet. The external check is the IPST 2011 inrush benchmark
(Chiesa et al.).
