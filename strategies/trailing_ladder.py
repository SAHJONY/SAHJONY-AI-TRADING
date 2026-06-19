import logging
from datetime import datetime
from utils.alpaca_client import AlpacaClient

log = logging.getLogger(__name__)

class TrailingLadderStrategy:
    """Equity ladder strategy (demo placeholder).
    - 10% absolute stop‑loss.
    - Dynamic trailing stop when profit >=10%.
    - Scale‑in buys at -20% and -30% drawdowns."""

    def __init__(self, client: AlpacaClient, ticker: str = 'AAPL', allocation: float = 0.20):
        self.client = client
        self.ticker = ticker
        self.allocation = allocation

    def run(self, state: dict) -> dict:
        log.info('Running TrailingLadderStrategy for %s', self.ticker)
        account = self.client.get_account()
        if not account:
            log.warning('No account info – aborting ladder step')
            return state
        equity = float(account.get('equity', 0))
        target_notional = equity * self.allocation
        log.debug('Target notional for ladder: $%.2f', target_notional)
        # Demo placeholder – real price fetching & order logic omitted
        log.info('[DEMO] Would evaluate price, set stop‑loss, trailing stop, and ladder‑in buys.')
        state.setdefault('ladder', []).append({
            'timestamp': datetime.utcnow().isoformat(),
            'ticker': self.ticker,
            'action': 'demo_ladder_cycle',
            'equity_used': target_notional,
        })
        return state
