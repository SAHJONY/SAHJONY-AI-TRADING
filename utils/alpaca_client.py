"""Alpaca client wrapper for the autonomous trading bot.
Provides a singleton Alpaca REST client with basic error handling and logging.
"""
import logging
from typing import Any, Dict, List
from alpaca_trade_api.rest import REST

logger = logging.getLogger("alpaca_client")
handler = logging.FileHandler("logs/bot.log")
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class AlpacaClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AlpacaClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://paper-api.alpaca.markets"):
        if getattr(self, "_initialized", False):
            return
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        try:
            self.rest = REST(api_key, secret_key, base_url, api_version="v2")
            logger.info("Alpaca client initialized")
        except Exception as e:
            logger.exception("Failed to initialize Alpaca client: %s", e)
            raise
        self._initialized = True

    # Helper methods -------------------------------------------------
    def get_account(self) -> Dict[str, Any]:
        try:
            return self.rest.get_account()._raw
        except Exception as e:
            logger.exception("get_account error: %s", e)
            return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        try:
            return self.rest.list_positions()
        except Exception as e:
            logger.exception("list_positions error: %s", e)
            return []

    def submit_order(self, **order_kwargs) -> Any:
        """Submit an order; kwargs follow Alpaca REST spec.
        Returns the order response or None on failure.
        """
        try:
            order = self.rest.submit_order(**order_kwargs)
            logger.info("Order submitted: %s", order)
            return order
        except Exception as e:
            logger.exception("submit_order error: %s", e)
            return None

    # Additional convenient wrappers can be added as needed.

# Factory function for easy import
def get_client():
    from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER_URL
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        raise EnvironmentError("Alpaca API credentials not set in environment or .env file.")
    return AlpacaClient(ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER_URL)
