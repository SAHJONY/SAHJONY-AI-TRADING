#!/usr/bin/env bash
# Run several isolated desks side by side (e.g. Robinhood crypto + Alpaca
# equities). Each desk is a gitignored env file in desks/<name>.env plus its own
# SAHJONY_HOME (state/db/status/HALT) under desks/homes/<name>.
#
#   cp desks/robinhood-crypto.env.example desks/robinhood-crypto.env   # add keys
#   cp desks/alpaca-equities.env.example  desks/alpaca-equities.env    # add keys
#
#   scripts/desk.sh robinhood-crypto --preflight    # read-only check (no orders)
#   scripts/desk.sh robinhood-crypto --loop         # run the desk
#   scripts/desk.sh alpaca-equities  --loop         # second desk, in parallel
#   scripts/desk.sh robinhood-crypto off|on|status  # per-desk kill switch
#
# Safety: each desk arms live ONLY via the deliberate opt-ins inside its own env
# file (see GO_LIVE.md); this launcher never arms anything. Hard risk ceilings
# apply per desk. Each desk has its OWN HALT file, stoppable independently.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="${1:-}"; shift || true
[ -n "$NAME" ] || { echo "usage: scripts/desk.sh <desk-name> [--preflight|--once|--loop|on|off|status]"; exit 1; }
ENV_FILE="desks/${NAME}.env"
[ -f "$ENV_FILE" ] || { echo "✗ $ENV_FILE not found. Copy desks/${NAME}.env.example → $ENV_FILE and add your keys."; exit 1; }

# Load the desk's env (values never printed) and give it an isolated home.
set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a
export SAHJONY_HOME="${SAHJONY_HOME:-$(pwd)/desks/homes/$NAME}"
mkdir -p "$SAHJONY_HOME"

PY="${PYTHON:-python3}"
[ -d .venv ] && source .venv/bin/activate 2>/dev/null || true

case "${1:-}" in
  on|off|status) exec scripts/live.sh "$1" ;;                 # per-desk kill switch
  *)             exec "$PY" main.py "${@:---once}" ;;         # default: one cycle
esac
