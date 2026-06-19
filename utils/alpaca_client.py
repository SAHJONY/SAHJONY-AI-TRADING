import logging
from typing import Any, Dict, List, Optional

from alpaca.trading.client import TradingClient
from config import settings

log = logging.getLogger(__name__)

class AlpacaClient:
    def __init__(self) -> None:
        self.client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_api_secret,
            paper=True,
        )
        log.info('Alpaca client initialized (paper trading)')

    def get_account(self) -> Optional[Dict[str, Any]]:
        try:
            acc = self.client.get_account()
            return acc.model_dump()
        except Exception as exc:
            log.error('Failed to fetch account: %s', exc)
            return None

    def get_positions(self) -> List[Dict[str, Any]]:
        try:
            positions = self.client.get_all_positions()
            return [p.model_dump() for p in positions]
        except Exception as exc:
            log.error('Failed to list positions: %s', exc)
            return []

    def submit_order(self, **order_kwargs: Any) -> Optional[Dict[str, Any]]:
        """Submit an order to Alpaca.
        Accepts any kwargs accepted by ``TradingClient.submit_order``.
        Returns the order model as a dict on success, ``None`` on failure.
        """
        try:
            order = self.client.submit_order(**order_kwargs)
            log.info('Order submitted: %s', order)
            return order.model_dump()
        except Exception as exc:
            log.error('Order submission failed: %s', exc)
            return None

