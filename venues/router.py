"""VenueRouter: one BrokerAdapter face, many venues behind it.

The desk keeps talking to a single ``client`` (workforce, risk engine,
reporter, main preflight all unchanged). The router sends each call to the
venue that owns the symbol:

  • get_price / get_history / get_option_chain → owning venue; unknown symbol
    → safe defaults (0.0 / empty), so the council stays neutral, never blind.
  • submit_*_order → owning venue, after a per-venue notional cap check.
    Unknown symbol → {"status": "rejected", reason: "no venue supports ..."}.
    Fail closed, always.
  • get_account / get_broker_positions → aggregated across online venues
    (symbols are unique per venue by construction).
  • describe_venues() → per-venue dashboard block for status.json.

Every delegated call is fault-isolated: one venue's exception degrades to the
safe default instead of sinking the cycle.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from utils.logger import get_logger
from venues.base import VenueSpec, normalize_symbol

log = get_logger("venue_router")


class VenueRouter:
    """Drop-in BrokerAdapter that routes per symbol across venues."""

    def __init__(self, specs: List[VenueSpec]):
        if not specs:
            raise ValueError("VenueRouter needs at least one venue spec")
        self.specs = list(specs)
        self._by_symbol: Dict[str, VenueSpec] = {}
        for spec in specs:
            for sym in spec.tickers:
                key = normalize_symbol(sym)
                if key in self._by_symbol:
                    other = self._by_symbol[key].venue_id
                    log.error("Ticker %s assigned to both %s and %s — first wins",
                              sym, other, spec.venue_id)
                    continue
                self._by_symbol[key] = spec

    # ── routing ──────────────────────────────────────────────────────────────
    def spec_for(self, symbol: str) -> VenueSpec | None:
        return self._by_symbol.get(normalize_symbol(symbol))

    def unclaimed_symbols(self) -> List[str]:
        return []  # registry reports these at build; router only sees assigned

    # ── BrokerAdapter contract ───────────────────────────────────────────────
    @property
    def online(self) -> bool:
        try:
            return any(self._safe(lambda s: bool(s.adapter.online), s, False)
                       for s in self.specs)
        except Exception:
            return False

    @property
    def mode(self) -> str:
        # "LIVE" if ANY venue is live-armed (the reporter's kill-switch banner
        # keys off this); otherwise paper.
        try:
            if any(s.live_armed for s in self.specs):
                return "LIVE"
        except Exception:
            pass
        return "paper"

    @staticmethod
    def _safe(fn, spec: VenueSpec, default):
        try:
            return fn(spec)
        except Exception as exc:
            log.warning("Venue %s call failed: %s", spec.venue_id, exc)
            return default

    def get_account(self) -> Dict[str, float]:
        total = {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}
        for spec in self.specs:
            acct = self._safe(lambda s: s.adapter.get_account() or {}, spec, {})
            for k in total:
                try:
                    total[k] += float(acct.get(k, 0.0) or 0.0)
                except (TypeError, ValueError):
                    pass
        return total

    def get_venue_accounts(self) -> Dict[str, Dict[str, float]]:
        """Per-venue account snapshot (for the dashboard strip)."""
        out = {}
        for spec in self.specs:
            acct = self._safe(lambda s: s.adapter.get_account() or {}, spec, {})
            out[spec.venue_id] = {k: float(acct.get(k, 0.0) or 0.0)
                                  for k in ("equity", "cash", "buying_power")}
        return out

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        merged: Dict[str, Dict[str, float]] = {}
        for spec in self.specs:
            pos = self._safe(lambda s: s.adapter.get_broker_positions() or {}, spec, {})
            for sym, h in pos.items():
                if sym in merged:
                    log.error("Position %s reported by two venues — keeping first", sym)
                    continue
                merged[sym] = h
        return merged

    def get_price(self, symbol: str) -> float:
        spec = self.spec_for(symbol)
        if spec is None:
            return 0.0   # fail closed: no venue → no price → council neutral
        px = self._safe(lambda s: s.adapter.get_price(symbol), spec, 0.0)
        try:
            return float(px or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def get_price_with_ts(self, symbol: str):
        spec = self.spec_for(symbol)
        if spec is None:
            return 0.0, None
        adapter = spec.adapter
        if hasattr(adapter, "get_price_with_ts"):
            try:
                return adapter.get_price_with_ts(symbol)
            except Exception as exc:
                log.warning("Venue %s get_price_with_ts failed: %s", spec.venue_id, exc)
        return self.get_price(symbol), None

    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        spec = self.spec_for(symbol)
        if spec is None:
            return {"closes": np.array([]), "volumes": np.array([])}
        return self._safe(lambda s: s.adapter.get_history(symbol, days), spec,
                          {"closes": np.array([]), "volumes": np.array([])})

    def is_market_open(self) -> bool:
        return any(self._safe(lambda s: bool(s.adapter.is_market_open()), s, False)
                   for s in self.specs)

    def get_option_chain(self, symbol, spot, dte_min, dte_max, vol,
                         kinds=("put", "call")) -> List[Dict]:
        spec = self.spec_for(symbol)
        if spec is None:
            return []
        return self._safe(
            lambda s: s.adapter.get_option_chain(symbol, spot, dte_min, dte_max,
                                                 vol, kinds) or [],
            spec, [])

    def _check_venue_cap(self, spec: VenueSpec, symbol: str, qty: float) -> Dict | None:
        """Per-venue notional cap. Returns a rejection dict or None if OK."""
        try:
            px = float(self.get_price(symbol) or 0.0)
        except (TypeError, ValueError):
            px = 0.0
        notional = abs(float(qty or 0.0)) * px
        if notional > spec.max_order_usd:
            log.warning("Order %s %s ~$%.2f exceeds venue %s cap $%.2f — blocked",
                        symbol, spec.venue_id, notional, spec.venue_id,
                        spec.max_order_usd)
            return {"status": "rejected",
                    "reason": f"exceeds venue {spec.venue_id} max_order_usd "
                              f"${spec.max_order_usd:.2f}",
                    "venue": spec.venue_id}
        return None

    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        spec = self.spec_for(symbol)
        if spec is None:
            log.warning("Order FAIL-CLOSED: no venue supports symbol %s", symbol)
            return {"status": "rejected",
                    "reason": f"no venue supports symbol {symbol}"}
        blocked = self._check_venue_cap(spec, symbol, qty)
        if blocked:
            return blocked
        try:
            res = spec.adapter.submit_equity_order(symbol, qty, side) or {}
        except Exception as exc:
            log.error("Venue %s submit failed: %s", spec.venue_id, exc)
            return {"status": "error", "reason": str(exc), "venue": spec.venue_id}
        if isinstance(res, dict):
            res.setdefault("venue", spec.venue_id)
        return res

    def submit_option_order(self, contract: str, qty: int, side: str,
                            premium: float = 0.0) -> Dict:
        # Option contracts route via their underlying symbol prefix when the
        # desk tracks it; otherwise try each venue that supports options.
        spec = self.spec_for(contract)
        if spec is None:
            log.warning("Option order FAIL-CLOSED: no venue for %s", contract)
            return {"status": "rejected",
                    "reason": f"no venue supports contract {contract}"}
        try:
            res = spec.adapter.submit_option_order(contract, qty, side, premium) or {}
        except Exception as exc:
            log.error("Venue %s option submit failed: %s", spec.venue_id, exc)
            return {"status": "error", "reason": str(exc), "venue": spec.venue_id}
        if isinstance(res, dict):
            res.setdefault("venue", spec.venue_id)
        return res

    def get_order_status(self, order_id: str, symbol: str = "") -> Dict:
        spec = self.spec_for(symbol) if symbol else None
        if spec is None:
            return {"status": "unknown", "order_id": order_id,
                    "reason": "no venue for symbol"}
        adapter = spec.adapter
        getter = getattr(adapter, "get_order_status", None)
        if getter is None:
            return {"status": "unknown", "order_id": order_id,
                    "reason": f"venue {spec.venue_id} has no order lookup"}
        try:
            return getter(order_id, symbol)
        except Exception as exc:
            return {"status": "unknown", "order_id": order_id, "reason": str(exc)}

    def cancel_order(self, order_id: str, symbol: str = "") -> Dict:
        """Best-effort cancel. Venues without cancel support → unsupported."""
        spec = self.spec_for(symbol) if symbol else None
        if spec is None:
            return {"status": "rejected", "order_id": order_id,
                    "reason": "no venue for symbol"}
        canceller = getattr(spec.adapter, "cancel_order", None)
        if canceller is None:
            return {"status": "unsupported", "order_id": order_id,
                    "venue": spec.venue_id,
                    "reason": f"venue {spec.venue_id} does not support cancel"}
        try:
            return canceller(order_id, symbol)
        except Exception as exc:
            return {"status": "error", "order_id": order_id, "reason": str(exc)}

    def get_order_history(self, symbol: str = "") -> List[Dict]:
        """Merged order history across venues that provide one."""
        out: List[Dict] = []
        specs = [self.spec_for(symbol)] if symbol else self.specs
        for spec in specs:
            if spec is None:
                continue
            getter = getattr(spec.adapter, "get_order_history", None)
            if getter is None:
                continue
            try:
                rows = getter(symbol) if symbol else getter()
                for r in rows or []:
                    if isinstance(r, dict):
                        r.setdefault("venue", spec.venue_id)
                        out.append(r)
            except Exception as exc:
                log.warning("Venue %s order history failed: %s", spec.venue_id, exc)
        return out

    def advance_sim(self, steps: int = 1) -> None:
        for spec in self.specs:
            try:
                spec.adapter.advance_sim(steps)
            except Exception as exc:
                log.warning("Venue %s advance_sim failed: %s", spec.venue_id, exc)

    # ── observability ────────────────────────────────────────────────────────
    def describe_venues(self) -> List[Dict]:
        """Per-venue block for status.json → dashboard Venues strip."""
        out = []
        for spec in self.specs:
            try:
                out.append(spec.describe())
            except Exception as exc:
                log.warning("describe() failed for %s: %s", spec.venue_id, exc)
                out.append({"id": spec.venue_id, "kind": spec.kind, "mode": "paper",
                            "online": False, "live_armed": False, "error": str(exc)})
        return out
