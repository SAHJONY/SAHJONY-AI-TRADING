"""Simulator venue — paper trading for any symbol, worldwide, fake money.

Wraps utils/sim_broker.SimBroker (synthetic price paths, realistic fills with
slippage + commission). This venue can NEVER be live: the mode is hard-coded
to "paper" and any attempt to configure it :live is forced back to paper with
a loud warning. It exists so Juan can test strategies on any market — stocks,
crypto, anything — with zero real money at risk.

Claims every symbol, so it is the catch-all when no real venue is configured.
"""
from __future__ import annotations

from config import Config
from utils.logger import get_logger
from utils.sim_broker import SimBroker
from venues.base import normalize_symbol

log = get_logger("venue_simulator")


class SimulatorVenue:
    venue_id = "simulator"
    kind = "sim"

    def __init__(self, cfg: Config, live_requested: bool = False):
        if live_requested:
            # Not a misconfiguration we silently accept: the simulator has no
            # live path at all, so :live here is always an operator mistake.
            log.warning("Simulator venue cannot be live — ignoring ':live' and "
                        "forcing PAPER (fail closed).")
        self._broker = SimBroker(cfg)
        self.tickers: list = []

    # ── BrokerAdapter surface (delegated; paper-only by construction) ────────
    @property
    def online(self) -> bool:
        return True   # the simulator is always "connected" to fake money

    @property
    def mode(self) -> str:
        return "paper"   # hard-coded — no live path exists

    @property
    def live_armed(self) -> bool:
        return False     # hard-coded — can never arm for real money

    def claims(self, symbol: str) -> bool:
        return bool((symbol or "").strip())

    def supports(self, symbol: str) -> bool:
        return normalize_symbol(symbol) in {normalize_symbol(s) for s in self.tickers}

    def get_account(self):
        return self._broker.get_account()

    def get_broker_positions(self):
        return self._broker.get_broker_positions()

    def get_history(self, symbol: str, days: int = 120):
        return self._broker.get_history(symbol, days)

    def get_price(self, symbol: str) -> float:
        return self._broker.get_price(symbol)

    def is_market_open(self) -> bool:
        return self._broker.is_market_open()

    def get_option_chain(self, symbol, spot, dte_min, dte_max, vol, kinds=("put", "call")):
        return self._broker.get_option_chain(symbol, spot, dte_min, dte_max, vol, kinds)

    def submit_equity_order(self, symbol: str, qty: float, side: str):
        res = self._broker.submit_equity_order(symbol, qty, side)
        res["venue"] = self.venue_id
        return res

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0):
        res = self._broker.submit_option_order(contract, qty, side, premium)
        res["venue"] = self.venue_id
        return res

    def advance_sim(self, steps: int = 1) -> None:
        return self._broker.advance_sim(steps)
