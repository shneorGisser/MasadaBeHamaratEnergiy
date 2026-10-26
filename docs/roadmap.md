# Backlog (after experiments 1–6)

Order agreed with the user on 2026-10-20. Done items move to `test-log.md`.

1. ~~Import real lab reports as measurement sets~~. Done: `vel/labdata`, plus the import UI in the measurements panel.
2. ~~Automatic explanation of measured-vs-simulated differences~~. Done: `services/diagnose.py` (the per-comparison detectors and the parameter-set probe).
3. ~~**Visual wiring guide.**~~ Done: `services/wiring.py` + the guide in each study, with the cable highlighted in the schematic and the 3D bench. Requested by the user: "איך לחבר ואיפה איזה כבל".
   * For every study circuit, a step-by-step guide that shows which cable goes from which
     terminal to which, in the order a student wires the bench: supply off first, then the
     current path, then the voltage leads.
   * The same circuit document that drives the schematic and the 3D bench drives the guide,
     so the guide can never contradict the simulation.
   * It is only partly possible until there are photos of the real terminal boards. Until then
     it shows the schematic terminal names (A1, F1, U1 …) and highlights wire k of n on the
     schematic and the 3D bench.
4. ~~Word export of the report~~ Done: `services/report_docx.py`.: Hebrew RTL, David 11, line spacing 1.15, MATLAB/Python code in an appendix.
5. ~~Hysteresis (falling OCC branch)~~ Done: `F_h` for the DC machine (fitted); for the synchronous machine the data do not resolve one, so `F_h` = 0 — for the synchronous and DC machines.
6. 3D bench modelled on the real equipment. Waits for the photos.
7. ~~Experiment 8 (installation testing)~~ Done: module `installation`, see `docs/model-installation.md`. RCD, insulation, earth and continuity run on assumed values until the lab measures them.
8. Cloud deployment. **Ready:** CI builds the image and smoke-tests it against PostgreSQL 16 on every push. **Left:** the deployment itself needs the user's Google Cloud account (`docs/deploy-cloud-run.md`).

## From the external review (Gemini, 2026-10-20) — checked against the code

Accepted and done:
* Build output tracked in git (`backend/build/`, `*.egg-info`, an old snapshot with only
  experiment 1). Untracked, and ignored in `.gitignore` and `.dockerignore`.
* The run list loaded every run's full result. It is now deferred, which matters for
  transient runs with thousands of samples.

Accepted, queued (after the time-domain steps T1.4–T1.6):
1. ~~Scope tools in the charts~~ Done: `ScopeChart` + `scope.ts` (cursors A/B, Δt, 1/Δt, mean/RMS/p-p over the window, harmonics over whole periods of f₀ with THD); the inrush study now reports I₂/I₁ (> 15 %: what a differential relay blocks on).
2. ~~Charts in the Word report~~ Done (and in the HTML/PDF, which turned out to have none either): `report_charts.py` draws every curve of a section from the report's tables with matplotlib (≥ 3.11 lays Hebrew out with the bidi algorithm; labels get a leading RLM). Long tables are folded to 15 rows, the MATLAB appendix is thinned to ≈ 400 points, and `GET /reports/{id}/data.zip` carries all the data as CSV — a transient report went from 120 Word pages to 11.
3. ~~Winding temperature~~ Done: `experiments/thermal.py` (docs/thermal.md).
4. ~~"Calibrate the model to my measurements"~~ Done: `services/calibration.py` (docs/calibration.md) — least squares on the comparison itself, uncertainties, correlations, bounds; applied only on request.
5. ~~Front-end unit tests; split LabBench3D~~ Done: `lab3d/` is now `LabBench3D.tsx` (scene + controls), `Equipment.tsx`, `Studio.tsx`, `live.ts`; Vitest for `curves.ts`, `live.ts`, `scope.ts`, `router.ts`, `dxf.ts`.
6. ~~Move installation physics to the engine~~ Done: `vel/engine/installation.py`.
7. ~~Wiring check against the template~~ Done: `services/wiring_check.py`, `GET …/circuits/{kind}/check`, button "בדוק מול החוברת". Compares nets (not cables), picks the closest variant, reports missing joints with the student's groups and extra joints (shorts); a difference is reported as "differs from the manual", not as an error.

Checked and rejected, or already the case:
* "MNA has no nonlinear iteration": wrong. The magnetising branch is solved iteratively
  (`NonlinearShunt`, `ConvergenceError`). Rectifiers are not supported; that is out of the
  course's scope.
* "Machines are linear, 15–25 % error at high field": wrong. The DC and synchronous OCCs
  saturate and are fitted to the 2025/2026 data, and the transformer magnetising branch
  saturates.
* Automatic Gmin stepping: rejected. It turns a wrong circuit (a floating part, a
  source/ammeter loop) into a plausible-looking answer. The project's rule is that failures
  are explicit. Floating parts are already pinned and reported (`floating_groups`), and
  source loops are explicit errors.
* "Measured points are not overlaid on the model curves": they already are, in every
  comparison view.
* "Brush drop not modelled": it is, in the DC machine (U_b·tanh). Slip-ring brushes of the
  wound rotor carry small currents, so the effect there is negligible.
* "Unbalanced loads / neutral shift": the MNA is a full three-phase abc network, so unbalance
  is native. Symmetrical-component readings could be added if a lab table needs them.
* "Transient for only 1 of 6 experiments": out of date. The DC machine is done (T1.3); the
  transformer and synchronous machine are next (T1.4, T1.5).
* Renaming `dc_machine/modules.py`: it defines two modules (experiments 5 and 6), so the
  plural is accurate. Cosmetic.
* The missing e2e number s6, an English translation, and datasets as JSON instead of typed
  Python (the Python form is type-checked and tested): low value for a one-course Hebrew tool.
* Deep-bar effect and saturation of leakage at starting current: real, and listed as not
  modelled in model-transient.md. It needs a measured locked-rotor test at several
  frequencies before a model can be fitted.
