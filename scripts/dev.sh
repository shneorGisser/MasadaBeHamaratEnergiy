#!/usr/bin/env bash
# Development: backend on :8000 (auto-reload) + Vite on :5173 with /api proxy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
( cd "$ROOT/backend" && "$ROOT/.venv/bin/uvicorn" --factory vel.main:create_app --reload --port 8000 ) &
BACK=$!
trap 'kill $BACK' EXIT
cd "$ROOT/frontend" && npm run dev
