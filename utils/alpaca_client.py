"""Unified Alpaca connection client.

One interface, two backends:
  • PAPER/LIVE — real Alpaca via alpaca-py (account, quotes, bars, orders, clock).
  • OFFLINE-SIM — when no credentials (or the SDK is unavailable): deterministic
    geometric-Brownian price paths seeded per symbol+day, a $100k simulated
    account, and orders that "fill" at the latest sim price. ZERO real orders.

Every external call is wrapped so a failure logs and returns a safe default
instead of crashing the orchestrator loop (fault isolation).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from config import Config
from intelligence import engines
from utils.logger import get_logger

log = get_logger("alpaca_client")

SIM_START_EQUITY = 100_000.0
_SIM_HISTORY = 180   # bars of synthetic history available at step 0
_SIM_HORIZON = 120   # additional bars the sim can walk forward


def _seed(symbol: str) -> int:
    key = symbol + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


class AlpacaClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.mode = cfg.mode
        self._trading = None
        self._data = None
        self._sim_paths: Dict[str, np.ndarray] = {}
        self._sim_vols: Dict[str, np.ndarray] = {}
        self._sim_step = _SIM_HISTORY
        self._sim_cash = SIM_START_EQUITY
        self._sim_positions: Dict[str, Dict[str, float]] = {}

        if cfg.has_credentials:
            self._connect_live()
        else:
            log.warning("No Alpaca credentials → OFFLINE-SIM mode (no real orders).")

    # ── connection ───────────────────────────────────────────────────────────
    def _connect_live(self) -> None:
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient
            self._trading = TradingClient(self.cfg.alpaca_api_key, self.cfg.alpaca_secret_key,
                                          paper=self.cfg.alpaca_paper)
            self._data = StockHistoricalDataClient(self.cfg.alpaca_api_key, self.cfg.alpaca_secret_key)
            log.info("Connected to Alpaca (%s).", self.mode)
        except Exception as exc:  # SDK missing / bad keys → degrade gracefully
            log.error("Alpaca connect failed (%s) → falling back to OFFLINE-SIM.", exc)
            self._trading = None
            self._data = None
            self.mode = "offline-sim"

    @property
    def online(self) -> bool:
        return self._trading is not None

    # ── sim machinery ─────────────────────────────────────────────────────────
    def _ensure_sim_path(self, symbol: str) -> None:
        if symbol in self._sim_paths:
            return
        rng = np.random.default_rng(_seed(symbol))
        n = _SIM_HISTORY + _SIM_HORIZON
        mu, sigma = 0.08 / engines.TRADING_DAYS, 0.28 / np.sqrt(engines.TRADING_DAYS)
        # occasional symbols get a drawdown bias so ladder/floor logic is exercised
        if rng.random() < 0.4:
            mu = -abs(mu) * 1.5
        shocks = rng.normal(mu, sigma, n)
        start = float(rng.uniform(40, 400))
        path = start * np.exp(np.cumsum(shocks))
        self._sim_paths[symbol] = path
        self._sim_vols[symbol] = np.abs(rng.normal(0, 1, n)) * 1e6 + 5e5  # volumes

    def advance_sim(self, steps: int = 1) -> None:
        """Walk the simulated clock forward (dry-run only)."""
        if not self.online:
            self._sim_step = min(self._sim_step + steps, _SIM_HISTORY + _SIM_HORIZON)

    # ── account ────────────────────────────────────────────────────────────────
    def get_account(self) -> Dict[str, float]:
        if self.online:
            try:
                a = self._trading.get_account()
                return {"equity": float(a.equity), "cash": float(a.cash),
                        "buying_power": float(a.buying_power)}
            except Exception as exc:
                log.error("get_account failed: %s", exc)
                return {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}
        # sim: equity = cash + mark-to-market of sim positions
        mtm = 0.0
        for sym, pos in self._sim_positions.items():
            mtm += pos["qty"] * self.get_price(sym)
        eq = self._sim_cash + mtm
        return {"equity": eq, "cash": self._sim_cash, "buying_power": self._sim_cash}

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        if self.online:
            try:
                out = {}
                for p in self._trading.get_all_positions():
                    out[p.symbol] = {"qty": float(p.qty), "avg_price": float(p.avg_entry_price),
                                     "market_value": float(p.market_value)}
                return out
            except Exception as exc:
                log.error("get_all_positions failed: %s", exc)
                return {}
        return {sym: dict(p) for sym, p in self._sim_positions.items()}

    # ── market data ──────────────────────────────────────────────────────────
    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        if self.online:
            try:
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.timeframe import TimeFrame
                from datetime import timedelta
                req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
                                       start=datetime.now(timezone.utc) - timedelta(days=days + 10))
                bars = self._data.get_stock_bars(req).data.get(symbol, [])
                closes = np.array([b.close for b in bars], dtype=float)
                vols = np.array([float(b.volume) for b in bars], dtype=float)
                return {"closes": closes[-days:], "volumes": vols[-days:]}
            except Exception as exc:
                log.error("get_history(%s) failed: %s", symbol, exc)
                return {"closes": np.array([]), "volumes": np.array([])}
        self._ensure_sim_path(symbol)
        lo = max(0, self._sim_step - days)
        return {"closes": self._sim_paths[symbol][lo:self._sim_step].copy(),
                "volumes": self._sim_vols[symbol][lo:self._sim_step].copy()}

    def get_price(self, symbol: str) -> float:
        if self.online:
            try:
                from alpaca.data.requests import StockLatestQuoteRequest
                q = self._data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))
                quote = q[symbol]
                mid = (float(quote.ask_price) + float(quote.bid_price)) / 2.0
                return mid if mid > 0 else float(quote.ask_price or quote.bid_price)
            except Exception as exc:
                log.error("get_price(%s) failed: %s", symbol, exc)
                hist = self.get_history(symbol, 5)
                return float(hist["closes"][-1]) if hist["closes"].size else 0.0
        self._ensure_sim_path(symbol)
        return float(self._sim_paths[symbol][self._sim_step - 1])

    def is_market_open(self) -> bool:
        if self.online:
            try:
                return bool(self._trading.get_clock().is_open)
            except Exception as exc:
                log.error("get_clock failed: %s", exc)
        # offline approximation: Mon-Fri, ~13:30-20:00 UTC (US cash session)
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:
            return False
        minutes = now.hour * 60 + now.minute
        return (13 * 60 + 30) <= minutes <= (20 * 60)

    # ── options chain (normalized; synthesized in sim / on failure) ───────────
    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        if self.online:
            chain = self._live_option_chain(symbol, dte_min, dte_max, kinds)
            if chain:
                return chain
            log.warning("Live option chain empty for %s → synthesizing from BS.", symbol)
        return self._synth_option_chain(symbol, spot, dte_min, dte_max, vol, kinds)

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

    def _synth_option_chain(self, symbol, spot, dte_min, dte_max, vol, kinds) -> List[Dict]:
        if spot <= 0:
            return []
        vol = max(0.05, vol or 0.25)
        dte = int(round((dte_min + dte_max) / 2))
        T = dte / 365.0
        out = []
        for mult in np.arange(0.80, 1.21, 0.05):
            strike = round(spot * mult, 2)
            for kind in kinds:
                price = engines.bs_price(spot, strike, T, vol, kind)
                delta = engines.bs_delta(spot, strike, T, vol, kind)
                spread = max(0.02, price * 0.04)
                out.append({
                    "contract": f"{symbol}-SIM-{kind[0].upper()}{strike}-{dte}d",
                    "strike": strike, "expiry": f"+{dte}d", "dte": dte, "type": kind,
                    "bid": round(max(0.0, price - spread / 2), 2),
                    "ask": round(price + spread / 2, 2),
                    "mid": round(max(0.0, price), 2),
                    "delta": round(delta, 4), "iv": round(vol, 4), "source": "synthetic",
                })
        return out

    # ── orders ─────────────────────────────────────────────────────────────────
    def submit_equity_order(self, symbol: str, qty: int, side: str) -> Dict:
        side = side.lower()
        if qty <= 0:
            return {"status": "rejected", "reason": "qty<=0"}
        if self.online:
            try:
                from alpaca.trading.requests import MarketOrderRequest
                from alpaca.trading.enums import OrderSide, TimeInForce
                order = self._trading.submit_order(MarketOrderRequest(
                    symbol=symbol, qty=qty,
                    side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                    time_in_force=TimeInForce.DAY))
                log.info("ORDER %s %s x%d submitted id=%s", side, symbol, qty, order.id)
                return {"status": "submitted", "id": str(order.id), "symbol": symbol,
                        "qty": qty, "side": side, "simulated": False}
            except Exception as exc:
                log.error("submit_equity_order(%s) failed: %s", symbol, exc)
                return {"status": "error", "reason": str(exc)}
        # sim fill at latest price
        px = self.get_price(symbol)
        pos = self._sim_positions.setdefault(symbol, {"qty": 0.0, "avg_price": 0.0, "market_value": 0.0})
        if side == "buy":
            cost = px * qty
            new_qty = pos["qty"] + qty
            pos["avg_price"] = (pos["avg_price"] * pos["qty"] + cost) / new_qty if new_qty else px
            pos["qty"] = new_qty
            self._sim_cash -= cost
        else:
            pos["qty"] = max(0.0, pos["qty"] - qty)
            self._sim_cash += px * qty
            if pos["qty"] == 0:
                self._sim_positions.pop(symbol, None)
        return {"status": "filled", "symbol": symbol, "qty": qty, "side": side,
                "fill_price": round(px, 2), "simulated": True}

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        side = side.lower()
        if self.online:
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
        credit = premium * 100 * qty
        if side in ("sell", "sell_to_open"):
            self._sim_cash += credit
        return {"status": "filled", "contract": contract, "qty": qty, "side": side,
                "premium": premium, "credit": round(credit, 2), "simulated": True}
