"""Robinhood Agentic Trading MCP adapter through a local authenticated gateway.

The remote Robinhood MCP uses interactive OAuth managed by an MCP-capable client.
This adapter therefore never stores Robinhood browser credentials or OAuth tokens.
It talks only to a local gateway that has already authenticated the official
Robinhood Trading MCP and exposes the small, typed contract documented below.

Required environment:
  BROKER=robinhood_mcp
  ROBINHOOD_MCP_GATEWAY_URL=http://127.0.0.1:8787
  ROBINHOOD_MCP_GATEWAY_TOKEN=<random local bearer token>
  ROBINHOOD_MCP_EXPECTED_LAST4=1131

Real orders are triple-locked and fail closed. All must be true:
  ROBINHOOD_MCP_LIVE=true
  LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY
  the gateway reports the authenticated Agentic account ending in EXPECTED_LAST4

Gateway contract:
  GET  /health
  GET  /account
  GET  /positions
  GET  /quotes/{symbol}
  GET  /history/{symbol}?days=N       optional
  POST /orders/preview               required before every live order
  POST /orders                       submits an approved preview

No option orders are supported by this adapter until the gateway explicitly
implements and advertises them.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import numpy as np
import requests

from config import Config
from utils.logger import get_logger
from utils.sim_broker import SimBroker

log = get_logger("robinhood_mcp")


class RobinhoodMCPBroker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._sim = SimBroker(cfg)
        self.base_url = os.getenv("ROBINHOOD_MCP_GATEWAY_URL", "").strip().rstrip("/")
        self.token = os.getenv("ROBINHOOD_MCP_GATEWAY_TOKEN", "").strip()
        self.expected_last4 = os.getenv("ROBINHOOD_MCP_EXPECTED_LAST4", "1131").strip()
        self.live_requested = os.getenv("ROBINHOOD_MCP_LIVE", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.live_ack = os.getenv("LIVE_TRADING_ACK", "").strip() == "I_UNDERSTAND_REAL_MONEY"
        self._online = False
        self._identity_verified = False
        self._account: Dict[str, Any] = {}
        self.mode = "offline-sim"
        self._connect()

    @property
    def online(self) -> bool:
        return self._online

    @property
    def trading_armed(self) -> bool:
        return self._online and self._identity_verified and self.live_requested and self.live_ack

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, *, payload: Dict[str, Any] | None = None) -> Any:
        if not self.base_url:
            return None
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except Exception as exc:
            log.error("Robinhood MCP gateway %s %s failed: %s", method, path, exc)
            return None

    def _connect(self) -> None:
        if not self.base_url or not self.token:
            log.warning("Robinhood MCP gateway not configured -> OFFLINE-SIM (no real orders).")
            return
        health = self._request("GET", "/health")
        account = self._request("GET", "/account")
        if not isinstance(health, dict) or not health.get("ok") or not isinstance(account, dict):
            log.error("Robinhood MCP gateway/account probe failed -> OFFLINE-SIM.")
            return
        last4 = str(account.get("account_number_last4") or account.get("last4") or "")[-4:]
        account_type = str(account.get("account_type", "")).lower()
        status = str(account.get("status", "")).lower()
        self._identity_verified = (
            bool(self.expected_last4)
            and last4 == self.expected_last4
            and "agentic" in account_type
            and status in {"active", "open", "enabled"}
        )
        if not self._identity_verified:
            log.error(
                "Robinhood MCP identity mismatch: expected Agentic ***%s, got type=%s last4=***%s status=%s",
                self.expected_last4,
                account_type or "unknown",
                last4 or "unknown",
                status or "unknown",
            )
            return
        self._account = account
        self._online = True
        self.mode = "LIVE" if self.trading_armed else "live-data"
        log.info(
            "Connected to Robinhood Trading MCP — %s. Agentic account ***%s.",
            "LIVE TRADING ARMED" if self.trading_armed else "READ-ONLY LIVE DATA (no orders)",
            last4,
        )

    def get_account(self) -> Dict[str, float]:
        if not self.online:
            return self._sim.get_account()
        account = self._request("GET", "/account") or self._account
        return {
            "equity": float(account.get("equity", 0.0) or 0.0),
            "cash": float(account.get("cash", 0.0) or 0.0),
            "buying_power": float(account.get("buying_power", 0.0) or 0.0),
        }

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        if not self.online:
            return self._sim.get_broker_positions()
        payload = self._request("GET", "/positions") or {}
        rows = payload.get("positions", payload if isinstance(payload, list) else [])
        result: Dict[str, Dict[str, float]] = {}
        for row in rows or []:
            symbol = str(row.get("symbol", "")).upper()
            if not symbol:
                continue
            result[symbol] = {
                "qty": float(row.get("qty", row.get("quantity", 0.0)) or 0.0),
                "market_value": float(row.get("market_value", 0.0) or 0.0),
                "avg_entry_price": float(row.get("avg_entry_price", row.get("average_price", 0.0)) or 0.0),
            }
        return result

    def get_price(self, symbol: str) -> float:
        if not self.online:
            return self._sim.get_price(symbol)
        payload = self._request("GET", f"/quotes/{symbol.upper()}") or {}
        price = float(payload.get("price", payload.get("last", 0.0)) or 0.0)
        if price <= 0:
            raise RuntimeError(f"No valid MCP quote for {symbol}")
        return price

    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        if not self.online:
            return self._sim.get_history(symbol, days)
        payload = self._request("GET", f"/history/{symbol.upper()}?days={int(days)}") or {}
        closes = np.asarray(payload.get("closes", []), dtype=float)
        volumes = np.asarray(payload.get("volumes", []), dtype=float)
        return {"closes": closes, "volumes": volumes}

    def is_market_open(self) -> bool:
        if not self.online:
            return self._sim.is_market_open()
        health = self._request("GET", "/health") or {}
        return bool(health.get("market_open", False))

    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        return []

    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        if not self.trading_armed:
            return {
                "status": "rejected",
                "simulated": False,
                "reason": "Robinhood MCP live trading is not armed or identity is unverified",
            }
        order = {"symbol": symbol.upper(), "qty": float(qty), "side": side.lower(), "type": "market"}
        preview = self._request("POST", "/orders/preview", payload=order)
        if not isinstance(preview, dict) or not preview.get("approved"):
            return {"status": "rejected", "simulated": False, "reason": "order preview rejected"}
        preview_id = preview.get("preview_id")
        if not preview_id:
            return {"status": "rejected", "simulated": False, "reason": "missing preview_id"}
        result = self._request("POST", "/orders", payload={"preview_id": preview_id})
        if not isinstance(result, dict):
            return {"status": "rejected", "simulated": False, "reason": "gateway submission failed"}
        result.setdefault("simulated", False)
        return result

    def submit_option_order(self, contract: str, qty: int, side: str, premium: float = 0.0) -> Dict:
        return {
            "status": "rejected",
            "simulated": False,
            "reason": "options are not enabled for the Robinhood MCP adapter",
        }

    def advance_sim(self, steps: int = 1) -> None:
        if not self.online:
            self._sim.advance_sim(steps)
