import logging
from datetime import datetime
from utils.alpaca_client import AlpacaClient

log = logging.getLogger(__name__)

class WheelStrategy:
    """Simple options-wheel implementation (demo placeholder).
    1. Sell 10 % OTM puts on a ticker.
    2. If assigned, buy underlying.
    3. Sell 10 % OTM covered calls.
    """

    def __init__(self, client: AlpacaClient, ticker: str = 'AAPL', allocation: float = 0.10):
        self.client = client
        self.ticker = ticker
        self.allocation = allocation

    def run(self, state: dict) -> dict:
        log.info('Running WheelStrategy for %s', self.ticker)
        account = self.client.get_account()
        if not account:
            log.warning('No account info – aborting wheel step')
            return state
        equity = float(account.get('equity', 0))
        target_notional = equity * self.allocation
        log.debug('Target notional for wheel: $%.2f', target_notional)
        # Demo placeholder – actual option market data not fetched here
        log.info('[DEMO] Would sell %s OTM puts, buy on assignment, then sell covered calls.', self.ticker)
        state.setdefault('wheel', []).append({
            'timestamp': datetime.utcnow().isoformat(),
            'ticker': self.ticker,
            'action': 'demo_wheel_cycle',
            'equity_used': target_notional,
        })
        return state
