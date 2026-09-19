# Multi-Venue Trading — Operator Guide

## The honest reality

The bot's current Robinhood integration is **crypto-only**. Robinhood's
official Crypto Trading API physically cannot trade stocks — there is no
endpoint for it, and this is not something code can work around. Real stock
trading requires a **stock broker account with its own API** (e.g. Alpaca).

What this change delivers is **architecture, not a new live market**: the
desk is now venue-agnostic. Adding a market later is one credential away —
not a rewrite.

## How it works

```
VENUES="robinhood_crypto:live,alpaca:paper,simulator:paper"
```

- Each entry is `venue_id:mode`. Mode defaults to `paper` when omitted.
- **Unset/empty `VENUES`** → the desk behaves exactly as before
  (single broker from `BROKER`). The live Robinhood crypto path is untouched.
- The desk routes each symbol to the venue that owns it. A symbol no venue
  supports **fails closed**: no price, no order, loud log line.

| Venue | Kind | Trades | Live gate |
|---|---|---|---|
| `robinhood_crypto` | crypto | BTC/USD… (crypto only) | `ROBINHOOD_LIVE=true` + `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (unchanged) |
| `alpaca` | stocks + crypto | AAPL, MSFT… + BTC/USD… | `ALPACA_LIVE=true` + `ALPACA_LIVE_ACK=I_UNDERSTAND_REAL_MONEY` + desk-wide `LIVE_TRADING_ACK` |
| `simulator` | anything | any symbol, fake money | **never live — hard-coded paper** |

Per-venue tickers (optional): `TICKERS_ALPACA="AAPL,MSFT"`,
`TICKERS_ROBINHOOD_CRYPTO="BTC/USD,ETH/USD"`, `TICKERS_SIMULATOR="*"`.
Without them, tickers auto-assign from `TICKERS` in `VENUES` order. A venue
with an explicit list gets exactly those symbols.

Per-venue notional cap: `MAX_ORDER_USD_<VENUE>` (default $25), enforced by
the router on top of each adapter's own limits. Global risk caps
(70% deployed, 10% daily halt, etc.) still apply on the aggregate.

## Dashboard

The flagship dashboard shows a **Venues** strip: each venue's kind,
mode (LIVE/paper), connection status, equity, symbol count, and per-order
cap — all from `status.json` → `venues`.

## To enable REAL stock trading (Juan's steps)

1. **Open and fund a stock broker account.** Alpaca is the wired choice
   (alpaca.markets) — US stocks, paper trading included for testing.
2. **Create API keys** in the Alpaca dashboard (paper keys first).
3. **Add the secrets** to the desk's GitHub Actions secrets / environment:
   `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`.
4. **Test in paper**: `VENUES="alpaca:paper,simulator:paper"` with
   `TICKERS_ALPACA="AAPL,MSFT"`. Watch fills on the dashboard. $0 real risk.
5. **Go live only when ready**: set `ALPACA_LIVE=true` and
   `ALPACA_LIVE_ACK=I_UNDERSTAND_REAL_MONEY` (the exact phrase — anything
   else fails closed to paper), keep the desk-wide `LIVE_TRADING_ACK`, and
   give explicit approval for the go-live. There is no silent path to live.

Until step 5 is done deliberately, Alpaca is paper-only by construction.
