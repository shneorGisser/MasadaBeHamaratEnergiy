#!/usr/bin/env bash
# Full quality gate: lint, types, unit/integration/reference tests, frontend tests, build, E2E.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/.venv/bin/activate"
echo "== backend: ruff";  (cd "$ROOT/backend" && ruff check vel tests && ruff format --check vel tests)
echo "== backend: mypy";  (cd "$ROOT/backend" && mypy)
echo "== backend: pytest"; (cd "$ROOT/backend" && pytest)
echo "== frontend: lint"; (cd "$ROOT/frontend" && npm run -s lint)
echo "== frontend: typecheck"; (cd "$ROOT/frontend" && npm run -s typecheck)
echo "== frontend: vitest"; (cd "$ROOT/frontend" && npm test --silent)
echo "== frontend: build"; (cd "$ROOT/frontend" && npm run -s build)
echo "== e2e: playwright"; (cd "$ROOT/frontend" && npx playwright test)
echo "ALL CHECKS PASSED"
