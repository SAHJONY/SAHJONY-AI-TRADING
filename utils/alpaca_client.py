import logging\nfrom typing import Any, Dict, List, Optional\n\nfrom alpaca.trading.client import TradingClient\nfrom config import settings\n\nlog = logging.getLogger(__name__)\n\nclass AlpacaClient:\n    def __init__(self) -> None:\n        self.client = TradingClient(\n            api_key=settings.alpaca_api_key,\n            secret_key=settings.alpaca_api_secret,\n            paper=True,\n        )\n        log.info('Alpaca client initialised (paper trading)')\n\n    def get_account(self) -> Optional[Dict[str, Any]]:\n        try:\n            acc = self.client.get_account()\n            return acc.model_dump()\n        except Exception as exc:\n            log.error('Failed to fetch account: %s', exc)\n            return None\n\n    def get_positions(self) -> List[Dict[str, Any]]:\n        try:\n            positions = self.client.get_all_positions()\n            return [p.model_dump() for p in positions]\n        except Exception as exc:\n            log.error('Failed to list positions: %s', exc)\n            return []\n\n    def submit_order(self, **order_kwargs: Any) -> Optional[Dict[str, Any]]:\n        Wrapper
around
client.submit_order
–
accepts
any
kwargs
accepted
by
Alpaca.\n        try:\n            order = self.client.submit_order(**order_kwargs)\n            log.info('Order submitted: %s', order)\n            return order.model_dump()\n        except Exception as exc:\n            log.error('Order submission failed: %s', exc)\n            return None
