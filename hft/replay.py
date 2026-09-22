"""Trade-print replay feed (HFT Lab v2 — research simulator, paper only).

IMPORTANT — what this is and is not
------------------------------------
This is TRADE-PRINT replay, NOT full L2 depth replay. Each event's TRADE
print (price, size, aggressor side, timestamp) is real historical data from
the fixed fixture in ``hft/data/`` (see ``hft/data/SOURCE.md``). Everything
*around* the print — the bid/ask quotes and the deeper book levels — is
SYNTHESIZED by a seeded RNG (numpy ``default_rng``): the spread (1-3 ticks),
the decaying level sizes, and the quote-update timing are modeled, not
observed. Queue position, hidden liquidity, and cancellations are not in the
fixture and are not replayed.

Consequences: backtests on this feed measure how a strategy behaves against
real print timing/prices wrapped in a *modeled* book. They do not reproduce
what any real order book looked like, and they prove nothing about live
profitability. HFT Lab v2 is a research simulator.

:class:`ReplayFeed` implements the same consumer-facing interface as
``SyntheticL2Feed`` in :mod:`hft.feed` (``__iter__`` yielding
:class:`FeedEvent`, ``sim_seconds`` attribute, ``estimate_event_count()``),
so it plugs into :class:`hft.backtest.Backtest` via duck typing.

Determinism: same fixture file + same seed -> byte-identical event stream.
Different seeds differ only in the synthetic book-building around the
identical prints. The module performs no network I/O; it reads only the
fixture file.
"""

from __future__ import annotations

import json
from typing import Iterator, List, Tuple

import numpy as np

from .book import BUY, SELL
from .feed import LEVEL, TRADE, FeedEvent

#: One integer quantity unit = 1 milli-BTC. Integer FeedEvent quantities are
#: derived from fixture BTC sizes by this factor (min 1 unit).
QTY_PER_BTC = 1000


class ReplayFeed:
    """Replay real trade prints from a fixed JSONL fixture.

    Fixture line format (one JSON object per line)::

        {"ts": <unix ns int>, "price": <float>, "qty": <float BTC>,
         "side": "b" | "s"}

    ``side`` is the aggressor side as tagged by the venue ("b" =
    buyer-initiated, "s" = seller-initiated).

    Parameters
    ----------
    fixture_path: path to the fixed JSONL fixture file.
    seed: RNG seed — same seed reproduces the identical event stream.
    levels: quote levels synthesized per side around each print (>= 1).
    tick_size: price granularity used to convert fixture prices to integer
        ticks (must match the backtest's price-tick convention).
    """

    def __init__(
        self,
        fixture_path: str,
        seed: int = 0,
        levels: int = 5,
        tick_size: float = 0.01,
    ) -> None:
        if levels < 1:
            raise ValueError("levels must be >= 1")
        if tick_size <= 0:
            raise ValueError("tick_size must be positive")
        self.fixture_path = fixture_path
        self.seed = int(seed)
        self.levels = int(levels)
        self.tick_size = float(tick_size)

        trades: List[Tuple[int, float, float, str]] = []
        with open(fixture_path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                side = str(d["side"])
                if side not in ("b", "s"):
                    raise ValueError(
                        f"{fixture_path}:{lineno}: side must be 'b' or 's'"
                    )
                trades.append(
                    (int(d["ts"]), float(d["price"]), float(d["qty"]), side)
                )
        if not trades:
            raise ValueError(f"fixture {fixture_path} contains no trades")

        # Sort by timestamp; enforce strictly increasing with deterministic
        # +1 ns nudges (never drop prints: the TRADE count must equal the
        # fixture trade count).
        trades.sort(key=lambda t: t[0])
        fixed: List[Tuple[int, float, float, str]] = [trades[0]]
        for t in trades[1:]:
            prev_ts = fixed[-1][0]
            ts = t[0] if t[0] > prev_ts else prev_ts + 1
            fixed.append((ts, t[1], t[2], t[3]))
        self._trades = fixed

        self._t0 = fixed[0][0]
        self.sim_seconds = float((fixed[-1][0] - fixed[0][0]) / 1_000_000_000)
        if self.sim_seconds <= 0:
            # degenerate single-timestamp fixture: still replayable
            self.sim_seconds = 1e-9

    # ------------------------------------------------------------------
    @property
    def n_trades(self) -> int:
        return len(self._trades)

    def estimate_event_count(self) -> int:
        # per print: `levels` bid levels + `levels` ask levels + the print
        return self.n_trades * (2 * self.levels + 1)

    # ------------------------------------------------------------------
    def __iter__(self) -> Iterator[FeedEvent]:
        rng = np.random.default_rng(self.seed)  # fresh each pass: re-iterable
        prev_ts = -1

        for ts, price, qty, side in self._trades:
            base = ts - self._t0
            start = base if base > prev_ts else prev_ts + 1

            p = int(round(price / self.tick_size))
            if p <= 0:
                raise ValueError(f"non-positive price tick {p} from {price}")
            spread = int(rng.integers(1, 4))  # 1..3 ticks, modeled
            if side == "b":  # buyer-initiated: print lifted the ask
                ask, bid, aggressor = p, p - spread, BUY
            else:  # seller-initiated: print hit the bid
                bid, ask, aggressor = p, p + spread, SELL

            qty_units = max(1, int(round(qty * QTY_PER_BTC)))

            # Quote levels around the print: touch first, then deeper,
            # sizes decaying with depth. All modeled, not observed.
            t = start
            for lvl in range(self.levels):
                bid_q = max(1, int(rng.integers(20, 200) // (lvl + 1)))
                ask_q = max(1, int(rng.integers(20, 200) // (lvl + 1)))
                yield FeedEvent(kind=LEVEL, ts_ns=int(t), side=BUY,
                                price=int(bid - lvl), qty=int(bid_q))
                t += 1
                yield FeedEvent(kind=LEVEL, ts_ns=int(t), side=SELL,
                                price=int(ask + lvl), qty=int(ask_q))
                t += 1

            # The real print, at the real price, with the venue-tagged
            # aggressor side.
            yield FeedEvent(kind=TRADE, ts_ns=int(t), side=int(aggressor),
                            price=int(p), qty=int(qty_units))
            prev_ts = t
