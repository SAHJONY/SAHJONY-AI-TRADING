"""Real-time quote intelligence — provenance, staleness and outlier rejection.

The desk's brokers return a bare float. A float cannot tell you *when* it was
true, whether the feed has frozen, or whether it is a fat-fingered print — so the
desk will happily size a position against a stale or corrupt tick and never know.
Every quote that reaches a decision should carry that context.

This wraps any adapter satisfying the `utils/broker.py` contract and adds:

  • **Provenance** — each accepted price is a `Quote` with a fetch timestamp and
    source, so downstream code can ask how old its information is.
  • **Outlier rejection** — a print that jumps more than `max_jump_pct` against
    the last accepted price is quarantined, not traded. A *second* consecutive
    print in the same region confirms a genuine move and is accepted, so real
    gaps get through while single bad ticks do not.
  • **Freeze detection** — a feed that returns an identical price for longer than
    `stale_after_s` is flagged. Crypto trades 24/7; an unchanging price is much
    more often a dead socket than a quiet market.
  • **Health telemetry** — per-symbol counters the reporter and Hermes can read,
    so a degrading feed is visible before it costs money.

Honest limitation: these adapters do not expose the venue's own quote timestamp,
so "age" here is measured from *our* fetch, not from the exchange print. That
detects a frozen or failing feed; it cannot detect a venue publishing stale data
with a fresh timestamp. Fixing that needs the exchange timestamp plumbed through
the adapter contract.

Safety posture: this can only ever make the desk trade *less* on bad data. A
rejected quote falls back to the last good price (flagged stale) and never to
0.0 — a zero would read as a -100% move and fire every catastrophic floor.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from utils.logger import get_logger

log = get_logger("realtime")


@dataclass
class Quote:
    """A price with the context needed to decide whether to trust it."""
    symbol: str
    price: float
    ts: float                       # epoch seconds, when WE fetched it
    source: str = "broker"
    stale: bool = False             # served from cache after a rejection/failure
    suspect: bool = False           # accepted, but the feed looks unhealthy

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.ts)

    @property
    def trustworthy(self) -> bool:
        return self.price > 0 and not self.stale and not self.suspect


@dataclass
class _SymbolState:
    last_price: float = 0.0
    last_ts: float = 0.0
    last_change_ts: float = 0.0
    pending: Optional[float] = None   # a jump awaiting confirmation
    accepted: int = 0
    rejected: int = 0
    frozen_flags: int = 0


@dataclass
class FeedHealth:
    symbols: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_accepted: int = 0
    total_rejected: int = 0

    @property
    def reject_rate(self) -> float:
        n = self.total_accepted + self.total_rejected
        return 0.0 if n == 0 else self.total_rejected / n


class RealtimeGuard:
    """Broker wrapper that validates every quote before it reaches the desk."""

    def __init__(self, broker: Any, max_jump_pct: float = 0.10,
                 stale_after_s: float = 300.0, source: str = ""):
        object.__setattr__(self, "_broker", broker)
        object.__setattr__(self, "_state", {})
        object.__setattr__(self, "_max_jump", max(0.0, float(max_jump_pct)))
        object.__setattr__(self, "_stale_after", max(0.0, float(stale_after_s)))
        object.__setattr__(self, "_source",
                           source or getattr(broker, "mode", "broker"))
        object.__setattr__(self, "_quotes", {})

    # -- transparent delegation ----------------------------------------------
    def __getattr__(self, name: str):
        return getattr(self._broker, name)

    def __setattr__(self, name: str, value) -> None:
        if name in ("_broker", "_state", "_max_jump", "_stale_after", "_source",
                    "_quotes"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._broker, name, value)

    # -- validation ----------------------------------------------------------
    def _validate(self, symbol: str, raw: float) -> Quote:
        st = self._state.setdefault(symbol, _SymbolState())
        now = time.time()

        # 1) a failed or nonsensical read never becomes a price
        if not raw or raw <= 0 or raw != raw:          # NaN-safe
            st.rejected += 1
            if st.last_price > 0:
                log.warning("%s: bad quote (%r) — serving last good %.6f (age %.0fs)",
                            symbol, raw, st.last_price, now - st.last_ts)
                return Quote(symbol, st.last_price, st.last_ts, self._source, stale=True)
            return Quote(symbol, 0.0, now, self._source, stale=True)

        # 2) outlier gate — one wild print is quarantined, two in a row is a move
        if st.last_price > 0 and self._max_jump > 0:
            jump = abs(raw / st.last_price - 1.0)
            if jump > self._max_jump:
                confirms = (st.pending is not None
                            and abs(raw / st.pending - 1.0) <= self._max_jump)
                if not confirms:
                    st.pending = raw
                    st.rejected += 1
                    log.warning("%s: %.1f%% jump to %.6f rejected pending confirmation "
                                "(last good %.6f)", symbol, jump * 100, raw, st.last_price)
                    return Quote(symbol, st.last_price, st.last_ts, self._source,
                                 stale=True)
                log.info("%s: %.1f%% move to %.6f confirmed by a second print",
                         symbol, jump * 100, raw)
        st.pending = None

        # 3) freeze detection — an unchanging 24/7 feed is usually a dead socket
        suspect = False
        if raw != st.last_price:
            st.last_change_ts = now
        elif st.last_change_ts and (now - st.last_change_ts) > self._stale_after:
            suspect = True
            st.frozen_flags += 1
            log.warning("%s: price unchanged at %.6f for %.0fs — feed may be frozen",
                        symbol, raw, now - st.last_change_ts)

        st.last_price, st.last_ts = raw, now
        if not st.last_change_ts:
            st.last_change_ts = now
        st.accepted += 1
        return Quote(symbol, raw, now, self._source, stale=False, suspect=suspect)

    # -- broker surface ------------------------------------------------------
    def get_price(self, symbol: str) -> float:
        q = self._validate(symbol, self._broker.get_price(symbol))
        self._quotes[symbol] = q
        return q.price

    def get_quote(self, symbol: str) -> Quote:
        """Price *with* provenance — for callers that want to reason about trust."""
        self.get_price(symbol)
        return self._quotes[symbol]

    def last_quote(self, symbol: str) -> Optional[Quote]:
        return self._quotes.get(symbol)

    def health(self) -> FeedHealth:
        h = FeedHealth()
        for sym, st in self._state.items():
            h.total_accepted += st.accepted
            h.total_rejected += st.rejected
            h.symbols[sym] = {
                "last_price": round(st.last_price, 8),
                "age_s": round(time.time() - st.last_ts, 1) if st.last_ts else None,
                "since_change_s": (round(time.time() - st.last_change_ts, 1)
                                   if st.last_change_ts else None),
                "accepted": st.accepted, "rejected": st.rejected,
                "frozen_flags": st.frozen_flags,
            }
        return h


def consensus_price(quotes, max_disagreement_pct: float = 0.02):
    """Median price across independent sources, with a disagreement flag.

    Returns (price, agreed). Cross-source disagreement beyond the threshold is
    the strongest available signal that one venue is publishing garbage — the
    caller should stand down rather than pick a side.
    """
    good = sorted(q.price for q in quotes if q and q.price > 0 and not q.stale)
    if not good:
        return 0.0, False
    n = len(good)
    mid = good[n // 2] if n % 2 else (good[n // 2 - 1] + good[n // 2]) / 2.0
    if n < 2 or mid <= 0:
        return mid, True
    spread = (good[-1] - good[0]) / mid
    if spread > max_disagreement_pct:
        log.warning("source disagreement %.2f%% across %d feeds (%.6f..%.6f)",
                    spread * 100, n, good[0], good[-1])
        return mid, False
    return mid, True
