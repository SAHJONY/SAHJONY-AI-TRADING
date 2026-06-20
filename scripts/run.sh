#!/usr/bin/env bash
# Run one trading cycle. Used by cron/launchd and for manual ticks.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
[ -d .venv ] && source .venv/bin/activate || true
exec "$PY" main.py --once "$@"
