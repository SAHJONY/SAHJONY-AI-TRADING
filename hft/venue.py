"""Venue adapters (paper/sim implementations only).

* :class:`PaperVenue` wraps the :class:`hft.matching.MatchingEngine` and
  exposes a minimal submit/cancel interface for research code.
* :class:`AlpacaPaperVenue` routes orders to Alpaca's **paper trading**
  endpoint only (stocks/ETFs). The live Alpaca endpoint is hard-rejected,
  credentials must be passed explicitly (never read from disk/env here),
  and no HTTP request is ever made at import or construction time — the
  network is touched only when ``submit``/``cancel`` are actually called.
* :class:`LiveVenue` **cannot be constructed**: it raises
  ``NotImplementedError`` with an explicit explanation. Live high-frequency
  trading requires exchange membership, colocated infrastructure, direct
  market-data feeds, and deterministic microsecond networking — none of
  which exist in this package, and a retail-style venue (REST/web order
  entry) cannot do true HFT regardless.
"""

from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

from .book import L2OrderBook
from .matching import IncomingOrder, MatchingEngine, OrderResult


class Venue(ABC):
    """Minimal order-routing interface."""

    @abstractmethod
    def submit(self, order: IncomingOrder) -> OrderResult:
        ...

    @abstractmethod
    def cancel(self, client_order_id: str) -> bool:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


class PaperVenue(Venue):
    """In-memory simulated venue. No network, no real orders."""

    def __init__(self, tick_size: float = 0.01) -> None:
        self.book = L2OrderBook(tick_size=tick_size)
        self.engine = MatchingEngine(self.book)

    def submit(self, order: IncomingOrder) -> OrderResult:
        return self.engine.submit(order)

    def cancel(self, client_order_id: str) -> bool:
        return self.engine.cancel(client_order_id)

    def close(self) -> None:
        pass


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
_LIVE_BASE_URL = "https://api.alpaca.markets"

# Hard paper-only switch. Defense in depth alongside the __init__
# ValueError on non-paper URLs and the runtime assertion in _request().
PAPER_ONLY = True


class AlpacaPaperVenue(Venue):
    """Alpaca **paper trading** venue adapter (stocks/ETFs).

    Paper only, by construction:

    * ``base_url`` must be exactly the Alpaca paper endpoint — the live
      endpoint (or any other URL) raises ``ValueError``.
    * API key/secret must be passed explicitly as arguments. They are
      never read from environment files or disk by this class, and this
      module never logs or prints them.
    * No network activity happens at import or construction time. HTTPS
      requests are issued lazily, only when :meth:`submit` or
      :meth:`cancel` are called, using the standard library (``urllib``).

    Order-type mapping is best-effort: ``market``/``limit`` map directly;
    ``ioc``/``fok`` map to limit orders with the matching
    ``time_in_force``; ``post_only`` maps to a plain limit order (Alpaca
    has no native post-only flag — the no-cross guarantee is NOT
    enforced by this adapter, only by the local simulator). Fills are
    reported asynchronously by the paper venue; :meth:`submit` returns
    the accepted order with the full quantity as leaves.
    """

    def __init__(self, api_key: Optional[str] = None,
                 secret_key: Optional[str] = None,
                 base_url: str = PAPER_BASE_URL) -> None:
        if base_url != PAPER_BASE_URL:
            raise ValueError(
                "AlpacaPaperVenue supports ONLY the Alpaca paper endpoint "
                f"({PAPER_BASE_URL}); refusing {base_url!r}. Live trading "
                "is not supported by this adapter."
            )
        if not api_key or not secret_key:
            raise ValueError(
                "Alpaca paper API key and secret are required as explicit "
                "arguments. Use paper credentials only — never live keys."
            )
        self._api_key = api_key
        self._secret_key = secret_key
        self._base_url = base_url

    @property
    def paper_mode(self) -> bool:
        """Always True — this adapter has no live mode."""
        return PAPER_ONLY

    # -- plumbing (network only when actually called) -----------------
    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str,
                 body: Optional[dict] = None) -> dict:
        assert self._base_url == PAPER_BASE_URL, "refusing non-paper endpoint"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self._base_url + path, data=data, headers=self._headers(),
            method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            # Surface Alpaca's JSON error body (it explains 4xx rejections)
            try:
                detail = exc.read().decode()[:500]
            except Exception:
                detail = ""
            raise RuntimeError(
                f"alpaca {method} {path} -> HTTP {exc.code}: {detail}"
            ) from exc

    def submit(self, order: IncomingOrder, symbol: str = "") -> OrderResult:
        """Route one order to the Alpaca paper endpoint.

        ``symbol`` is required (e.g. ``"SPY"``); the simulator's
        :class:`IncomingOrder` carries no symbol field, so it is passed
        explicitly.
        """
        if not symbol:
            return OrderResult(status="rejected",
                               reason="symbol is required for Alpaca routing")
        tif = {"market": "day", "limit": "day", "ioc": "ioc",
               "fok": "fok", "post_only": "day"}.get(order.order_type, "day")
        body = {
            "symbol": symbol,
            "qty": order.qty,
            "side": "buy" if order.side == 1 else "sell",
            "type": "market" if order.order_type == "market" else "limit",
            "time_in_force": tif,
            "client_order_id": order.client_order_id,
        }
        if order.order_type != "market":
            if order.price is None:
                return OrderResult(status="rejected",
                                   reason="limit price required")
            body["limit_price"] = round(order.price * 0.01, 2)
        resp = self._request("POST", "/v2/orders", body)
        status = resp.get("status", "new")
        return OrderResult(status="new" if status in ("new", "accepted")
                           else status,
                           leaves_qty=order.qty,
                           reason=f"alpaca paper order id {resp.get('id')}")

    def cancel(self, client_order_id: str) -> bool:
        try:
            self._request("DELETE",
                          f"/v2/orders:client_order_id={client_order_id}")
            return True
        except Exception:
            return False

    def close(self) -> None:
        # credentials are held in memory only; drop references on close
        self._api_key = None  # type: ignore[assignment]
        self._secret_key = None  # type: ignore[assignment]


class LiveVenue(Venue):
    """Placeholder that refuses to exist.

    Instantiating this class raises ``NotImplementedError`` — deliberately.
    Connecting a research simulator to a live venue would require, at
    minimum: exchange membership and clearing arrangements, colocated
    servers with kernel-bypass networking, direct L2 market-data feeds,
    microsecond-accurate time sync, and pre-trade risk/fat-finger controls
    reviewed by compliance. This package provides none of that.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "LiveVenue is not implemented: live HFT needs colocated direct "
            "market access (exchange membership, direct data feeds, "
            "deterministic sub-100us networking). This package is a "
            "paper-only research simulator and will never place live orders."
        )

    def submit(self, order: IncomingOrder) -> OrderResult:  # pragma: no cover
        raise NotImplementedError

    def cancel(self, client_order_id: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        raise NotImplementedError
