"""Multi-venue trading layer.

One desk, many markets. Each venue is a broker adapter plus routing metadata
(venue id, asset kind, assigned tickers, per-venue risk caps). The
:class:`venues.router.VenueRouter` implements the existing BrokerAdapter
contract, so the workforce, risk engine, and reporter need no changes: they
keep talking to one ``client`` and the router sends each symbol to the venue
that supports it.

Safety posture (non-negotiable):
  • Every venue defaults to PAPER. Live per venue needs its own explicit ack
    variable, fail-closed (same pattern as LIVE_TRADING_ACK).
  • The simulator venue can NEVER be live — hard-coded, not configurable.
  • A symbol with no supporting venue fails closed: no price, no order.
  • Per-venue notional caps are enforced by the router on top of each
    adapter's own limits; the desk's global risk engine is untouched.
  • When VENUES is unset, utils.broker.get_broker() behaves EXACTLY as before
    (single legacy broker) — the live Robinhood crypto path is not regressed.
"""
from venues.router import VenueRouter
from venues.registry import build_venue_specs, parse_venues, VenueSpec

__all__ = ["VenueRouter", "build_venue_specs", "parse_venues", "VenueSpec"]
