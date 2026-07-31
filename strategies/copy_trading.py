"""Copy-trading engine — mirror an external signal source (e.g. politician /
congressional disclosure feeds) into risk-gated OrderIntents.

Per the project blueprint's Copy Trading component. Kept faithful to the house
rules: it is a PURE decision engine plus one fault-isolated fetch — it never
touches the broker or DB directly. Every mirrored trade still flows through the
Risk Officer (allocation caps, hard ceilings, conviction floor) and the
Execution Trader, exactly like the wheel and ladder desks.

Signal source is configurable and supplies NO credentials in the repo:
  COPY_TRADING_ENABLED=true
  COPY_TRADING_SOURCE_URL=https://…           # JSON: [{"symbol","side","weight"?}]
  COPY_TRADING_API_KEY=…                       # optional bearer, from .env only
Public disclosure aggregators (CapitolTrades/Quiver/Unusual Whales/etc.) change
formats and terms often; this adapter normalizes a simple JSON shape and degrades
to an empty signal list on any error so the trading loop never breaks.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import Config
from strategies.base import OrderIntent, is_crypto, size_qty
from utils.logger import get_logger

log = get_logger("copy_trading")

# Crypto-only venues cannot price or trade equities. Public-disclosure feeds
# (SEC Form 4 insider buys, congressional filings) are almost all equities, so
# on these venues we drop non-crypto symbols before pricing them — otherwise
# each one hits the crypto marketdata endpoint and logs a spurious
# "Invalid symbol" error every cycle.
_CRYPTO_ONLY_BROKERS = frozenset({"robinhood_crypto", "robinhood", "ccxt"})
# Placeholder tickers seen in disclosure feeds — never tradeable.
_JUNK_TICKERS = {"NONE", "N/A", "NA", "-", "--", "NULL", "UNKNOWN", "TBD", ""}


class CopyTrader:
    name = "Copy Trading Desk"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.stop_pct = abs(float(getattr(cfg, "copy_stop_pct", 0.15) or 0.0))
        self.trail_trigger = abs(float(getattr(cfg, "copy_trail_trigger_pct", 0.15) or 0.0))
        self.trail_pct = abs(float(getattr(cfg, "copy_trail_pct", 0.08) or 0.0))

    # ── protective exits (feed-independent) ────────────────────────────────────
    def manage(self, state: Dict[str, Any], get_price) -> List[OrderIntent]:
        """Risk-manage held copy positions WITHOUT depending on the signal feed.

        The desk used to exit only when a mirrored SELL arrived, so a position was
        orphaned whenever the source stopped publishing (or 404'd) — one name rode
        -56% with nothing to stop it. Every other desk has a protective floor;
        this gives the copy desk the same discipline:
          • hard stop at COPY_STOP_PCT below the cost basis, and
          • a ratchet trailing stop once the position is up COPY_TRAIL_TRIGGER_PCT.
        Exits are risk-REDUCING, so they still flow while new risk is halted.
        """
        out: List[OrderIntent] = []
        for sym, pos in list((state.get("positions") or {}).items()):
            if pos.get("strategy") != "copy":
                continue
            shares = float(pos.get("shares", 0) or 0)
            if shares <= 0:
                continue
            try:
                price = float(get_price(sym))
            except Exception:
                price = 0.0
            if price <= 0:            # bad tick: never liquidate on a zero price
                continue
            basis = float(pos.get("cost_basis") or pos.get("entry_price") or price)
            if basis <= 0:
                continue
            peak = max(float(pos.get("peak", basis) or basis), price)
            ret = price / basis - 1.0
            trail_floor = (peak * (1.0 - self.trail_pct)
                           if (peak / basis - 1.0) >= self.trail_trigger else None)

            if self.stop_pct and ret <= -self.stop_pct:
                why = f"hard stop {ret:+.1%} (limit -{self.stop_pct:.0%}) — feed-independent"
            elif trail_floor is not None and price <= trail_floor:
                why = (f"trailing stop — peak ${peak:,.2f}, floor ${trail_floor:,.2f}, "
                       f"locked {ret:+.1%}")
            else:
                out.append(OrderIntent(
                    sym, "copy", "state", "copy_hold",
                    reason=f"{ret:+.1%} vs basis, peak ${peak:,.2f}",
                    merge_position={"peak": peak}))
                continue

            out.append(OrderIntent(
                sym, "copy", "equity", "copy_stop", side="sell", reason=why,
                qty=shares, est_notional=0.0, risk_check=False,
                realized_delta=(price - basis) * shares if not is_crypto(sym) else 0.0,
                clear_position=True))
        return out

    # ── source ingestion (fault-isolated I/O) ──────────────────────────────────
    def fetch_signals(self) -> List[Dict[str, Any]]:
        """Pull recent target transactions; return normalized signals or []."""
        url = getattr(self.cfg, "copy_trading_source_url", "")
        if not (getattr(self.cfg, "copy_trading_enabled", False) and url):
            return []
        try:
            import requests
            headers = {"Accept": "application/json"}
            key = getattr(self.cfg, "copy_trading_api_key", "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            rows = data if isinstance(data, list) else data.get("data") or data.get("trades") or []
            return self._normalize(rows)
        except Exception as exc:   # network/format failure never sinks the cycle
            log.warning("copy-trading fetch failed (%s) — trying the local snapshot", exc)
            return self._local_signals()

    def _local_signals(self) -> List[Dict[str, Any]]:
        """Fallback to the snapshot this repo publishes each cycle.

        The configured URL points at the deployed dashboard, which can 404 while
        a deploy is stale. `public/copy_signals.json` is regenerated in-repo every
        run, so read it directly rather than losing the feed entirely.
        """
        import json
        import os
        for path in ("public/copy_signals.json",
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "public", "copy_signals.json")):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    rows = json.load(fh)
                rows = rows if isinstance(rows, list) else rows.get("data") or []
                sigs = self._normalize(rows)
                if sigs:
                    log.info("copy-trading: using local snapshot (%d signal(s))", len(sigs))
                return sigs
            except Exception:
                continue
        return []

    @staticmethod
    def _normalize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for x in rows or []:
            sym = str(x.get("symbol") or x.get("ticker") or "").upper().strip()
            raw = str(x.get("side") or x.get("type") or x.get("transaction") or "").lower()
            # SEC filings carry placeholder tickers ("NONE", "N/A", "-"): mirroring
            # those would send orders for securities that do not exist.
            if not sym or sym in _JUNK_TICKERS or not sym.replace(".", "").replace("-", "").isalnum():
                continue
            side = "buy" if any(k in raw for k in ("buy", "purchase", "long")) else \
                   "sell" if any(k in raw for k in ("sell", "sale", "short")) else ""
            if not side:
                continue
            out.append({"symbol": sym, "side": side, "weight": float(x.get("weight", 1.0) or 1.0),
                        "source": x.get("source") or x.get("politician") or x.get("name") or "filing"})
        return out

    # ── pure decision logic ────────────────────────────────────────────────────
    def decide(self, signals: List[Dict[str, Any]], state: Dict[str, Any],
               equity: float, get_price) -> List[OrderIntent]:
        """Turn signals into OrderIntents: buy → open/add (risk-gated); sell →
        close a held position. Buys are sized to the per-position budget."""
        intents: List[OrderIntent] = []
        positions = state.get("positions", {})
        cap = max(0, int(getattr(self.cfg, "copy_trading_max_symbols", 10)))
        budget_each = equity * self.cfg.max_allocation_pct
        seen = set()
        crypto_only = getattr(self.cfg, "broker", "") in _CRYPTO_ONLY_BROKERS
        for s in signals:
            sym = s["symbol"]
            if crypto_only and not is_crypto(sym):
                continue  # equity filing on a crypto-only venue — cannot trade
            if sym in seen:
                continue
            seen.add(sym)
            if len(seen) > cap:
                break
            try:
                price = float(get_price(sym))
            except Exception:
                price = 0.0
            held = positions.get(sym, {})
            shares_held = float(held.get("shares", 0) or 0)
            if s["side"] == "buy":
                if price <= 0:
                    continue
                qty = size_qty(sym, budget_each * min(1.0, s.get("weight", 1.0)), price,
                               int(budget_each // price) if price else 0, self.cfg.allow_fractional)
                if qty <= 0:
                    continue
                # Weighted-average the cost basis when adding to an existing copy
                # position — using the new fill price alone would erase the basis
                # of the shares already held and corrupt copy_exit's realized P&L.
                new_shares = shares_held + qty
                prior_basis = float(held.get("cost_basis", 0.0) or 0.0)
                new_basis = ((prior_basis * shares_held) + (price * qty)) / new_shares \
                    if new_shares else price
                intents.append(OrderIntent(
                    sym, "copy", "equity", "copy_buy", side="buy",
                    reason=f"mirror {s.get('source','filing')} buy {qty} @ {price:.2f}",
                    qty=qty, est_notional=qty * price, risk_check=True,
                    set_position={"strategy": "copy", "shares": new_shares,
                                  "entry_price": float(held.get("entry_price", price) or price),
                                  "cost_basis": new_basis}))
            elif s["side"] == "sell" and shares_held > 0:
                intents.append(OrderIntent(
                    sym, "copy", "equity", "copy_exit", side="sell",
                    reason=f"mirror {s.get('source','filing')} sell {shares_held}",
                    qty=shares_held, est_notional=0.0, risk_check=False,
                    realized_delta=(float(get_price(sym)) - float(held.get("cost_basis", price))) * shares_held
                    if not is_crypto(sym) else 0.0,
                    clear_position=True))
        return intents
