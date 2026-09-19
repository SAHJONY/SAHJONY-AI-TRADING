"""Venue registry: parses VENUES config, assigns tickers, builds VenueSpecs.

Configuration:
  VENUES="robinhood_crypto:live,alpaca:paper,simulator:paper"
      Comma-separated ``venue_id:mode`` pairs. Mode defaults to paper when
      omitted ("alpaca" == "alpaca:paper"). Unset/empty VENUES → [] and the
      desk keeps its legacy single-broker behavior, untouched.

  Per-venue tickers (optional, override auto-assignment):
      TICKERS_ROBINHOOD_CRYPTO="BTC/USD,ETH/USD"
      TICKERS_ALPACA="AAPL,MSFT,SPY"
      TICKERS_SIMULATOR="*"

  Per-venue notional cap (optional):
      MAX_ORDER_USD_<VENUE_ID>  (default 25.0)

Auto-assignment: any global TICKERS symbol not explicitly assigned goes to the
first venue (in VENUES order) whose claims() accepts it — EXCLUDING venues
that have an explicit TICKERS_<VENUE> override (explicit means exact: those
venues get precisely their listed symbols, nothing auto-assigned). A symbol
no venue claims is reported as unclaimed — the router then fails closed on
it (no price, no order), loudly, instead of silently dropping it.

Fail-fast: unknown venue ids, duplicate venues, bad modes, or an explicitly
assigned ticker the venue cannot support all raise ValueError at build time —
before any trading — never mid-cycle.
"""
from __future__ import annotations

import os
from typing import List, Tuple

from config import Config
from utils.logger import get_logger
from venues.alpaca_venue import AlpacaVenue
from venues.base import VenueSpec, normalize_symbol
from venues.robinhood_venue import RobinhoodCryptoVenue
from venues.simulator_venue import SimulatorVenue

log = get_logger("venue_registry")

_BUILDERS = {
    "robinhood_crypto": lambda cfg, live: RobinhoodCryptoVenue(cfg),
    "alpaca": lambda cfg, live: AlpacaVenue(cfg, live_requested=live),
    "simulator": lambda cfg, live: SimulatorVenue(cfg, live_requested=live),
}

_DEFAULT_MAX_ORDER_USD = 25.0


def parse_venues(raw: str) -> List[Tuple[str, str]]:
    """Parse VENUES into [(venue_id, mode)] with mode in {"live","paper"}."""
    out: List[Tuple[str, str]] = []
    seen = set()
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            name, mode = entry.split(":", 1)
        else:
            name, mode = entry, "paper"   # default: paper, never live
        name = name.strip().lower()
        mode = mode.strip().lower()
        if name not in _BUILDERS:
            raise ValueError(
                f"Unknown venue '{name}' in VENUES. Registered: "
                f"{', '.join(sorted(_BUILDERS))}.")
        if name in seen:
            raise ValueError(f"Duplicate venue '{name}' in VENUES.")
        if mode not in ("live", "paper"):
            raise ValueError(
                f"Bad mode '{mode}' for venue '{name}' in VENUES — use live|paper.")
        seen.add(name)
        out.append((name, mode))
    return out


def _explicit_tickers(venue_id: str) -> List[str] | None:
    """Per-venue TICKERS_<VENUE_ID> override. None → auto-assign."""
    raw = os.getenv(f"TICKERS_{venue_id.upper()}", "")
    if not raw.strip():
        return None
    if raw.strip() == "*":
        return ["*"]
    return [normalize_symbol(s) for s in raw.split(",") if s.strip()]


def _venue_max_order_usd(venue_id: str) -> float:
    raw = os.getenv(f"MAX_ORDER_USD_{venue_id.upper()}", "")
    try:
        val = float(raw)
        return val if val > 0 else _DEFAULT_MAX_ORDER_USD
    except (TypeError, ValueError):
        return _DEFAULT_MAX_ORDER_USD


def build_venue_specs(cfg: Config) -> List[VenueSpec]:
    """Build the venue list from VENUES. [] when VENUES is unset (legacy mode)."""
    raw = (getattr(cfg, "venues", "") or "").strip()
    parsed = parse_venues(raw)
    if not parsed:
        return []

    global_tickers = [normalize_symbol(s) for s in (getattr(cfg, "tickers", []) or [])]
    assigned: set = set()
    explicit_venues: set = set()   # venues with TICKERS_<VENUE> get exactly those
    venues: List[VenueSpec] = []
    adapters = {}

    # 1) construct adapters + apply explicit ticker overrides
    for venue_id, mode in parsed:
        live_requested = (mode == "live")
        adapter = _BUILDERS[venue_id](cfg, live_requested)
        adapters[venue_id] = adapter
        explicit = _explicit_tickers(venue_id)
        tickers: List[str] = []
        if explicit is not None:
            explicit_venues.add(venue_id)
            if explicit == ["*"]:
                tickers = list(global_tickers)
            else:
                for sym in explicit:
                    if not adapter.claims(sym):
                        raise ValueError(
                            f"Venue '{venue_id}' cannot support explicitly assigned "
                            f"ticker '{sym}' (wrong asset class for this venue).")
                    tickers.append(sym)
            assigned.update(tickers)
        venues.append(VenueSpec(
            venue_id=venue_id,
            adapter=adapter,
            kind=getattr(adapter, "kind", "multi"),
            tickers=tickers,
            max_order_usd=_venue_max_order_usd(venue_id),
            live_requested=live_requested,
        ))

    # 2) auto-assign the rest in VENUES order (first claiming venue wins),
    #    skipping venues that declared an explicit ticker list.
    by_id = {v.venue_id: v for v in venues}
    unclaimed: List[str] = []
    for sym in global_tickers:
        if sym in assigned:
            continue
        placed = False
        for venue_id, _mode in parsed:
            if venue_id in explicit_venues:
                continue
            adapter = adapters[venue_id]
            if adapter.claims(sym):
                by_id[venue_id].tickers.append(sym)
                assigned.add(sym)
                placed = True
                break
        if not placed:
            unclaimed.append(sym)

    if unclaimed:
        # Loud, not silent: these symbols will fail closed on every order.
        log.warning("No venue claims %d ticker(s); they will fail closed "
                    "(no price, no order): %s", len(unclaimed), ", ".join(unclaimed))

    for v in venues:
        v.adapter.tickers = list(v.tickers)
        log.info("Venue %-16s kind=%-6s mode=%-5s tickers=%d max_order_usd=%.2f",
                 v.venue_id, v.kind,
                 "LIVE" if v.live_armed else "paper",
                 len(v.tickers), v.max_order_usd)
    return venues
