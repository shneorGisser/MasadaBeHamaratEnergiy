#!/usr/bin/env bash
# Start the backend with a fresh temporary database, serving the built frontend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8765}"
TMP="$(mktemp -d)"
export VEL_DATABASE_URL="sqlite:///$TMP/e2e.sqlite3"
export VEL_STATIC_DIR="$ROOT/frontend/dist"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/uvicorn" --factory vel.main:create_app --host 127.0.0.1 --port "$PORT" --log-level warning
