"""CCXT adapter (BROKER=ccxt) — worldwide crypto exchanges, 24/7/365.

One adapter, ~100 exchanges (Binance, Kraken, Coinbase, OKX, Bybit, …) via the
unified ccxt library. If ccxt isn't installed or the exchange can't be reached,
it degrades to the shared SimBroker (zero real orders), like every adapter.

⚠️ UNTESTED AGAINST A LIVE EXCHANGE in this repo's CI. Written to the unified ccxt
API; validate against an exchange testnet/sandbox (and `--preflight`) before
trading real funds. See MULTI_ACCOUNT.md.

Symbols use ccxt's unified form: BTC/USDT, ETH/USD, SOL/USDT.
Set CCXT_SANDBOX=true to use the exchange's testnet where supported.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from config import Config
from utils.logger import get_logger
from utils.sim_broker import SimBroker

log = get_logger("ccxt")


class CCXTBroker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ex = None
        self._sim = SimBroker(cfg)
        self.mode = "offline-sim"
        self._connect()

    # ── connection ─────────────────────────────────────────────────────────────
    def _connect(self) -> None:
        if not (self.cfg.ccxt_api_key and self.cfg.ccxt_secret):
            log.warning("No CCXT credentials → OFFLINE-SIM mode (no real orders).")
            return
        try:
            import ccxt
            klass = getattr(ccxt, self.cfg.ccxt_exchange)
            params = {"apiKey": self.cfg.ccxt_api_key, "secret": self.cfg.ccxt_secret,
                      "enableRateLimit": True}
            if self.cfg.ccxt_password:
                params["password"] = self.cfg.ccxt_password
            ex = klass(params)
            if self.cfg.ccxt_sandbox:
                ex.set_sandbox_mode(True)
            ex.load_markets()
            self._ex = ex
            self.mode = "paper" if self.cfg.ccxt_sandbox else "LIVE"
            log.info("Connected to CCXT %s (%s).", self.cfg.ccxt_exchange, self.mode)
        except Exception as exc:  # library missing / bad keys / network → safe sim
            log.error("CCXT connect failed (%s) → OFFLINE-SIM (no real orders).", exc)
            self._ex = None
            self.mode = "offline-sim"

    @property
    def online(self) -> bool:
        return self._ex is not None

    def advance_sim(self, steps: int = 1) -> None:
        if not self.online:
            self._sim.advance_sim(steps)

    # ── account / positions ─────────────────────────────────────────────────────
    def get_account(self) -> Dict[str, float]:
        if not self.online:
            return self._sim.get_account()
        try:
            bal = self._ex.fetch_balance()
            totals = bal.get("total", {}) or {}
            free = bal.get("free", {}) or {}
            quote = self.cfg.ccxt_quote
            cash = float(free.get(quote, 0.0) or 0.0)
            equity = float(totals.get(quote, 0.0) or 0.0)
            for coin, amt in totals.items():       # mark non-quote holdings to market
                amt = float(amt or 0.0)
                if coin == quote or amt == 0:
                    continue
                equity += amt * self.get_price(f"{coin}/{quote}")
            return {"equity": equity, "cash": cash, "buying_power": cash}
        except Exception as exc:
            log.error("get_account failed: %s", exc)
            return {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        if not self.online:
            return self._sim.get_broker_positions()
        try:
            bal = self._ex.fetch_balance()
            quote = self.cfg.ccxt_quote
            out = {}
            for coin, amt in (bal.get("total", {}) or {}).items():
                amt = float(amt or 0.0)
                if coin == quote or amt == 0:
                    continue
                sym = f"{coin}/{quote}"
                px = self.get_price(sym)
                out[sym] = {"qty": amt, "avg_price": 0.0, "market_value": amt * px}
            return out
        except Exception as exc:
            log.error("positions failed: %s", exc)
            return {}

    # ── market data ──────────────────────────────────────────────────────────────
    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        if not self.online:
            return self._sim.get_history(symbol, days)
        try:
            ohlcv = self._ex.fetch_ohlcv(symbol, timeframe="1d", limit=days)
            closes = np.array([row[4] for row in ohlcv], dtype=float)
            vols = np.array([float(row[5]) for row in ohlcv], dtype=float)
            return {"closes": closes, "volumes": vols}
        except Exception as exc:
            log.error("get_history(%s) failed: %s", symbol, exc)
            return {"closes": np.array([]), "volumes": np.array([])}

    def get_price(self, symbol: str) -> float:
        if not self.online:
            return self._sim.get_price(symbol)
        try:
            t = self._ex.fetch_ticker(symbol)
            px = t.get("last") or t.get("close")
            if not px:
                bid, ask = t.get("bid"), t.get("ask")
                px = (bid + ask) / 2.0 if bid and ask else (bid or ask)
            return float(px or 0.0)
        except Exception as exc:
            log.error("get_price(%s) failed: %s", symbol, exc)
            return 0.0

    def is_market_open(self) -> bool:
        return True   # crypto exchanges trade 24/7/365

    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        return self._sim.get_option_chain(symbol, spot, dte_min, dte_max, vol, kinds)

    # ── orders ───────────────────────────────────────────────────────────────────
    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        side = side.lower()
        if qty <= 0:
            return {"status": "rejected", "reason": "qty<=0"}
        if not self.online:
            return self._sim.submit_equity_order(symbol, qty, side)
        try:
            amount = round(float(qty), 8)   # crypto is fractional
            order = (self._ex.create_market_buy_order(symbol, amount) if side == "buy"
                     else self._ex.create_market_sell_order(symbol, amount))
            oid = order.get("id", "")
            log.info("CCXT ORDER %s %s x%s id=%s", side, symbol, amount, oid)
            return {"status": "submitted", "id": str(oid), "symbol": symbol,
                    "qty": amount, "side": side, "simulated": False}
        except Exception as exc:
            log.error("submit_equity_order(%s) failed: %s", symbol, exc)
            return {"status": "error", "reason": str(exc)}

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        return self._sim.submit_option_order(contract, qty, side, premium)   # no spot-exchange options
