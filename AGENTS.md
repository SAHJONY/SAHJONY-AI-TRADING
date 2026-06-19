# Project Context: Autonomous Trading Engine
- This is an autonomous algorithmic trading bot interfacing with the Alpaca Paper Trading API.
- Maintain a local persistent state inside `state.json`. Never allow state loss between cron executions.
- Strict Security: Never commit `.env` files.
- Modular Layout: Separate the runtime orchestrator, data layers, and specific trading strategies.
- Fault Isolation: Wrap API calls in try/except blocks and log to `logs/bot.log`.
