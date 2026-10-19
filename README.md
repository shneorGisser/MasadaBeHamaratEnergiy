# Virtual Energy Lab — מעבדה וירטואלית להמרת אנרגיה

A browser-based virtual laboratory for the Electrical Energy Conversion lab course (JCT).
First module: **Experiment 1 — three-phase transformer** (insulation, DC winding resistance,
no-load, short-circuit, R/L/C load, vector groups).

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
Optional: install `ngspice` to run the independent cross-validation tests (they are skipped,
and reported as skipped, when it is missing).
