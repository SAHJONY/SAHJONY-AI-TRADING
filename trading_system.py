# Main trading system that integrates all components

import time
from datetime import datetime
from db import TradingFirmDB
from strategy import TradingStrategy
from risk import RiskManager
from portfolio import PortfolioManager

class TradingSystem:
    def __init__(self):
        self.db = TradingFirmDB()
        self.strategy = TradingStrategy()
        self.risk = RiskManager()
        self.portfolio = PortfolioManager()
    
    def run_trading_session(self):
        """Run a complete trading session"""
        print("Starting trading session...")
        
        # Get portfolio summary
        portfolio_summary = self.portfolio.get_portfolio_summary()
        print(f"Current portfolio value: ${portfolio_summary['total_value']:,.2f}")
        
        # Generate trade signals for a few sample symbols
        symbols = ['NVDA', 'TSLA', 'AAPL', 'MSFT', 'GOOGL']
        for symbol in symbols:
            current_price = 100.0  # Placeholder price
            signal = self.strategy.generate_trade_signal(symbol, current_price)
            if signal:
                print(f"Generated signal for {symbol}: {signal}")
        
        print("Trading session completed.")
    
    def get_status(self):
        """Get the status of all system components"""
        return {
            'database': 'Operational',
            'strategy': 'Operational',
            'risk': 'Operational',
            'portfolio': 'Operational'
        }

# Initialize the trading system
ts = TradingSystem()
print("Trading system initialized")