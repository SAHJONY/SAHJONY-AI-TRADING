"""Broker adapter contract + factory.

The Firm only ever talks to a broker through this interface, so adding a new
venue (a second broker, a new asset class, a new region) is an isolated task:
implement every method below and register the class in `get_broker()`.

AlpacaClient (utils/alpaca_client.py) is the reference implementation — US
equities/options plus 24/7 crypto. A new adapter (e.g. IBKR for FX/futures or a
CCXT exchange for worldwide crypto) just has to satisfy the same contract; the
orchestrator, risk engine, and reporter need no changes.

See utils/brokers/template_adapter.py for a copy-paste starting point.
"""
from __future__ import annotations

from typing import Dict, List, Protocol, runtime_checkable

import numpy as np

from config import Config

# The methods/attributes the Firm relies on. get_broker() checks an adapter
# provides all of them, so a half-built broker fails fast with a clear error
# instead of blowing up mid-cycle.
REQUIRED = (
    "online", "mode", "get_account", "get_broker_positions", "get_history",
    "get_price", "is_market_open", "get_option_chain", "submit_equity_order",
    "submit_option_order", "advance_sim",
)


@runtime_checkable
class BrokerAdapter(Protocol):
    mode: str

    @property
    def online(self) -> bool: ...

    def get_account(self) -> Dict[str, float]: ...
    def get_broker_positions(self) -> Dict[str, Dict[str, float]]: ...
    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]: ...
    def get_price(self, symbol: str) -> float: ...
    def is_market_open(self) -> bool: ...
    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]: ...
    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict: ...
    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict: ...
    def advance_sim(self, steps: int = 1) -> None: ...


def _verify(adapter) -> object:
    missing = [m for m in REQUIRED if not hasattr(adapter, m)]
    if missing:
        raise TypeError(f"{type(adapter).__name__} is not a complete BrokerAdapter; "
                        f"missing: {', '.join(missing)}")
    return adapter


def get_broker(cfg: Config):
    """Return the broker adapter selected by cfg.broker (default 'alpaca').

    To add a venue: implement BrokerAdapter and add a branch here."""
    name = (getattr(cfg, "broker", "alpaca") or "alpaca").lower()
    if name == "alpaca":
        from utils.alpaca_client import AlpacaClient
        return _verify(AlpacaClient(cfg))
    if name == "ibkr":
        from utils.brokers.ibkr import IBKRBroker
        return _verify(IBKRBroker(cfg))
    if name == "ccxt":
        from utils.brokers.ccxt_broker import CCXTBroker
        return _verify(CCXTBroker(cfg))
    raise ValueError(f"Unknown BROKER '{name}'. Registered: alpaca, ibkr, ccxt. "
                     f"Implement an adapter (see utils/brokers/template_adapter.py) "
                     f"and register it in utils/broker.py.")
