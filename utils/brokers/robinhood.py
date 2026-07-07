"""Robinhood adapter (BROKER=robinhood) — official Robinhood Crypto Trading API.

Trades crypto 24/7 through Robinhood's public, Ed25519-signed Crypto Trading API
(the API-key + private-key pair issued in the Robinhood app). If PyNaCl or the
credentials are missing, if the connection fails, or if live trading is not
explicitly armed, it degrades to the shared SimBroker (ZERO real orders) — like
every adapter, the loop never crashes (fault isolation, per CLAUDE.md).

⚠️ REAL MONEY, NO SANDBOX. Robinhood exposes no paper venue for the Crypto API,
so this adapter is deliberately DOUBLE-LOCKED before it will place a single real
order:

    1. ROBINHOOD_LIVE=true            (arm THIS venue for real orders)
    2. LIVE_TRADING_ACK="I_UNDERSTAND_REAL_MONEY"   (the desk-wide real-money ack)

With either missing it runs OFFLINE-SIM. When both are set it reports mode="LIVE",
which additionally routes through main.py's confirm_live() 5-second abort gate and
the risk engine's hard ceilings (config.py) — real orders are never unattended.

⚠️ UNTESTED AGAINST A LIVE ACCOUNT in this repo's CI. It is written to Robinhood's
documented Crypto Trading API; validate it with `python main.py --preflight` (a
read-only connection/funding/data check) BEFORE arming live. Robinhood's Crypto
API has no historical-candle endpoint, so get_history returns empty in live mode
— strategies that need history produce no signal (and therefore no trade) rather
than trading on synthetic data.

Symbols use the desk's crypto convention (BTC/USD, ETH/USD); they are mapped to
Robinhood's dash form (BTC-USD) at the API boundary.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Dict, List

import numpy as np

from config import Config
from utils.logger import get_logger
from utils.sim_broker import SimBroker

log = get_logger("robinhood")

_HOST = "https://trading.robinhood.com"
_ACCOUNTS = "/api/v1/crypto/trading/accounts/"
_HOLDINGS = "/api/v1/crypto/trading/holdings/"
_ORDERS = "/api/v1/crypto/trading/orders/"
_BEST_BID_ASK = "/api/v1/crypto/marketdata/best_bid_ask/"


class RobinhoodBroker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._sim = SimBroker(cfg)
        self._signing_key = None
        self._live = False
        self.mode = "offline-sim"
        self._connect()

    # ── connection / arming ─────────────────────────────────────────────────────
    def _connect(self) -> None:
        """Arm live trading ONLY when creds + PyNaCl + both safety flags are present
        AND the account endpoint answers. Any gap → OFFLINE-SIM (zero real orders)."""
        if not (self.cfg.robinhood_api_key and self.cfg.robinhood_private_key):
            log.warning("No Robinhood credentials → OFFLINE-SIM mode (no real orders).")
            return
        # The desk-wide real-money ack AND this venue's own arm flag are both required.
        if not (self.cfg.robinhood_live and self.cfg.live_trading_ack):
            log.warning("Robinhood credentials present but live NOT armed "
                        "(need ROBINHOOD_LIVE=true and LIVE_TRADING_ACK) → OFFLINE-SIM.")
            return
        try:
            from nacl.signing import SigningKey
            self._signing_key = SigningKey(base64.b64decode(self.cfg.robinhood_private_key))
        except Exception as exc:  # PyNaCl missing / malformed key → safe sim
            log.error("Robinhood key/PyNaCl unavailable (%s) → OFFLINE-SIM (no real orders).", exc)
            self._signing_key = None
            return
        acct = self._request("GET", _ACCOUNTS)
        if acct is None or "buying_power" not in acct:
            log.error("Robinhood account probe failed → OFFLINE-SIM (no real orders).")
            self._signing_key = None
            return
        self._live = True
        self.mode = "LIVE"
        log.info("Connected to Robinhood Crypto (LIVE, armed). Account %s.",
                 acct.get("account_number", "?"))

    @property
    def online(self) -> bool:
        return self._live and self._signing_key is not None

    def advance_sim(self, steps: int = 1) -> None:
        if not self.online:
            self._sim.advance_sim(steps)

    # ── signed transport ─────────────────────────────────────────────────────────
    def _headers(self, method: str, path: str, body: str) -> Dict[str, str]:
        ts = str(int(time.time()))
        # Robinhood signs the concatenation: api_key + timestamp + path + method + body
        message = f"{self.cfg.robinhood_api_key}{ts}{path}{method.upper()}{body}"
        sig = self._signing_key.sign(message.encode("utf-8")).signature
        return {
            "x-api-key": self.cfg.robinhood_api_key,
            "x-timestamp": ts,
            "x-signature": base64.b64encode(sig).decode("utf-8"),
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body_obj=None):
        """Signed request. Returns parsed JSON, or None on ANY failure (fault
        isolation — a broker/network error must never crash the trading loop)."""
        if self._signing_key is None:
            return None
        body = json.dumps(body_obj) if body_obj is not None else ""
        try:
            req = urllib.request.Request(
                _HOST + path,
                data=body.encode("utf-8") if body else None,
                headers=self._headers(method, path, body),
                method=method.upper(),
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:
                pass
            log.error("Robinhood %s %s → HTTP %s %s", method, path, exc.code, detail)
            return None
        except Exception as exc:
            log.error("Robinhood %s %s failed: %s", method, path, exc)
            return None

    # ── symbol helpers ───────────────────────────────────────────────────────────
    def _rh_symbol(self, symbol: str) -> str:
        """Desk form (BTC/USD or BTC) → Robinhood form (BTC-USD)."""
        s = symbol.upper().replace("/", "-")
        return s if "-" in s else f"{s}-{self.cfg.robinhood_quote}"

    def _asset_code(self, symbol: str) -> str:
        return self._rh_symbol(symbol).split("-", 1)[0]

    # ── account / positions ─────────────────────────────────────────────────────
    def get_account(self) -> Dict[str, float]:
        if not self.online:
            return self._sim.get_account()
        acct = self._request("GET", _ACCOUNTS)
        cash = float((acct or {}).get("buying_power", 0.0) or 0.0)
        equity = cash + sum(p["market_value"] for p in self.get_broker_positions().values())
        return {"equity": equity, "cash": cash, "buying_power": cash}

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        if not self.online:
            return self._sim.get_broker_positions()
        data = self._request("GET", _HOLDINGS)
        out: Dict[str, Dict[str, float]] = {}
        for h in (data or {}).get("results", []) or []:
            code = str(h.get("asset_code", "")).upper()
            qty = float(h.get("total_quantity", 0.0) or 0.0)
            if not code or qty == 0:
                continue
            sym = f"{code}/{self.cfg.robinhood_quote}"
            px = self.get_price(sym)
            out[sym] = {"qty": qty, "avg_price": 0.0, "market_value": qty * px}
        return out

    # ── market data ──────────────────────────────────────────────────────────────
    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        if not self.online:
            return self._sim.get_history(symbol, days)
        # Robinhood's Crypto Trading API exposes no OHLCV/candle endpoint. Return
        # empty arrays so history-dependent estimators emit NO signal (and thus no
        # real trade) rather than trading on synthetic data. Supply a candle feed
        # via a data-only adapter if you need history-based strategies live.
        return {"closes": np.array([]), "volumes": np.array([])}

    def get_price(self, symbol: str) -> float:
        if not self.online:
            return self._sim.get_price(symbol)
        rh = self._rh_symbol(symbol)
        data = self._request("GET", f"{_BEST_BID_ASK}?symbol={rh}")
        rows = (data or {}).get("results", []) or []
        if not rows:
            return 0.0
        row = rows[0]
        bid = float(row.get("bid_inclusive_of_sell_spread", 0.0) or 0.0)
        ask = float(row.get("ask_inclusive_of_buy_spread", 0.0) or 0.0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        return float(row.get("price", 0.0) or 0.0)

    def is_market_open(self) -> bool:
        return True   # crypto trades 24/7/365

    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        return self._sim.get_option_chain(symbol, spot, dte_min, dte_max, vol, kinds)

    # ── orders ───────────────────────────────────────────────────────────────────
    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        side = side.lower()
        if qty <= 0:
            return {"status": "rejected", "reason": "qty<=0"}
        # Defense in depth: refuse a real order unless fully armed, even if some
        # other code path reached us with online False.
        if not self.online:
            return self._sim.submit_equity_order(symbol, qty, side)
        rh = self._rh_symbol(symbol)
        body = {
            "client_order_id": str(uuid.uuid4()),
            "side": side,
            "symbol": rh,
            "type": "market",
            "market_order_config": {"asset_quantity": f"{float(qty):.8f}"},
        }
        order = self._request("POST", _ORDERS, body)
        if not order or "id" not in order:
            return {"status": "error", "reason": "robinhood order rejected (see logs)"}
        log.info("ROBINHOOD ORDER %s %s x%.8f id=%s", side, rh, float(qty), order["id"])
        return {"status": "submitted", "id": str(order["id"]), "symbol": symbol,
                "qty": float(qty), "side": side, "simulated": False}

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        return self._sim.submit_option_order(contract, qty, side, premium)   # no crypto options
