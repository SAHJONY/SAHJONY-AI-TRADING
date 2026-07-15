"""Alpaca broker adapter.

One interface, two backends:
  • PAPER/LIVE — real Alpaca via alpaca-py (account, quotes, bars, orders, clock,
    options chain) for US equities/options and 24/7 crypto.
  • OFFLINE-SIM — when no credentials (or the SDK is unavailable): delegates to a
    shared SimBroker (synthetic prices, $100k paper account, ZERO real orders).

Every external call is wrapped so a failure logs and returns a safe default
instead of crashing the orchestrator loop (fault isolation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

from config import Config
from utils.logger import get_logger
from utils.sim_broker import SimBroker

log = get_logger("alpaca_client")


def _is_crypto(symbol: str) -> bool:
    """Alpaca crypto pairs are BASE/QUOTE (e.g. BTC/USD) and trade 24/7/365."""
    return "/" in symbol


class AlpacaClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.mode = cfg.mode
        self._trading = None
        self._data = None
        self._crypto = None
        self._sim = SimBroker(cfg)   # safe offline fallback

        if cfg.has_credentials:
            self._connect_live()
        else:
            log.warning("No Alpaca credentials → OFFLINE-SIM mode (no real orders).")

    # ── connection ───────────────────────────────────────────────────────────
    def _connect_live(self) -> None:
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
            self._trading = TradingClient(self.cfg.alpaca_api_key, self.cfg.alpaca_secret_key,
                                          paper=self.cfg.alpaca_paper)
            self._data = StockHistoricalDataClient(self.cfg.alpaca_api_key, self.cfg.alpaca_secret_key)
            self._crypto = CryptoHistoricalDataClient(self.cfg.alpaca_api_key, self.cfg.alpaca_secret_key)
            log.info("Connected to Alpaca (%s).", self.mode)
        except Exception as exc:  # SDK missing / bad keys → degrade gracefully
            log.error("Alpaca connect failed (%s) → falling back to OFFLINE-SIM.", exc)
            self._trading = None
            self._data = None
            self.mode = "offline-sim"

    @property
    def online(self) -> bool:
        return self._trading is not None

    def advance_sim(self, steps: int = 1) -> None:
        if not self.online:
            self._sim.advance_sim(steps)

    # ── account ────────────────────────────────────────────────────────────────
    def get_account(self) -> Dict[str, float]:
        if not self.online:
            return self._sim.get_account()
        try:
            a = self._trading.get_account()
            return {"equity": float(a.equity), "cash": float(a.cash),
                    "buying_power": float(a.buying_power)}
        except Exception as exc:
            log.error("get_account failed: %s", exc)
            return {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        if not self.online:
            return self._sim.get_broker_positions()
        try:
            out = {}
            for p in self._trading.get_all_positions():
                out[p.symbol] = {"qty": float(p.qty), "avg_price": float(p.avg_entry_price),
                                 "market_value": float(p.market_value)}
            return out
        except Exception as exc:
            log.error("get_all_positions failed: %s", exc)
            return {}

    # ── market data ──────────────────────────────────────────────────────────
    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        if not self.online:
            return self._sim.get_history(symbol, days)
        try:
            from alpaca.data.timeframe import TimeFrame
            from datetime import timedelta
            start = datetime.now(timezone.utc) - timedelta(days=days + 10)
            if _is_crypto(symbol):
                from alpaca.data.requests import CryptoBarsRequest
                req = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start)
                bars = self._crypto.get_crypto_bars(req).data.get(symbol, [])
            else:
                from alpaca.data.requests import StockBarsRequest
                req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start)
                bars = self._data.get_stock_bars(req).data.get(symbol, [])
            closes = np.array([b.close for b in bars], dtype=float)
            vols = np.array([float(b.volume) for b in bars], dtype=float)
            timestamps = np.array([b.timestamp for b in bars], dtype=object)
            retrieved_at = datetime.now(timezone.utc).isoformat()
            return {"closes": closes[-days:], "volumes": vols[-days:],
                    "timestamps": timestamps[-days:], "retrieved_at": retrieved_at,
                    "exchange_timestamp": (timestamps[-1].isoformat() if timestamps.size else None)}
        except Exception as exc:
            log.error("get_history(%s) failed: %s", symbol, exc)
            return {"closes": np.array([]), "volumes": np.array([])}

    def get_price(self, symbol: str) -> float:
        if not self.online:
            return self._sim.get_price(symbol)
        try:
            if _is_crypto(symbol):
                from alpaca.data.requests import CryptoLatestQuoteRequest
                q = self._crypto.get_crypto_latest_quote(
                    CryptoLatestQuoteRequest(symbol_or_symbols=symbol))
            else:
                from alpaca.data.requests import StockLatestQuoteRequest
                q = self._data.get_stock_latest_quote(
                    StockLatestQuoteRequest(symbol_or_symbols=symbol))
            quote = q[symbol]
            mid = (float(quote.ask_price) + float(quote.bid_price)) / 2.0
            return mid if mid > 0 else float(quote.ask_price or quote.bid_price)
        except Exception as exc:
            log.error("get_price(%s) failed: %s", symbol, exc)
            hist = self.get_history(symbol, 5)
            return float(hist["closes"][-1]) if hist["closes"].size else 0.0

    def is_market_open(self) -> bool:
        if self.cfg.always_on:   # 24/7 desk (crypto) — never closed
            return True
        if self.online:
            try:
                return bool(self._trading.get_clock().is_open)
            except Exception as exc:
                log.error("get_clock failed: %s", exc)
        return self._sim.is_market_open()

    # ── options chain (normalized; synthesized in sim / on failure) ───────────
    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        if self.online:
            chain = self._live_option_chain(symbol, dte_min, dte_max, kinds)
            if chain:
                return chain
            log.warning("Live option chain empty for %s → synthesizing from BS.", symbol)
        return self._sim.get_option_chain(symbol, spot, dte_min, dte_max, vol, kinds)

    def _live_option_chain(self, symbol, dte_min, dte_max, kinds) -> List[Dict]:
        try:
            from alpaca.trading.requests import GetOptionContractsRequest
            from datetime import timedelta
            today = datetime.now(timezone.utc).date()
            req = GetOptionContractsRequest(
                underlying_symbols=[symbol],
                expiration_date_gte=today + timedelta(days=dte_min),
                expiration_date_lte=today + timedelta(days=dte_max),
                limit=500,
            )
            contracts = self._trading.get_option_contracts(req).option_contracts or []
            out = []
            for c in contracts:
                kind = str(getattr(c, "type", "")).lower().split(".")[-1]
                if kind not in kinds:
                    continue
                strike = float(c.strike_price)
                exp = c.expiration_date
                dte = (exp - today).days if hasattr(exp, "year") else dte_min
                out.append({"contract": c.symbol, "strike": strike, "expiry": str(exp),
                            "dte": int(dte), "type": kind, "bid": 0.0, "ask": 0.0,
                            "mid": 0.0, "delta": 0.0, "iv": 0.0, "source": "alpaca"})
            return out
        except Exception as exc:
            log.error("live option chain(%s) failed: %s", symbol, exc)
            return []

    # ── orders ─────────────────────────────────────────────────────────────────
    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        side = side.lower()
        if qty <= 0:
            return {"status": "rejected", "reason": "qty<=0"}
        if not self.online:
            return self._sim.submit_equity_order(symbol, qty, side)
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            crypto = _is_crypto(symbol)
            # crypto requires GTC + fractional; equities use DAY. Fractional equity
            # orders (dollar-investing) are allowed when ALLOW_FRACTIONAL is on.
            frac_equity = getattr(self.cfg, "allow_fractional", False)
            order_qty = round(float(qty), 6) if (crypto or frac_equity) else int(qty)
            if order_qty <= 0:
                return {"status": "rejected", "reason": "qty<=0"}
            order = self._trading.submit_order(MarketOrderRequest(
                symbol=symbol, qty=order_qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.GTC if crypto else TimeInForce.DAY))
            log.info("ORDER %s %s x%s submitted id=%s", side, symbol, order_qty, order.id)
            return {"status": "submitted", "id": str(order.id), "symbol": symbol,
                    "qty": order_qty, "side": side, "simulated": False}
        except Exception as exc:
            log.error("submit_equity_order(%s) failed: %s", symbol, exc)
            return {"status": "error", "reason": str(exc)}

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        side = side.lower()
        if not self.online:
            return self._sim.submit_option_order(contract, qty, side, premium)
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            order = self._trading.submit_order(MarketOrderRequest(
                symbol=contract, qty=qty,
                side=OrderSide.SELL if side in ("sell", "sell_to_open") else OrderSide.BUY,
                time_in_force=TimeInForce.DAY))
            log.info("OPTION ORDER %s %s x%d id=%s", side, contract, qty, order.id)
            return {"status": "submitted", "id": str(order.id), "contract": contract,
                    "qty": qty, "side": side, "simulated": False}
        except Exception as exc:
            log.error("submit_option_order(%s) failed: %s", contract, exc)
            return {"status": "error", "reason": str(exc)}
