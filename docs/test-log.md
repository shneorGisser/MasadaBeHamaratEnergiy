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
