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

**The wrapper ships as `scripts/desk.sh`.** Each desk is a gitignored env file
in `desks/<name>.env` (copy the committed `*.env.example`) with its own
`SAHJONY_HOME` under `desks/homes/<name>`:

```bash
cp desks/robinhood-crypto.env.example desks/robinhood-crypto.env   # add RH keys
cp desks/alpaca-equities.env.example  desks/alpaca-equities.env    # add Alpaca keys

scripts/desk.sh robinhood-crypto --preflight   # read-only check (no orders)
scripts/desk.sh robinhood-crypto --loop &      # crypto desk, 24/7
scripts/desk.sh alpaca-equities  --loop &      # equities desk (paper), in parallel
scripts/desk.sh robinhood-crypto off           # per-desk kill switch (on|off|status)
```

The launcher never arms live trading — each desk arms only via the deliberate
opt-ins inside its own env file (GO_LIVE.md §D/§E), and the hard risk ceilings
apply per desk.

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

## Choosing a venue — `BROKER`
The Firm talks to brokers only through `BrokerAdapter` (`utils/broker.py`);
`get_broker(cfg)` picks one from `BROKER=<venue>`. Registered venues:

- ✅ **`alpaca`** (default) — US equities + US options (market hours) and crypto (24/7).
- ⚠️ **`ibkr`** — Interactive Brokers: worldwide equities, FX, futures via a
  running TWS / IB Gateway. **Wired but not yet validated against a live IBKR
  connection** — test on PAPER first (see below).
- ⚠️ **`ccxt`** — worldwide crypto via ~100 exchanges (Binance, Kraken, Coinbase,
  OKX, …). **Wired but not yet validated against a live exchange** — test on an
  exchange testnet first (see below).

### Interactive Brokers (`BROKER=ibkr`)
1. `pip install -r requirements-ibkr.txt` and start **TWS or IB Gateway**, with
   the API enabled. Paper ports: TWS 7497 / Gateway 4002. Live: 7496 / 4001.
2. Set `BROKER=ibkr`, `IBKR_PORT=<port>`, and your `TICKERS` using the symbol
   convention: `AAPL` · `LSE:VOD:GBP` · `FX:EUR/USD` · `CRYPTO:BTC/USD` · `FUT:ES@CME`.
3. For FX/futures/non-US, set `MARKET_HOURS=24_7` so the desk runs continuously
   (IBKR rejects genuinely-closed orders, which are caught + logged).
4. `python main.py --preflight` — must report connected + READY before you trade.
   Live still requires the `LIVE_TRADING_ACK` opt-in; a live IBKR port resolves to
   mode `LIVE` and triggers the same real-money gate as Alpaca.

If ib_insync isn't installed or TWS isn't running, the adapter falls back to
offline-sim (zero real orders) — never a real order by surprise.

### CCXT crypto exchanges (`BROKER=ccxt`)
1. `pip install -r requirements-ccxt.txt`.
2. Set `BROKER=ccxt`, `CCXT_EXCHANGE=<binance|kraken|coinbase|…>`, your
   `CCXT_API_KEY`/`CCXT_SECRET` (and `CCXT_PASSWORD` if the exchange needs one),
   and `TICKERS` in unified form (`BTC/USDT,ETH/USDT`). `CCXT_QUOTE` (default
   USDT) is the currency equity is valued in.
3. Keep `CCXT_SANDBOX=true` (testnet, mode → `paper`) until you've validated;
   `false` connects to the live exchange (mode → `LIVE`, requires `LIVE_TRADING_ACK`).
4. `python main.py --preflight` — must report connected + READY before trading.

Without ccxt installed or valid keys it falls back to offline-sim (zero real orders).

### Still not wired
Other venues — add them via the seam:
1. Copy `utils/brokers/template_adapter.py` → `utils/brokers/<venue>.py`.
2. Implement every method against the venue's SDK; wrap each external call so a
   failure logs and degrades to sim — never crashes the loop.
3. Register in `get_broker()`:  `if name == "<venue>": return _verify(MyBroker(cfg))`.
4. Select per desk with `BROKER=<venue>`.

The factory verifies an adapter implements the whole contract, so a half-built
venue fails fast. Risk caps, circuit breaker, kill switch, and the dashboard work
unchanged across venues.
