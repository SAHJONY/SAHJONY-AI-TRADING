# Running SAHJONY as your personal LIVE trading desk

> ⚠️ **Real money.** Live mode places real orders on your Alpaca account and can
> lose money. The desk's "intelligence" is transparent public-domain estimators,
> not a profit guarantee. You are responsible for every order it places. Start on
> paper, watch it for a while, and only arm live when you understand the behavior.

This is the **single-user** path (you). Adding family & friends accounts is a
separate multi-account layer — see [SAAS.md](SAAS.md).

## 1. Get Alpaca keys
Create an account at alpaca.markets. You get two key pairs:
- **Paper** keys → simulated account, no real money. Start here.
- **Live** keys → your real, funded brokerage account.

Generate fresh keys in the Alpaca dashboard. **Never paste keys into chat or
commit them** — they go only in `.env` (gitignored) or your host's secret store.

## 2. Configure
```bash
cp .env.template .env
```
Edit `.env`:

**Paper first (recommended):**
```
ALPACA_API_KEY=<your PAPER key>
ALPACA_SECRET_KEY=<your PAPER secret>
ALPACA_PAPER=true
TICKERS=AAPL,MSFT,SPY
# optional brain:
AI_BRAIN_ENABLED=true
ANTHROPIC_API_KEY=<your Anthropic key>
```

Run it and watch:
```bash
python main.py --preflight    # read-only: confirms keys/account/data, NO orders
python main.py --cycles 8     # offline-style dry run
python main.py --once         # one real paper cycle (market hours)
python main.py --loop         # every CYCLE_MINUTES during market hours
```
Always run `--preflight` first after changing keys or mode — it confirms the
broker connects, the account is reachable/funded, and market data flows, without
placing a single order.

## 3. Going LIVE (real money) — deliberate two-step
Live is refused unless you do **both**:
```
ALPACA_API_KEY=<your LIVE key>
ALPACA_SECRET_KEY=<your LIVE secret>
ALPACA_PAPER=false
LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY
```
Then:
```bash
python main.py --preflight    # must report READY ✓ and "LIVE ARMED" before you trade
python main.py --once
```
The preflight must show your real account equity and `LIVE ARMED`. On the trading
run you'll then see a **LIVE REAL-MONEY TRADING ARMED** banner showing your
account equity and the active risk caps, with a 5-second window to Ctrl-C and
abort. If `LIVE_TRADING_ACK` is missing, the desk refuses to place live orders
and tells you how to enable it. (`ALPACA_PAPER=true` always keeps you on paper,
regardless of the ack.)

## 4. Risk controls (always on)
Hard ceilings in `config.py` cannot be widened from `.env` — only tightened:
- `HARD_MAX_ALLOCATION_PCT` — max % of equity in one position
- `HARD_MAX_TOTAL_DEPLOYED_PCT` — max % of equity deployed at once
- `HARD_MIN_CONVICTION` — never trade below this council conviction

Tighten your own caps in `.env`: `MAX_ALLOCATION_PCT`, `MAX_TOTAL_DEPLOYED_PCT`,
`MIN_COUNCIL_CONVICTION`.

## 5. Run it on a schedule
```bash
bash scripts/install_scheduler.sh   # every 15 min during market hours
```
Or keep `python main.py --loop` alive under a process manager (systemd, pm2,
`tmux`, a small VPS/Railway/Render worker).

## 6. Watch it
`python main.py` writes `public/status.json`, which the dashboard
(`public/index.html`) renders. Deploy `public/` to Vercel for a live view, or
just open the file locally.
