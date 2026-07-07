#!/usr/bin/env bash
# One-command desk setup for your own machine.
#
#   git clone https://github.com/SAHJONY/SAHJONY-AI-TRADING.git
#   cd SAHJONY-AI-TRADING
#   bash scripts/setup.sh
#
# Does everything that can be automated: a Python venv, all dependencies
# (including the Robinhood adapter), and a .env scaffolded from the template.
# The ONLY thing left for you afterwards is pasting your keys into .env — that's
# yours to do; secrets never live in the repo. Re-running is safe (idempotent).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
say() { printf '\n\033[1;33m▸ %s\033[0m\n' "$*"; }

# 1. Python
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "✗ Python 3.11+ not found — install from https://python.org/downloads"; exit 1; }
say "Using $("$PY" --version)"

# 2. Virtual environment
if [ ! -d .venv ]; then say "Creating virtual environment (.venv)"; "$PY" -m venv .venv; fi
# shellcheck disable=SC1091
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; else source .venv/Scripts/activate; fi

# 3. Dependencies (base + Robinhood adapter)
say "Installing dependencies (this can take a minute)"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
[ -f requirements-robinhood.txt ] && python -m pip install --quiet -r requirements-robinhood.txt

# 4. .env scaffold (never overwrite an existing one)
if [ ! -f .env ]; then
  cp .env.template .env
  say "Created .env from the template — now open it and paste your keys."
else
  say ".env already exists — leaving it untouched."
fi

# 5. Confirm the trading engine imports and can build its config (no orders)
say "Verifying the engine loads"
python -c "from config import load_config; c=load_config(); print(f'   ✓ engine OK — broker={c.broker}, mode={c.mode}')"

cat <<'NEXT'

────────────────────────────────────────────────────────────────────────
 SETUP DONE. Two steps left, both yours:

 1) Edit .env and paste your keys (paper-safe to start):
      BROKER=robinhood
      ROBINHOOD_API_KEY=...        ROBINHOOD_PRIVATE_KEY=...
      TICKERS=BTC/USD,ETH/USD      MARKET_HOURS=24_7
      MAX_ALLOCATION_PCT=0.02
      ROBINHOOD_LIVE=false         LIVE_TRADING_ACK=      (leave these off)

 2) Activate the venv and prove the read-only connection (NO orders):
      source .venv/bin/activate     # Windows: .venv\Scripts\activate
      python main.py --preflight    # shows your real balances, mode "live-data"

 Then run it:   python main.py --loop
 Stop anytime:  scripts/live.sh off
 Go live (only when ready): set ROBINHOOD_LIVE=true and
      LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY in .env — see GO_LIVE.md §E/§F.
────────────────────────────────────────────────────────────────────────
NEXT
