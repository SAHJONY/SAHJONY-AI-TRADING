"""TEMPLATE broker adapter — copy this to add a new venue (NOT registered).

To support e.g. Interactive Brokers (FX/futures/non-US equities) or a CCXT
exchange (worldwide crypto):

  1. Copy this file to utils/brokers/<venue>.py and rename the class.
  2. Implement every method against the venue's SDK. Wrap EVERY external call so a
     failure logs and returns a safe default — the trading loop must never crash
     (fault isolation, per CLAUDE.md). Mirror utils/alpaca_client.py.
  3. Provide an OFFLINE-SIM fallback when credentials/SDK are unavailable, so the
     desk still runs with zero real orders (reuse the sim helpers if useful).
  4. Register it in utils/broker.py get_broker():  if name == "<venue>": ...
  5. Select it with BROKER=<venue> in the desk's .env.

Until fully implemented, leave methods raising NotImplementedError — get_broker()
only knows registered venues, so an unfinished template can never be selected by
accident.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from config import Config
from utils.logger import get_logger

log = get_logger("broker.template")


class TemplateBroker:
    """Reference skeleton for a new venue. See module docstring."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.mode = "offline-sim"   # set to 'paper'/'LIVE' once connected

    @property
    def online(self) -> bool:
        return False

    def get_account(self) -> Dict[str, float]:
        raise NotImplementedError("implement get_account for this venue")

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        raise NotImplementedError

    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        raise NotImplementedError

    def get_price(self, symbol: str) -> float:
        raise NotImplementedError

    def is_market_open(self) -> bool:
        # FX/crypto are typically 24/x; honor cfg.always_on as Alpaca does.
        return bool(self.cfg.always_on)

    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        return []   # venues without options return an empty chain

    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        raise NotImplementedError

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        raise NotImplementedError

    def advance_sim(self, steps: int = 1) -> None:
        pass
