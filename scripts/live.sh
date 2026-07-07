#!/usr/bin/env bash
# Owner on/off switch for trading — the operational go / no-go.
#
#   scripts/live.sh off      # STOP: suspend ALL new orders immediately (kill switch)
#   scripts/live.sh on       # RESUME: allow orders (LIVE if armed, else paper/sim)
#   scripts/live.sh status   # show on/off + whether real money is armed
#
# HOW IT WORKS: this toggles the desk's HALT file — the same kill switch the
# workforce checks every cycle (workforce._halted). "off" suspends new risk on the
# next tick; "on" clears it.
#
# SAFETY — read this: "on" does NOT arm real money. Whether an order is REAL or
# simulated is decided separately by the deliberate double-lock in your .env
# (ROBINHOOD_LIVE=true + LIVE_TRADING_ACK for Robinhood; ALPACA_PAPER=false +
# LIVE_TRADING_ACK for Alpaca). This switch only pauses/resumes trading within
# whatever mode you've already, deliberately, armed. "off" always fully stops.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
HALT="$("$PY" -c 'from paths import halt_path; print(halt_path())')"

_capability() {   # "ARMED — LIVE real money" or "not armed — paper/sim"
  "$PY" - <<'PY'
from config import load_config
c = load_config()
rh = c.broker == "robinhood" and c.robinhood_live and c.live_trading_ack
al = c.broker == "alpaca" and (not c.alpaca_paper) and c.live_trading_ack
print(f"ARMED — LIVE real money on {c.broker}" if (rh or al)
      else f"not armed — paper/sim on {c.broker}")
PY
}

case "${1:-status}" in
  off)
    : > "$HALT"
    echo "⛔ TRADING OFF — kill switch set ($HALT)."
    echo "   New orders are suspended from the next cycle. Open positions are untouched."
    ;;
  on)
    rm -f "$HALT"
    echo "▶  TRADING ON — kill switch cleared."
    echo "   Capability: $(_capability)"
    echo "   (To trade REAL money you must have armed it in .env; 'on' alone never does.)"
    ;;
  status)
    if [ -f "$HALT" ]; then echo "state:      OFF (HALT present)"; else echo "state:      ON (no HALT)"; fi
    echo "capability: $(_capability)"
    ;;
  *)
    echo "usage: scripts/live.sh {on|off|status}"; exit 1 ;;
esac
