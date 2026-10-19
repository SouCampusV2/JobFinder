#!/usr/bin/env bash
# Development instance: isolated from production.
#   Port      : 8001            (prod stays on 8000)
#   DB        : data/dev.db     (separate — never touches your live data)
#   Scheduler : OFF             (no auto-scraping / no surprise OpenAI spend)
#   Reload    : ON              (code + template changes reload instantly)
#
# Run this in a SECOND terminal while run-prod.sh keeps serving your live app.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .venv/bin/activate ] && source .venv/bin/activate

export DB_PATH="data/dev.db"
export HOST="127.0.0.1"
export PORT="8001"
export SCRAPE_INTERVAL_MINUTES="0"   # (legacy) no default interval
export JOBFINDER_NO_SCHEDULER="1"    # fully disable the scheduler in dev (no surprise scans/spend)

# Optional: start dev from a copy of your live data the first time, so there's
# something to look at. Comment out if you prefer an empty dev DB.
if [ ! -f data/dev.db ] && [ -f data/jobs.db ]; then
  cp data/jobs.db data/dev.db
  echo "Seeded data/dev.db from data/jobs.db"
fi

echo "DEV → http://$HOST:$PORT   (DB: $DB_PATH, reload on, scheduler off)"
exec uvicorn main:app --reload --host "$HOST" --port "$PORT"
