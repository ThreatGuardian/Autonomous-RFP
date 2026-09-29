#!/usr/bin/env bash
# One-command start for macOS / Linux: installs dependencies, builds the web app
# and serves everything on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --silent)
fi
(cd frontend && npm run build --silent)

cd backend
echo "Tenderdesk is starting on http://127.0.0.1:8000"
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
