"""DEX broker adapter.

Phase 1 is intentionally quote/simulation/approval only. It can source routes
across DEX liquidity through an aggregator, but it cannot hold a private key,
sign, or broadcast a transaction. This prevents an AI process from having
unrestricted wallet authority.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from config import Config
from utils.dex import DEXRouter, DEXSafetyError
from utils.logger import get_logger
from utils.sim_broker import SimBroker

log = get_logger("dex")


class DEXBroker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._sim = SimBroker(cfg)
        self.mode = "approval-required" if self._configured else "offline-sim"

    @property
    def _configured(self) -> bool:
        return bool(self.cfg.dex_api_key and self.cfg.dex_wallet_address)

    @property
    def online(self) -> bool:
        return self._configured

    def _router(self) -> DEXRouter:
        return DEXRouter(
            provider=self.cfg.dex_provider,
            api_key=self.cfg.dex_api_key,
            chain_id=self.cfg.dex_chain_id,
            wallet_address=self.cfg.dex_wallet_address,
            token_allowlist=self.cfg.dex_token_allowlist,
            max_slippage_bps=self.cfg.dex_max_slippage_bps,
        )

    def advance_sim(self, steps: int = 1) -> None:
        self._sim.advance_sim(steps)

    def get_account(self) -> Dict[str, float]:
        return self._sim.get_account()

    def get_broker_positions(self) -> Dict[str, Dict[str, float]]:
        return self._sim.get_broker_positions()

    def get_history(self, symbol: str, days: int = 120) -> Dict[str, np.ndarray]:
        return self._sim.get_history(symbol, days)

    def get_price(self, symbol: str) -> float:
        return self._sim.get_price(symbol)

    def is_market_open(self) -> bool:
        return True

    def get_option_chain(self, symbol: str, spot: float, dte_min: int, dte_max: int,
                         vol: float, kinds=("put", "call")) -> List[Dict]:
        return []

    def prepare_swap(self, sell_token: str, buy_token: str, sell_amount: int) -> Dict:
        try:
            quote = self._router().quote(sell_token, buy_token, sell_amount)
        except (DEXSafetyError, Exception) as exc:
            log.error("DEX quote rejected: %s", exc)
            return {"status": "rejected", "reason": str(exc), "simulated": True}
        return {
            "status": "approval_required",
            "provider": quote.provider,
            "chain_id": quote.chain_id,
            "sell_amount": quote.sell_amount,
            "buy_amount": quote.buy_amount,
            "minimum_buy_amount": quote.minimum_buy_amount,
            "allowance_target": quote.allowance_target,
            "transaction": quote.transaction,
            "liquidity_sources": list(quote.liquidity_sources),
            "simulated": True,
            "broadcast": False,
        }

    def submit_equity_order(self, symbol: str, qty: float, side: str) -> Dict:
        # Symbol/quantity lack token addresses and base-unit decimals, so generic
        # equity orders must never be guessed into an on-chain transaction.
        if not self.online:
            return self._sim.submit_equity_order(symbol, qty, side)
        return {
            "status": "rejected",
            "reason": "use prepare_swap with token addresses and base-unit amount",
            "simulated": True,
        }

    def submit_option_order(self, contract: str, qty: int, side: str,
                            premium: float = 0.0) -> Dict:
        return {"status": "rejected", "reason": "DEX spot adapter has no options",
                "simulated": True}
