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
| T1.5 | Synchronous machine: sudden 3-phase short circuit (checked against the analytic IEEE 115 envelope), synchronisation | **short circuit done**; synchronisation next |
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

## T1.5a — synchronous machine: sudden three-phase short circuit

`vel/engine/transient/synchronous.py`, study `sudden_sc` (experiment 3). Sauer–Pai
sub-transient model with stator transients, rotor frame, generator convention, cylindrical
rotor (X'q = Xq), speed held by the drive.

**Parameters.**

* From the spec: Xd = Xq = Xl + a·k_a (unsaturated) and R = Ra.
* Defaults for what the spec lacks:
  * X''d = X2, the measured negative-sequence reactance (X2 ≈ (X''d + X''q)/2);
  * X'd = 1.5·X''d (assumed);
  * T'd0 = 0.3 s, T''d0 = 0.02 s, T''q0 = 0.03 s (assumed).
* The run lists which of these values are assumed.

**Linearity.** The model is linear (air-gap line), which is correct for the sustained current
of a short-circuited machine. When the OCC is saturated at the chosen field current, the run
warns that the initial currents are slightly overstated.

**Two independent checks in every run:**

* the sustained current against the steady-state model (same E/Xs);
* the AC envelope against the IEEE Std 115 formula at 0.1 s.

For the lab machine (Ra = 33 Ω against X''d = 151 Ω, far from R ≪ X) the envelope still
agrees within 1.5 %.

**Tests (`test_transient_synchronous.py`):**

* **TS1:** the envelope is within 3 % of IEEE 115 at 0.05, 0.1, 0.3 and 1.0 s, for R small
  and for the lab's R.
* **TS2:**
  * the sustained current equals E/|R + jXs| (1e-5);
  * the first-cycle peak lies between √2E/X''d and twice that;
  * the field-current kick returns to the pre-fault value.
* **TS3:** the rotor angle at the fault sets the DC offset of phase A.
* **TS4:** the study passes both checks and rejects inconsistent reactances
  (X''d < Xl).

The cycle-averaged envelope is undefined within half a cycle of either end, and those samples
are left empty instead of being zero-padded.

## T1.5b — synchronous machine: synchronising to the grid

`synchronize()` in `vel/engine/transient/synchronous.py`, study `synchronize` (experiment 3).
It uses the same Sauer–Pai model as T1.5a, with two more states:

* the load angle δ, with dδ/dt = ω_e − ω_b;
* the rotor speed, with J·dω_m/dt = M_drive − M_em − M_fw.

The friction law M_fw ∝ ω gives P_fw ∝ n², the same law as the steady-state model.

**Setting.**

* The bus is infinite: v_d + j·v_q = √2·V·(sin δ + j·cos δ).
* Before the breaker closes, the machine runs open-circuit at f + Δf.
* Its EMF is the real OCC value at I_f, and its q axis is Δθ ahead of the bus voltage.
* After closing, the drive delivers a constant P_drive: + for a generator, − for a motor load.

**Saturation — the honest compromise.** The phasor engine saturates through the resultant
air-gap MMF; the dynamic model is linear.

* The study first solves the steady state on the grid with the phasor engine (template
  `motor_on_grid`). It then takes that solution's saturation factor k = E/(a·F).
* `saturate(m, k)` scales the mutual reactances X_ad and X_aq by k, keeping the rotor
  circuits. X_fd, X_1d and X_1q come from the equivalent-circuit identities. So X'd, X''d
  and the time constants move consistently, and less than Xd does.
* The field voltage sustains k·a·(I_f + F_res). The final state is therefore exact. The first
  swing is approximate, because k changes during it. A `saturation_linearised` warning
  appears when the pre-closing EMF and the model's field differ by more than 5 %.

**Checks in every run.**

* The final line current and power are compared with the phasor engine (`I_check`, `P_check`).
  The comparison runs only when the swing has died out. If it has not, the run shows the
  `not_settled` warning.
* At the rated point the two engines agree to 1e-4 or better.
* Pole slipping produces the `pole_slip` warning. Locking after slipping a pole pair produces
  the `slipped_poles` warning.

**Outputs.**

* The line currents over the first 0.4 s, at full resolution.
* The swing over the whole run: δ, P, n and the RMS current.
* The analytic estimate of the closing current |ΔU|/X''d.

**Assumed values.** J = 0.02 kg·m², together with the transient parameters of T1.5a. At
rated voltage the swing is lightly damped and takes about 10 s to settle (the default
t_end).

**Tests.**

* **TS5:** a perfect closing draws no current.
* **TS6:** a lossless generator settles on P = 3EV·sin δ/Xd (δ within 0.01°).
* **TS7:** a larger phase error gives a larger closing current, within the
  √2·2V·sin(Δθ/2)/X''d bounds.
* **TS8:** `saturate` keeps the reactance ordering, and the further a reactance is from the
  air gap, the less it moves.
* **TS9:** the study agrees with the phasor engine for P_drive = 0 and ±100 W.
* **TS10:** an overload slips poles and is reported, with no false check.
* **E2E T6:** the study runs with a 60° phase error.

## T1.6 — induction motor started on the inverter (V/f ramp, average model)

`vf_start()` and `VfRamp` in `vel/engine/transient/induction.py`; study `vf_start`
(experiment 2).

**Model.** The dq model is the same as T1.1. The frame turns with the supply frequency, which
now varies in time, so v_s = √2·U(f(t)) stays real.

* The frequency rises linearly from f_start to f_target in t_ramp.
* The voltage follows the same V/f law as the steady-state inverter study (`_vf`):
  U = U_boost + (U_n − U_boost)·f/f_n, capped at U_n above f_n (field weakening).
* The run is integrated in two pieces, the ramp and then constant frequency, so the solver never
  steps across the kink at the end of the ramp.
* Line currents are rebuilt with the supply angle θ = ∫2πf dt, which is computed analytically.

**Not modelled (average model):**

* PWM ripple and its losses;
* dead time;
* the DC-link voltage limit;
* the drive's current limit. The computed current is what the motor asks for, and a real drive
  may clip it.

**Warnings.**

* `average_model` appears on every run.
* `above_drive_limit` appears when the peak exceeds 150 % of the rated peak.
* `ramp_not_finished` appears when the run ends before the ramp does.

**Checks in every run.**

* `dn_check`: the final speed against the phasor solver at f_target and U(f_target), using
  `load_test`, which accepts any frequency.
* `iron_effect`: as in T1.1.
* The direct-on-line peak, for comparison (`I_ratio_dol`).

**Tests.**

* **TI9:** with t_ramp = 0 the run is a direct-on-line start, identical to `dol_start`.
* **TI10:** the run settles on the phasor point at 50 Hz, at 25 Hz with load, and at 60 Hz
  (field weakening). Speed agrees within 0.01 rpm and current within 1e-4.
* **TI11:** a longer ramp gives a smaller peak current, about 0.19 × DOL for 1 s. The warnings
  and invalid boost are also covered.
* **E2E T7.**

Reference for later work: motulator (MIT) provides inverter and control models, including
current-limited and vector-controlled drives. That remains the next step if the course needs
it.

## Cross-check against motulator (independent open-source model)

`vel/reference/motulator_im.py` runs the same direct-on-line start with **motulator**
(Aalto University, MIT licence, v0.18). The two implementations differ in every respect except
the physics:

| | Ours | motulator reference |
|---|---|---|
| Equivalent circuit | T | Γ (from inverse-Γ, exact conversion without saturation) |
| Frame | synchronous dq | stationary αβ |
| Solver | Radau | LSODA |
| Flux/current/torque code | `vel.engine.transient.induction` | `motulator.drive.model.InductionMachine` |

Shared on purpose, because they are inputs and not the model under test: the parameters, the
ideal supply and the load model (brake·tanh(ω/ω_ε) + k_fw·ω).

Result (`tests/test_reference_motulator.py`, three cases: the assumed motor unloaded and with a
1.5 N·m brake, and the AP-3030 fit at reduced voltage): line current, torque and speed agree to
**≈ 2·10⁻⁷ of their peaks** over the whole start. The test bound is 10⁻⁵. A missing √2, √3 or 3/2,
or a sign error in the frame rotation, would show up as ≥ 10⁻².

**V/f inverter start** (`test_REF2`, two ramps, one braked): time-varying frequency and
voltage with a kink at the end of the ramp. Both integrate in two pieces. Agreement ≈ 10⁻⁷.

## Cross-check against gym-electric-motor (DC shunt motor)

`vel/reference/gem_dc.py` runs our shunt-motor start through **gym-electric-motor** (Paderborn,
MIT, JOSS 2021), using its `DcShuntMotor.electrical_ode` and `torque`. GEM's DC machine is
linear, so the comparison is set up on the core both share:
* the field is energised first and settled;
* no armature reaction and no brush drop;
* GEM's L_e' = (OCC(F)/ω_ref)/i_f at that field.

What is checked is the coupling: EMF and torque constants, rpm ↔ rad/s, and the starter steps.
Result (`test_REF3`, three-step starter braked, and a direct start): ≈ 3·10⁻⁸ of the peaks.

The nonlinear parts (saturating field inductance, armature reaction, brush drop) are NOT covered
by this check. Their steady state is checked against the 2025 lab tables.

Not cross-checked this way:
* the synchronous machine. motulator's synchronous models are PM/SynRM drives; ours has a
  wound field and damper windings. That needs Modelica `Electrical.Machines` (planned).
* iron loss (absent in our transient model);
* saturation.
