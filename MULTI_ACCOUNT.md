# Running multiple accounts & 24/7 crypto

You can run several **independent** desks at once — each its own Alpaca account,
its own keys, its own state and kill switch. Two building blocks make this work.

## 1. Account isolation — `SAHJONY_HOME`
By default a desk keeps everything under the repo root (`state.json`,
`data/sahjony.db`, `public/status.json`, `HALT`). Set `SAHJONY_HOME` to give a
desk its own home so two desks never collide:

```bash
# Account A — US equities, market-hours
SAHJONY_HOME=~/desks/us   ALPACA_API_KEY=… ALPACA_SECRET_KEY=… \
  TICKERS=AAPL,MSFT,SPY   python main.py --loop

# Account B — crypto, 24/7, different keys
SAHJONY_HOME=~/desks/btc  ALPACA_API_KEY=… ALPACA_SECRET_KEY=… \
  TICKERS=BTC/USD,ETH/USD python main.py --loop
```

In practice put each account's settings in its own `.env` and point a small
wrapper/cron at it. Each home has its **own** `HALT` file, so you can stop one
account (`touch ~/desks/btc/HALT`) without touching the others. Separate
processes run genuinely in parallel.

## 2. 24/7/365 trading — crypto
Crypto markets never close, so a crypto desk trades around the clock.

- **How to enable:** put crypto pairs (`BTC/USD`, `ETH/USD`, `SOL/USD`, …) in
  `TICKERS`. Any `/` pair auto-enables 24/7 (`market_hours` → `24_7`), so the
  desk skips the US-session gate. You can also force it with `MARKET_HOURS=24_7`.
- **What happens:** the broker adapter routes crypto to Alpaca's crypto data +
  orders (fractional qty, GTC time-in-force). The Portfolio Manager assigns
  crypto to the **ladder** strategy — options/the wheel are equities-only.
- **Cadence:** run `python main.py --loop` (or a frequent cron). `CYCLE_MINUTES`
  sets the tick; the market-open gate is always true for a crypto desk.
- **Don't mix asset classes in one desk.** Run a US-equity desk and a crypto
  desk as two isolated `SAHJONY_HOME`s instead.

Everything else is identical: the same risk caps, the daily circuit breaker, the
kill switch, the live opt-in gate, and `--preflight` all apply per desk.

## Scope — what "worldwide markets" means today
- ✅ **US equities + US options** (Alpaca) — market hours.
- ✅ **Crypto** (Alpaca) — true 24/7/365.
- ❌ **Non-US equities (Tokyo/London/…), forex, futures, other brokers (IBKR…)**
  — NOT wired, but the seam is in place.

## Adding a venue (the broker adapter seam)
The Firm talks to brokers only through `BrokerAdapter` (`utils/broker.py`), and
`get_broker(cfg)` picks one from `BROKER=<venue>`. To add Interactive Brokers
(FX/futures/non-US equities) or a CCXT exchange (worldwide crypto):

1. Copy `utils/brokers/template_adapter.py` to `utils/brokers/<venue>.py`.
2. Implement every method against the venue's SDK (wrap each external call so a
   failure logs and degrades — never crashes the loop). Mirror `utils/alpaca_client.py`.
3. Register it in `get_broker()`:  `if name == "<venue>": return _verify(MyBroker(cfg))`.
4. Select it per desk with `BROKER=<venue>` in that desk's `.env`.

The factory verifies an adapter implements the whole contract, so a half-built
venue fails fast instead of breaking mid-cycle. Everything else — risk caps,
circuit breaker, kill switch, dashboard — works unchanged across venues.
