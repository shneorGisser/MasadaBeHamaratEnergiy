# Virtual Energy Lab — מעבדה וירטואלית להמרת אנרגיה

A browser-based virtual laboratory for the Electrical Energy Conversion lab course (JCT).
Modules:
- **Experiment 1 — three-phase transformer** (insulation, DC winding resistance, no-load,
  short-circuit, R/L/C load, vector groups).
- **Experiment 2 — squirrel-cage induction motor** (insulation, DC winding resistance, no-load,
  locked rotor, load with a magnetic-powder brake and torque–speed curve, inverter V/f).
  Motor parameters are assumed until the lab nameplate is available — see `docs/model-induction-motor.md`.
- **Experiment 3 — synchronous machine** (insulation, DC resistances, open-circuit characteristic, three-, two- and
  single-phase short circuits, R/L/C load characteristics, regulation, zero-power-factor/Potier, V-curves on the grid).
  Parameters fitted to the student's 2026 measurements — see `docs/model-synchronous.md` and `docs/lab-data-2026-exp3.md`.
- **Experiment 4 — wound-rotor induction machine** (turns ratio, no-load, locked rotor, load with/without starter
  resistance, induction regulator, induction generator on the grid, inverter) — see `docs/model-wound-rotor.md`.
- **Experiments 5 and 6 — DC machine as motor and as generator** (insulation, resistances with brush drop; shunt motor
  at no load and on load, speed control by extra armature resistance and by field, compound motor; OCC, external
  characteristics with separate / shunt / compound excitation incl. shunt build-up, regulation, parallel with a DC
  network). One machine model fitted to the 2025 reports of both experiments — see `docs/model-dc-machine.md`.

The planning package (vision, requirements, architecture, validation plan, roadmap) is in the
project's planning document; `docs/` holds the engineering notes and the test log.

## Layout
| Path | What |
|---|---|
| `backend/vel` | FastAPI app, phasor solver (`engine/`), experiment modules (`experiments/`), SQLite via SQLAlchemy + Alembic |
| `backend/tests` | unit, engineering-reference, ngspice cross-validation and API integration tests |
| `frontend/src` | React + TypeScript UI (Hebrew RTL), 2D schematic, 3D bench, instruments, reports |
| `frontend/e2e` | Playwright end-to-end tests against the real backend |
| `scripts/` | `dev.sh` (dev servers), `check.sh` (full quality gate), `serve-e2e.sh` |

## Quick start
```bash
python3 -m venv .venv && .venv/bin/pip install -e 'backend[dev]'
(cd frontend && npm ci)
scripts/dev.sh            # backend :8000 + Vite :5173
scripts/check.sh          # lint, types, all tests, build, E2E
```
Docs: `docs/model-transformer.md` (model), `docs/test-log.md` (every test run), `docs/lab-data-2025.md`
(real-data validation), `docs/deploy-cloud-run.md` (going online), `docs/prompts-google-stitch-ai-studio.md`.

Optional: install `ngspice` to run the independent cross-validation tests (they are skipped,
and reported as skipped, when it is missing).
