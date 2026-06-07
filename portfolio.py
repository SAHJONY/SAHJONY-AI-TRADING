# Portfolio management module for the trading firm

import time
from datetime import datetime
from db import TradingFirmDB
from strategy import TradingStrategy
from risk import RiskManager

class PortfolioManager:
    def __init__(self):
        self.db = TradingFirmDB()
        self.strategy = TradingStrategy()
        self.risk_manager = RiskManager()
        self.positions = {}
        self.cash = 1000000  # Starting cash balance
        self.portfolio_value = self.cash
    
    def update_portfolio_value(self):
        """Update the total portfolio value"""
        self.portfolio_value = self.cash
        # Add value of all positions to cash balance
        for symbol, position in self.positions.items():
            self.portfolio_value += position['value']
        return self.portfolio_value
    
    def get_portfolio_summary(self):
        """Get a summary of the current portfolio"""
        return {
            'cash': self.cash,
            'positions': self.positions,
            'total_value': self.portfolio_value,
            'timestamp': datetime.now().isoformat()
        }
    
    def add_position(self, symbol, quantity, avg_price):
        """Add a position to the portfolio"""
        self.positions[symbol] = {
            'quantity': quantity,
            'avg_price': avg_price,
            'value': quantity * avg_price
        }
        self.update_portfolio_value()
    
    def remove_position(self, symbol):
        """Remove a position from the portfolio"""
        if symbol in self.positions:
            del self.positions[symbol]
            self.update_portfolio_value()

# Initialize the portfolio manager
pm = PortfolioManager()
print("Portfolio manager initialized")