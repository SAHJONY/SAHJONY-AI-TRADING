"""Interactive Brokers adapter (BROKER=ibkr) — worldwide equities, FX, futures.

Connects to a running TWS or IB Gateway via ib_insync. If the library isn't
installed or no connection can be made, it degrades to the shared SimBroker
(zero real orders), exactly like the Alpaca adapter — the loop never crashes.

⚠️ UNTESTED AGAINST A LIVE IBKR CONNECTION in this repo's CI. It is written to
the documented ib_insync API, but you MUST validate it against a PAPER TWS/Gateway
(and `--preflight`) before trading real funds. See MULTI_ACCOUNT.md.

Symbol convention (unambiguous across global venues):
    AAPL              US stock (SMART routing, USD)
    LSE:VOD:GBP       stock VOD on exchange LSE in GBP   (EXCHANGE:SYMBOL[:CCY])
    FX:EUR/USD        spot forex
    CRYPTO:BTC/USD    crypto (PAXOS)
    FUT:ES@CME        continuous future ES on CME        (FUT:SYMBOL@EXCHANGE)

Ports: paper TWS 7497 / Gateway 4002 ; live TWS 7496 / Gateway 4001.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

from config import Config
from utils.logger import get_logger
from utils.sim_broker import SimBroker

log = get_logger("ibkr")

_PAPER_PORTS = {7497, 4002}
_LIVE_PORTS = {7496, 4001}


class IBKRBroker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ib = None
        self._sim = SimBroker(cfg)
        self._contracts: Dict[str, object] = {}
        self.mode = "offline-sim"
        self._connect()

    # ── connection ─────────────────────────────────────────────────────────────
    def _connect(self) -> None:
        try:
            from ib_insync import IB
            ib = IB()
            ib.connect(self.cfg.ibkr_host, self.cfg.ibkr_port,
                       clientId=self.cfg.ibkr_client_id, timeout=10)
            self._ib = ib
            self.mode = "LIVE" if self.cfg.ibkr_port in _LIVE_PORTS else "paper"
            log.info("Connected to IBKR %s:%s (%s).",
                     self.cfg.ibkr_host, self.cfg.ibkr_port, self.mode)
        except Exception as exc:  # library missing / TWS not running → safe sim
            log.error("IBKR connect failed (%s) → OFFLINE-SIM (no real orders).", exc)
            self._ib = None
            self.mode = "offline-sim"

    @property
    def online(self) -> bool:
        return self._ib is not None and getattr(self._ib, "isConnected", lambda: False)()

    def advance_sim(self, steps: int = 1) -> None:
        if not self.online:
            self._sim.advance_sim(steps)

    # ── symbol → IBKR contract ──────────────────────────────────────────────────
    def _contract(self, symbol: str):
        if symbol in self._contracts:
            return self._contracts[symbol]
        from ib_insync import Stock, Forex, Crypto, ContFuture
        try:
            if symbol.startswith("FX:"):
                c = Forex(symbol[3:].replace("/", ""))
            elif symbol.startswith("CRYPTO:"):
                base, quote = symbol[7:].split("/")
                c = Crypto(base, "PAXOS", quote)
            elif symbol.startswith("FUT:"):
                sym, _, exch = symbol[4:].partition("@")
                c = ContFuture(sym, exch or "CME")
            elif ":" in symbol:
                parts = symbol.split(":")
                exch, sym = parts[0], parts[1]
                ccy = parts[2] if len(parts) > 2 else "USD"
                c = Stock(sym, exch, ccy)
            else:
                c = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(c)
            self._contracts[symbol] = c
            return c
        except Exception as exc:
            log.error("contract(%s) failed: %s", symbol, exc)
            return None

    @staticmethod
    def _what_to_show(symbol: str) -> str:
        if symbol.startswith("FX:"):
            return "MIDPOINT"
        if symbol.startswith("CRYPTO:"):
            return "AGGTRADES"
        return "TRADES"

    # ── account / positions ─────────────────────────────────────────────────────
    def get_account(self) -> Dict[str, float]:
        if not self.online:
            return self._sim.get_account()
        try:
            tags = {"NetLiquidation": "equity", "TotalCashValue": "cash", "BuyingPower": "buying_power"}
            out = {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}
            for v in self._ib.accountSummary():
                if v.tag in tags and (not self.cfg.ibkr_account or v.account == self.cfg.ibkr_account):
                    out[tags[v.tag]] = float(v.value)
            return out
        except Exception as exc:
            log.error("get_account failed: %s", exc)
            return {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        if not self.online:
            return self._sim.get_broker_positions()
        try:
            out = {}
            for p in self._ib.positions():
                sym = p.contract.localSymbol or p.contract.symbol
                qty = float(p.position)
                out[sym] = {"qty": qty, "avg_price": float(p.avgCost),
                            "market_value": qty * float(p.avgCost)}
            return out
        except Exception as exc:
            log.error("positions failed: %s", exc)
            return {}

    # ── market data ──────────────────────────────────────────────────────────────
    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        if not self.online:
            return self._sim.get_history(symbol, days)
        try:
            c = self._contract(symbol)
            if c is None:
                return {"closes": np.array([]), "volumes": np.array([])}
            bars = self._ib.reqHistoricalData(
                c, endDateTime="", durationStr=f"{max(days + 10, 30)} D",
                barSizeSetting="1 day", whatToShow=self._what_to_show(symbol),
                useRTH=True, formatDate=1)
            closes = np.array([b.close for b in bars], dtype=float)
            vols = np.array([float(getattr(b, "volume", 0) or 0) for b in bars], dtype=float)
            timestamps = np.array([b.date for b in bars], dtype=object)
            return {"closes": closes[-days:], "volumes": vols[-days:],
                    "timestamps": timestamps[-days:],
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "exchange_timestamp": timestamps[-1] if timestamps.size else None}
        except Exception as exc:
            log.error("get_history(%s) failed: %s", symbol, exc)
            return {"closes": np.array([]), "volumes": np.array([])}

    def get_price(self, symbol: str) -> float:
        if not self.online:
            return self._sim.get_price(symbol)
        try:
            c = self._contract(symbol)
            if c is None:
                return 0.0
            [ticker] = self._ib.reqTickers(c)
            px = ticker.marketPrice()
            if px and px == px and px > 0:   # not NaN, positive
                return float(px)
            hist = self.get_history(symbol, 5)
            return float(hist["closes"][-1]) if hist["closes"].size else 0.0
        except Exception as exc:
            log.error("get_price(%s) failed: %s", symbol, exc)
            return 0.0

    def is_market_open(self) -> bool:
        # IBKR spans global venues with different hours; for FX/futures/non-US set
        # MARKET_HOURS=24_7 so the desk runs continuously and IBKR rejects any
        # genuinely-closed order (caught + logged). Otherwise use the US approx.
        if self.cfg.always_on:
            return True
        return self._sim.is_market_open()

    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        # Options via IBKR are not wired yet; synthesize so the wheel still models
        # premium. (Equity ladder is the primary IBKR strategy.)
        return self._sim.get_option_chain(symbol, spot, dte_min, dte_max, vol, kinds)

    # ── orders ───────────────────────────────────────────────────────────────────
    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        side = side.lower()
        if qty <= 0:
            return {"status": "rejected", "reason": "qty<=0"}
        if not self.online:
            return self._sim.submit_equity_order(symbol, qty, side)
        try:
            from ib_insync import MarketOrder
            c = self._contract(symbol)
            if c is None:
                return {"status": "error", "reason": "unresolved contract"}
            # whole units for stocks/futures; FX/crypto allow fractional
            fractional = symbol.startswith(("FX:", "CRYPTO:"))
            order_qty = round(float(qty), 6) if fractional else int(qty)
            if order_qty <= 0:
                return {"status": "rejected", "reason": "qty<=0"}
            order = MarketOrder("BUY" if side == "buy" else "SELL", order_qty)
            trade = self._ib.placeOrder(c, order)
            oid = getattr(trade.order, "orderId", "")
            log.info("IBKR ORDER %s %s x%s id=%s", side, symbol, order_qty, oid)
            return {"status": "submitted", "id": str(oid), "symbol": symbol,
                    "qty": order_qty, "side": side, "simulated": False}
        except Exception as exc:
            log.error("submit_equity_order(%s) failed: %s", symbol, exc)
            return {"status": "error", "reason": str(exc)}

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        # No IBKR options wiring yet → simulate the premium leg (never a real order).
        return self._sim.submit_option_order(contract, qty, side, premium)
