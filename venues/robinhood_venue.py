"""Robinhood Crypto venue — the live real-money crypto path.

Thin wrapper around the existing utils/brokers/robinhood_crypto.py adapter.
ZERO behavior change: arming still requires ROBINHOOD_LIVE=true AND
LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY AND a working Ed25519 signer.
Unarmed it stays a dry-run venue (prices live data, places nothing).

Robinhood's crypto API physically cannot trade stocks — this venue only ever
claims crypto-like symbols, so equity symbols fail closed here and route to a
stock venue (or nowhere).
"""
from __future__ import annotations

from config import Config
from utils.brokers.robinhood_crypto import RobinhoodCryptoBroker
from utils.logger import get_logger
from venues.base import is_crypto_like, normalize_symbol

log = get_logger("venue_robinhood")


class RobinhoodCryptoVenue:
    venue_id = "robinhood_crypto"
    kind = "crypto"

    def __init__(self, cfg: Config):
        # The inner broker is constructed exactly as the legacy single-broker
        # path constructs it — same env, same gates, same behavior.
        self._broker = RobinhoodCryptoBroker(cfg)
        self.tickers: list = []

    # ── BrokerAdapter surface (delegated 1:1 — no behavior change) ──────────
    @property
    def online(self) -> bool:
        return self._broker.online

    @property
    def mode(self) -> str:
        # Adapter reports "LIVE" only when fully armed, else "robinhood-dryrun".
        return self._broker.mode

    @property
    def armed(self) -> bool:
        return bool(self._broker.armed)

    @property
    def live_armed(self) -> bool:
        return self.armed

    def claims(self, symbol: str) -> bool:
        """Auto-assignment predicate: crypto-like symbols only."""
        return is_crypto_like(symbol)

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
        return self._broker.submit_equity_order(symbol, qty, side)

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0):
        return self._broker.submit_option_order(contract, qty, side, premium)

    def get_order_status(self, order_id: str, symbol: str = ""):
        return self._broker.get_order_status(order_id, symbol)

    def get_order(self, order_id: str):
        return self._broker.get_order(order_id)

    def advance_sim(self, steps: int = 1) -> None:
        return self._broker.advance_sim(steps)
