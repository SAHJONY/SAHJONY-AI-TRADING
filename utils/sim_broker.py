"""Offline simulator broker — the safe fallback for every adapter.

Deterministic geometric-Brownian price paths seeded per symbol+day, a $100k
simulated account, and orders that "fill" at the latest sim price. ZERO real
orders, ever. Any real broker adapter (Alpaca, IBKR, …) delegates to a SimBroker
when its SDK/credentials/connection are unavailable, so the trading loop always
has a working, side-effect-free backend instead of crashing (fault isolation).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

from config import Config
from intelligence import engines
from execution.cost_model import estimate_equity_fill, option_contract_fee
from utils.logger import get_logger

log = get_logger("sim_broker")

SIM_START_EQUITY = 100_000.0
_SIM_HISTORY = 180   # bars of synthetic history available at step 0
_SIM_HORIZON = 120   # additional bars the sim can walk forward


def seed(symbol: str) -> int:
    key = symbol + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


class SimBroker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.mode = "offline-sim"
        self._paths: Dict[str, np.ndarray] = {}
        self._vols: Dict[str, np.ndarray] = {}
        self._step = _SIM_HISTORY
        self._cash = SIM_START_EQUITY
        self._positions: Dict[str, Dict[str, float]] = {}

    @property
    def online(self) -> bool:
        return False

    def _ensure_path(self, symbol: str) -> None:
        if symbol in self._paths:
            return
        rng = np.random.default_rng(seed(symbol))
        n = _SIM_HISTORY + _SIM_HORIZON
        mu, sigma = 0.08 / engines.TRADING_DAYS, 0.28 / np.sqrt(engines.TRADING_DAYS)
        # occasional symbols get a drawdown bias so ladder/floor logic is exercised
        if rng.random() < 0.4:
            mu = -abs(mu) * 1.5
        shocks = rng.normal(mu, sigma, n)
        start = float(rng.uniform(40, 400))
        self._paths[symbol] = start * np.exp(np.cumsum(shocks))
        self._vols[symbol] = np.abs(rng.normal(0, 1, n)) * 1e6 + 5e5

    def advance_sim(self, steps: int = 1) -> None:
        self._step = min(self._step + steps, _SIM_HISTORY + _SIM_HORIZON)

    def get_account(self) -> Dict[str, float]:
        mtm = sum(pos["qty"] * self.get_price(sym) for sym, pos in self._positions.items())
        return {"equity": self._cash + mtm, "cash": self._cash, "buying_power": self._cash}

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        return {sym: dict(p) for sym, p in self._positions.items()}

    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        self._ensure_path(symbol)
        lo = max(0, self._step - days)
        return {"closes": self._paths[symbol][lo:self._step].copy(),
                "volumes": self._vols[symbol][lo:self._step].copy()}

    def get_price(self, symbol: str) -> float:
        self._ensure_path(symbol)
        return float(self._paths[symbol][self._step - 1])

    def is_market_open(self) -> bool:
        if self.cfg.always_on:   # 24/7 desk (crypto/FX) — never closed
            return True
        now = datetime.now(timezone.utc)   # offline approx: Mon-Fri ~13:30-20:00 UTC
        if now.weekday() >= 5:
            return False
        minutes = now.hour * 60 + now.minute
        return (13 * 60 + 30) <= minutes <= (20 * 60)

    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
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

    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        side = side.lower()
        if qty <= 0:
            return {"status": "rejected", "reason": "qty<=0"}
        reference_px = self.get_price(symbol)
        estimate = estimate_equity_fill(
            reference_px, qty, side,
            slippage_bps=self.cfg.sim_slippage_bps,
            commission_per_share=self.cfg.sim_commission_per_share,
        )
        px = estimate.fill_price
        pos = self._positions.setdefault(symbol, {"qty": 0.0, "avg_price": 0.0, "market_value": 0.0})
        if side == "buy":
            cost = px * qty
            new_qty = pos["qty"] + qty
            pos["avg_price"] = (pos["avg_price"] * pos["qty"] + cost) / new_qty if new_qty else px
            pos["qty"] = new_qty
            self._cash -= cost + estimate.commission
            if pos["qty"] == 0:              # buying back a short to flat
                self._positions.pop(symbol, None)
        else:
            new_qty = pos["qty"] - qty
            # Selling below flat opens/extends a SHORT: qty goes negative and is
            # marked to market as qty*price in get_account (the sale credited cash,
            # the negative position carries the liability). Mirrors Alpaca paper.
            if pos["qty"] >= 0 and new_qty < 0:
                pos["avg_price"] = px
            pos["qty"] = new_qty
            self._cash += px * qty - estimate.commission
            if pos["qty"] == 0:
                self._positions.pop(symbol, None)
        return {"status": "filled", "symbol": symbol, "qty": qty, "side": side,
                "fill_price": round(px, 6), "reference_price": round(reference_px, 6),
                "slippage_cost": round(estimate.slippage_cost, 6),
                "commission": round(estimate.commission, 6),
                "transaction_cost": round(estimate.transaction_cost, 6), "simulated": True}

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        side = side.lower()
        credit = premium * 100 * qty
        fee = option_contract_fee(qty, fee_per_contract=self.cfg.sim_option_fee_per_contract)
        if side in ("sell", "sell_to_open"):
            self._cash += credit
        self._cash -= fee
        return {"status": "filled", "contract": contract, "qty": qty, "side": side,
                "premium": premium, "credit": round(credit, 2),
                "commission": round(fee, 6), "transaction_cost": round(fee, 6),
                "simulated": True}
