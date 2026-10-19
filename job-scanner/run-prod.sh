#!/usr/bin/env bash
# Production instance: your live data, no auto-reload.
#   Port : 8000
#   DB   : data/jobs.db
# Leave this one running; develop against run-dev.sh in another terminal.
set -euo pipefail
cd "$(dirname "$0")"

# Activate venv if present.
[ -f .venv/bin/activate ] && source .venv/bin/activate

export DB_PATH="${DB_PATH:-data/jobs.db}"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"

echo "PROD → http://$HOST:$PORT   (DB: $DB_PATH)"
exec python main.py
