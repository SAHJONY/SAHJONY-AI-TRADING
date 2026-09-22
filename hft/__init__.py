"""HFT Lab v1 — a research/paper high-frequency trading simulator.

Scope
-----
An offline, deterministic teaching-and-research package for studying
microstructure mechanics: an L2 limit order book (``book``), a matching-engine
simulator (``matching``), a latency model (``latency``), a synthetic L2 feed
(``feed``), quoting/signal strategies (``strategies``), a pre-trade risk
gateway (``risk``), an event-driven backtester (``backtest``), and paper-only
venue adapters (``venue``).

Hard limits (by design, not by accident)
----------------------------------------
* SIMULATOR ONLY. Nothing here connects to a broker, exchange, data vendor,
  or any network resource. There are no credentials, no API keys, no live
  orders — not even a code path that could place one. ``venue.LiveVenue``
  raises ``NotImplementedError`` on construction.
* SYNTHETIC DATA ONLY. The feed is a seeded random-walk generator. Results
  describe how strategies behave against *this* generator, not against any
  real market.
* NOT A PRODUCTION HFT SYSTEM. Real high-frequency trading requires exchange
  membership, colocated servers, direct market-data feeds, deterministic
  sub-100 microsecond networking, and regulatory/compliance infrastructure.
  A retail-style venue (REST/web order entry, second-scale latency) cannot do
  true HFT. This package proves nothing about live profitability.
* DEPENDENCIES: Python standard library + numpy only. Deterministic: every
  stochastic component takes an explicit seed.

Conventions
-----------
* Prices are integer *ticks*. ``tick_size`` (default $0.01) converts to
  dollars. Quantities are integer shares/contracts. Timestamps are integer
  nanoseconds since the simulation epoch.
* Sides: ``BUY = 1``, ``SELL = -1`` (see ``hft.book``).
"""

from . import book, matching, latency, feed, strategies, risk, backtest, venue

__all__ = ["book", "matching", "latency", "feed", "strategies", "risk", "backtest", "venue"]

__version__ = "1.0.0"
