"""Robinhood Crypto broker adapter — REAL MONEY (official Crypto Trading API).

⚠️  SAFETY CONTRACT (read before touching):
  • Robinhood Crypto has NO paper/sandbox — every live order moves real money.
  • This adapter therefore DEFAULTS TO DRY-RUN: it builds and signs the request,
    logs the intended order, and places NOTHING. It will only place a real order
    when BOTH gates are set by the operator, deliberately:
        LIVE_TRADING_ACK = "I_UNDERSTAND_REAL_MONEY"
        ROBINHOOD_LIVE   = "true"
  • Even when armed, per-order notional is capped by ROBINHOOD_MAX_ORDER_USD and
    the desk's existing risk engine still gates size/conviction upstream.
  • Auth (Ed25519 signing) cannot be verified without live credentials — run the
    READ-ONLY check first: `python -m scripts.robinhood_check` (moves no money).

Only the official CRYPTO API is implemented — Robinhood has no official stock
API, and automating stocks via unofficial login/MFA libraries risks an account
lockout, so it is intentionally NOT built here.

API shape (official): host https://trading.robinhood.com
  headers: x-api-key, x-timestamp, x-signature (base64 Ed25519)
  signed message = f"{api_key}{timestamp}{path}{method}{body}"
  GET  /api/v1/crypto/trading/accounts/
  GET  /api/v1/crypto/trading/holdings/
  GET  /api/v1/crypto/marketdata/best_bid_ask/?symbol=BTC-USD
  POST /api/v1/crypto/trading/orders/   body: {client_order_id, side, symbol,
        type:"market", market_order_config:{asset_quantity:"..."}}
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Dict, List

import numpy as np

from config import Config
from utils.logger import get_logger

log = get_logger("robinhood_crypto")

_HOST = "https://trading.robinhood.com"
_ACK_PHRASE = "I_UNDERSTAND_REAL_MONEY"


def _rh_symbol(sym: str) -> str:
    """Normalize a desk symbol to Robinhood's 'BTC-USD' form ('BTC/USD' or 'BTC')."""
    s = sym.upper().replace("/", "-")
    return s if "-" in s else f"{s}-USD"


class RobinhoodCryptoBroker:
    """BrokerAdapter for Robinhood Crypto. Real-money orders are hard-gated;
    unarmed it is a dry-run venue that prices from live market data but places
    no orders (so the desk can run end-to-end and log intended trades safely)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.api_key = (os.getenv("ROBINHOOD_API_KEY", "") or "").strip()
        # Base64-encoded Ed25519 private-key seed (single line — NOT a PEM block).
        priv_b64 = (os.getenv("ROBINHOOD_PRIVATE_KEY", "") or "").strip()
        self._signer = None
        if self.api_key and priv_b64:
            try:
                import nacl.signing  # lazy: package optional until you go live
                seed = base64.b64decode(priv_b64)
                # RH provides a 32-byte seed; some tooling exports the 64-byte
                # signing key — take the first 32 (the seed) either way.
                self._signer = nacl.signing.SigningKey(seed[:32])
            except Exception as exc:
                log.error("Robinhood signer init failed (%s) — auth disabled", exc)
                self._signer = None

        self.armed = (cfg.live_trading_ack == _ACK_PHRASE
                      and (os.getenv("ROBINHOOD_LIVE", "") or "").strip().lower() == "true"
                      and self._signer is not None)
        try:
            self.max_order_usd = float(os.getenv("ROBINHOOD_MAX_ORDER_USD", "25") or 25)
        except (TypeError, ValueError):
            self.max_order_usd = 25.0
        self._price_cache: Dict[str, float] = {}

    # ── BrokerAdapter surface ────────────────────────────────────────────────
    @property
    def online(self) -> bool:
        return self._signer is not None

    @property
    def mode(self) -> str:
        # Only report LIVE when fully armed — main.confirm_live() then forces the
        # operator's deliberate 5-second real-money confirmation. Unarmed, we
        # report a distinct dry-run mode so nothing treats it as tradable-for-real.
        return "LIVE" if self.armed else "robinhood-dryrun"

    # ── signed request core ──────────────────────────────────────────────────
    def _headers(self, method: str, path: str, body: str) -> Dict[str, str]:
        ts = str(int(time.time()))
        message = f"{self.api_key}{ts}{path}{method}{body}"
        sig = self._signer.sign(message.encode("utf-8")).signature
        return {
            "x-api-key": self.api_key,
            "x-timestamp": ts,
            "x-signature": base64.b64encode(sig).decode("utf-8"),
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body_obj=None) -> Dict:
        if self._signer is None:
            raise RuntimeError("Robinhood not authenticated (missing API key / private key)")
        import requests
        body = json.dumps(body_obj, separators=(",", ":")) if body_obj is not None else ""
        r = requests.request(method, _HOST + path, headers=self._headers(method, path, body),
                             data=body or None, timeout=20)
        if not r.ok:
            raise RuntimeError(f"Robinhood {method} {path} → HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if r.text else {}

    # ── read-only market + account (safe; no money moves) ─────────────────────
    def get_account(self) -> Dict[str, float]:
        try:
            acct = self._request("GET", "/api/v1/crypto/trading/accounts/")
            bp = float(acct.get("buying_power", 0.0) or 0.0)
            # crypto holdings value
            hv = 0.0
            for h in self.get_broker_positions().values():
                hv += float(h.get("market_value", 0.0) or 0.0)
            return {"equity": bp + hv, "cash": bp, "buying_power": bp}
        except Exception as exc:
            log.error("get_account failed: %s", exc)
            return {"equity": 0.0, "cash": 0.0, "buying_power": 0.0}

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        try:
            data = self._request("GET", "/api/v1/crypto/trading/holdings/")
            out: Dict[str, Dict[str, float]] = {}
            for h in data.get("results", []) or []:
                sym = h.get("asset_code", "")
                qty = float(h.get("total_quantity", 0.0) or 0.0)
                if sym and qty:
                    px = self.get_price(f"{sym}-USD")
                    out[f"{sym}-USD"] = {"qty": qty, "market_value": qty * px}
            return out
        except Exception as exc:
            log.error("get_broker_positions failed: %s", exc)
            return {}

    def get_price(self, symbol: str) -> float:
        rh = _rh_symbol(symbol)
        try:
            data = self._request("GET", f"/api/v1/crypto/marketdata/best_bid_ask/?symbol={rh}")
            res = (data.get("results") or [{}])[0]
            bid = float(res.get("bid_inclusive_of_sell_spread", res.get("bid_price", 0)) or 0)
            ask = float(res.get("ask_inclusive_of_buy_spread", res.get("ask_price", 0)) or 0)
            mid = (bid + ask) / 2 if (bid and ask) else (bid or ask)
            if mid > 0:
                self._price_cache[rh] = mid
            return mid
        except Exception as exc:
            log.error("get_price(%s) failed: %s", symbol, exc)
            return self._price_cache.get(rh, 0.0)

    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        # The trading API doesn't serve OHLC candles; the council degrades safely
        # on a short/empty series (low confidence, neutral — see agents.clamp).
        px = self.get_price(symbol)
        closes = np.array([px] * 2, dtype=float) if px > 0 else np.array([], dtype=float)
        return {"closes": closes, "volumes": np.array([], dtype=float)}

    def is_market_open(self) -> bool:
        return True   # crypto trades 24/7

    def get_option_chain(self, symbol, spot, dte_min, dte_max, vol, kinds=("put", "call")) -> List[Dict]:
        return []     # no options on Robinhood Crypto

    def advance_sim(self, steps: int = 1) -> None:
        return None   # live venue — nothing to advance

    # ── orders (HARD-GATED) ────────────────────────────────────────────────────
    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        """The desk routes equity-style orders here; for a crypto venue they are
        crypto orders. Real placement requires the deliberate arming gates."""
        rh = _rh_symbol(symbol)
        side = side.lower()
        px = self.get_price(rh)
        notional = qty * px
        if notional > self.max_order_usd:
            log.warning("Robinhood order %s %s ~$%.2f exceeds ROBINHOOD_MAX_ORDER_USD $%.2f — blocked",
                        side, rh, notional, self.max_order_usd)
            return {"status": "rejected", "reason": "exceeds ROBINHOOD_MAX_ORDER_USD"}

        body = {"client_order_id": str(uuid.uuid4()), "side": side, "symbol": rh,
                "type": "market", "market_order_config": {"asset_quantity": f"{qty}"}}

        if not self.armed:
            log.warning("DRY-RUN (not armed): would place %s %s qty=%s (~$%.2f). "
                        "Set LIVE_TRADING_ACK + ROBINHOOD_LIVE=true to place real orders.",
                        side, rh, qty, notional)
            return {"status": "filled", "symbol": rh, "qty": qty, "side": side,
                    "fill_price": px, "simulated": True, "dry_run": True}
        try:
            res = self._request("POST", "/api/v1/crypto/trading/orders/", body)
            log.info("ROBINHOOD LIVE ORDER placed: %s %s qty=%s → %s", side, rh, qty, res.get("id"))
            return {"status": "submitted", "symbol": rh, "qty": qty, "side": side,
                    "fill_price": px, "simulated": False, "order_id": res.get("id")}
        except Exception as exc:
            log.error("Robinhood live order failed: %s", exc)
            return {"status": "rejected", "reason": str(exc)}

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        return {"status": "rejected", "reason": "Robinhood Crypto has no options"}
