"""Alpaca venue — US stocks (+ crypto), paper by default, live hard-gated.

Wraps the existing utils/alpaca_client.py AlpacaClient. Behavior:

  • Default (and any misconfiguration): PAPER. With credentials the adapter
    connects to Alpaca's paper-trading endpoint; without credentials (or
    without the SDK) it degrades to the offline simulator — still paper,
    still zero real orders.
  • Live requires ALL of: ALPACA_LIVE=true, ALPACA_LIVE_ACK exactly equal to
    "I_UNDERSTAND_REAL_MONEY", valid Alpaca credentials, AND the desk-wide
    LIVE_TRADING_ACK (the adapter's own pre-existing gate — defense in depth).
    Anything missing → paper, with a loud warning (fail closed).
  • Claims any symbol (stocks like AAPL, crypto like BTC/USD), so it is the
    venue that unlocks real stock trading once Juan connects keys.

To enable real stock trading Juan must: (1) open/fund an Alpaca brokerage
account, (2) create API keys, (3) set ALPACA_API_KEY/ALPACA_SECRET_KEY,
ALPACA_LIVE=true, ALPACA_LIVE_ACK=I_UNDERSTAND_REAL_MONEY (plus the desk-wide
LIVE_TRADING_ACK), and (4) approve the exact go-live. Until then: paper only.
"""
from __future__ import annotations

import dataclasses
import os

from config import Config
from utils.alpaca_client import AlpacaClient
from utils.logger import get_logger
from venues.base import ACK_PHRASE, normalize_symbol

log = get_logger("venue_alpaca")


class AlpacaVenue:
    venue_id = "alpaca"
    kind = "multi"   # US equities + options + 24/7 crypto

    def __init__(self, cfg: Config, live_requested: bool = False):
        self._live_requested = bool(live_requested)
        ack_ok = (os.getenv("ALPACA_LIVE_ACK", "") or "").strip() == ACK_PHRASE
        env_live = (os.getenv("ALPACA_LIVE", "") or "").strip().lower() == "true"

        self._live = False
        if self._live_requested and env_live and ack_ok:
            self._live = True
        elif self._live_requested or env_live:
            # Operator asked for live but the ack is missing/wrong → paper.
            # Loud on purpose: silent downgrades hide intent.
            log.warning("Alpaca live requested but ALPACA_LIVE_ACK is not the exact "
                        "ack phrase — venue forced to PAPER (fail closed).")

        venue_cfg = dataclasses.replace(cfg, alpaca_paper=not self._live)
        self._client = AlpacaClient(venue_cfg)
        self.tickers: list = []
        if self._live:
            log.warning("Alpaca venue LIVE-armed path selected — real orders still "
                        "require the adapter's own trading_armed gate "
                        "(desk-wide LIVE_TRADING_ACK + working credentials).")

    # ── BrokerAdapter surface (delegated) ────────────────────────────────────
    @property
    def online(self) -> bool:
        return self._client.online

    @property
    def mode(self) -> str:
        # "LIVE" only when every gate passed; otherwise this venue is paper.
        if self._live and self._client.online and self._client.trading_armed:
            return "LIVE"
        return "paper"

    @property
    def live_armed(self) -> bool:
        return self.mode == "LIVE"

    def claims(self, symbol: str) -> bool:
        # Stocks and crypto — the generalist venue.
        return bool((symbol or "").strip())

    def supports(self, symbol: str) -> bool:
        return normalize_symbol(symbol) in {normalize_symbol(s) for s in self.tickers}

    def get_account(self):
        return self._client.get_account()

    def get_broker_positions(self):
        return self._client.get_broker_positions()

    def get_history(self, symbol: str, days: int = 120):
        return self._client.get_history(symbol, days)

    def get_price(self, symbol: str) -> float:
        return self._client.get_price(symbol)

    def get_price_with_ts(self, symbol: str):
        return self._client.get_price_with_ts(symbol)

    def is_market_open(self) -> bool:
        return self._client.is_market_open()

    def get_option_chain(self, symbol, spot, dte_min, dte_max, vol, kinds=("put", "call")):
        return self._client.get_option_chain(symbol, spot, dte_min, dte_max, vol, kinds)

    def submit_equity_order(self, symbol: str, qty: float, side: str):
        return self._client.submit_equity_order(symbol, qty, side)

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0):
        return self._client.submit_option_order(contract, qty, side, premium)

    def get_order_status(self, order_id: str, symbol: str = ""):
        return self._client.get_order_status(order_id, symbol)

    def advance_sim(self, steps: int = 1) -> None:
        return self._client.advance_sim(steps)
