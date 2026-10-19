# Test log

Every entry records commands actually executed and their real output summary.

## S0 — infrastructure and projects (2026-10-19)
Command: `scripts/check.sh`
- ruff: all checks passed · mypy --strict: no issues (19 files)
- pytest: 6 passed (health, experiments, CRUD, persistence across app restart, invalid inputs, transformer spec validation)
- oxlint: 0 warnings · tsc: ok · vitest: 2 passed · vite build: ok
- Playwright (Chromium 1194, real backend + temp SQLite): 2 passed

## S1 — solver, transformer model, no-load / short-circuit / DC / insulation (2026-10-19)
Command: `scripts/check.sh` → ALL CHECKS PASSED
- pytest: 35 passed, including
  - R1 ideal ratio (4 voltage pairs, rel 1e-9) · R2 ideal current ratio/power · R3 hypothesis power balance (60 cases, rel 1e-9)
  - R4 Chapman Ex. 2-2 extraction (rel 0.5 %) — **textbook values transcribed; page copy pending verification**
  - R5 round trip: R_Fe, X_m, r_k, x_k within 2 % · manual x_k undefined for cos φk = 0.598
  - R7 capacitive load raises U2 · R8 ngspice-42 agreement on 5 linear circuits, rel 1e-8 · R9 seven invalid-circuit/case tests
  - API: immutable runs, spec change does not alter stored runs, reproduction identical, failed runs stored as failures
- vitest: 5 passed · Playwright: 5 passed (S0 ×2, S1 ×3: no-load, short circuit + invalid input, DC + insulation)
- Known limitation found while testing: none blocking. ngspice's `echo` prints 6 digits; the cross-check uses `print` with `numdgt=15`.

## S2 — 2D schematic, load test, vector groups (2026-10-19)
Command: `scripts/check.sh` → ALL CHECKS PASSED
- pytest: 46 passed. New: R6 vector groups Yy0/Yy6/Yy4/Yy8/Yd1/Yd11 from wiring topology (clock from phasors + cosine-law candidates),
  cosine-law geometry check on ideal Yy0, missing A1–a1 bridge → invalid_circuit, load study R/L/C (η, ΔU% sign, rated-current target hit to 1e-9)
- vitest: 8 passed (CircuitModel ↔ React Flow round trip, nets, id generation)
- Playwright: 8 passed. New: load test R and C; delete instrument → save → run fails naming A2 → reload persists edit →
  add ammeter + drag-wire between terminals → stored wire verified through the API → reset to manual circuit → success;
  vector groups 0 / 4 / 11 via the UI.
- Limitation: wire routing in the schematic is automatic (smoothstep); dense templates still have crossings.

## S3 — real measurements, comparison, extraction (2026-10-19)
Command: `scripts/check.sh` → ALL CHECKS PASSED
- pytest: 54 passed. New (R10 + API): unit conversion and rejection of incompatible/non-finite/unknown units; error definitions
  (meas − sim, relative to the selected reference, undefined for a zero reference with reason); append-only corrections with
  the original kept verbatim; rows with data cannot be removed; "simulate at measured points" reproduces measured operating
  points exactly; measured = simulated except I0 × 1.05 → I0 and Y_m errors exactly 5 %, g_m and P0 exactly 0; unmatched and
  missing rows explicit; kind mismatch rejected; vector group from measured voltages (θ = 30° → clock 1 or 11).
- Bug found by the tests and fixed: the no-load row (I2 = 0) was not detected (`0.0 or 1.0`), so ΔU% was missing.
- Simulated and measured tables now go through one derivation module (`derive.py`).
- Playwright: 10 passed. New: enter 9 values incl. mA, correct a typo (history shown), reload, measured P0 analysis,
  simulate at measured points, relative error of I0 checked numerically for both reference choices; invalid number rejected.

## S4 — 3D lab bench (2026-10-19)
Command: `scripts/check.sh` → ALL CHECKS PASSED
- pytest: 55 passed. New: live operating point equals the study run at the same voltage (bit-identical I0 and P);
  open switch → zero current and secondary voltage; overriding non-live parameters, unknown components and negative
  voltages are rejected / reported as invalid_circuit.
- Playwright: 11 passed. New: WebGL scene renders in headless Chromium; the ammeter/voltmeter labels in 3D show exactly
  the solver's values; variac to 475 V shows the saturated I0 (> 3× rated I0) matching the API; opening S gives 0 A / 0 V;
  selecting T in 3D selects it in the schematic and vice versa; nothing is persisted by the 3D view.
- Limitation: equipment geometry is generic (procedural) until photographs of the lab bench are provided.

## S5 — guided mode and reports (2026-10-19)
Command: `scripts/check.sh` → ALL CHECKS PASSED
- pytest: 60 passed. New: guide steps complete only from data (data steps cannot be ticked by a click); report HTML is RTL,
  David font, contains measured values and the student's discussion; a later measurement correction and spec change leave
  the published report byte-identical; empty discussion is stated, not generated; invalid section references rejected;
  PDF rendered by headless Chromium (`%PDF-`, > 5 kB).
- Playwright: 12 passed. New: the full §9 journey — guided mode (0/27 → safety ack), nameplate edit, simulation, reload,
  reproduction, lab measurements, simulate at measured points, comparison, report generated and reopened after reload,
  correction does not change the report, PDF downloads, guide shows compare + report steps done.

## S6 — real lab data, backup, deployment readiness (2026-10-19)
Command: `scripts/check.sh` → ALL CHECKS PASSED · plus `VEL_TEST_PG_URL=postgresql+psycopg://… pytest` → 67 passed on PostgreSQL 16
- pytest: 67 passed. New: fitted preset reproduces its own fit point; **independent validation** on last year's resistive-load
  table (not used for fitting): U2ph within 2.5 % and I1 within 1.6 % on 4 of 5 rows; row 1 (−3.7 % / +6.1 %) is the row whose
  P2 > U2·I2 is physically impossible and is flagged by the new plausibility check; line/phase ambiguity in the report's
  short-circuit table detected; export → import round trip (new ids, runs reproducible, correction chain, report byte-identical).
- Playwright: 14 passed. New: preset loaded and simulated at the report's rated short-circuit point; backup downloaded and restored.
- Packaged (non-editable) install: migrations + solver + report verified.
- NOT executed: `docker build` (Docker Hub blocked in this environment) and an actual Cloud Run deployment.
