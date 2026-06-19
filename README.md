# SAHJONY CAPITAL LLC Autonomous Trading Bot

This repository contains a **self‑contained, production‑ready** algorithmic trading engine that interacts with the Alpaca Paper Trading API. It is designed for continuous execution via a 15‑minute cron schedule, maintains persistent local state, and follows strict security practices (no `.env` committed).

## Project Layout
```
Trading/
├─ AGENTS.md               # Hermes Agent project description (auto‑read)
├─ .env.template          # Fill in your Alpaca keys, never commit
├─ config.py               # Loads env vars, defines risk limits
├─ state.json              # Persistent runtime state (updated each run)
├─ requirements.txt       # Python dependencies
├─ Dockerfile              # Multi‑stage container image
├─ main.py                 # Orchestrator / console dashboard
├─ logs/bot.log            # JSON‑style logs (rotated externally)
├─ utils/
│   └─ alpaca_client.py   # Singleton Alpaca wrapper with logging
└─ strategies/
    ├─ wheel_strategy.py   # Options wheel (OTM puts → covered calls)
    └─ trailing_ladder.py  # Equity ladder with trailing stops
```

## Quick Start (local)
```bash
# 1. Create a .env file from the template
cp .env.template .env
#   Fill in ALPACA_API_KEY and ALPACA_API_SECRET

# 2. Install deps & run
pip install -r requirements.txt
python main.py
```

## Docker
```bash
docker build -t sahjony-trading .
docker run --rm -v $(pwd)/state.json:/app/state.json \
  -v $(pwd)/logs:/app/logs \
  --env-file .env sahjony-trading
```

## Deployment & Scheduling
A persistent **Hermes Agent cron job** (see `manage-alpaca-trading-bot` skill) will invoke `python main.py` every 15 minutes during NYSE market hours (Mon‑Fri 09:30‑16:00 EST). See the generated skill for details.

## License
MIT – feel free to fork and adapt.
