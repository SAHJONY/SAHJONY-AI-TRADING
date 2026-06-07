# Trading simulator that executes trades based on strategy signals

import random
import time
from datetime import datetime
from trading_system import TradingSystem

class TradingSimulator:
    def __init__(self):
        self.trading_system = TradingSystem()
        self.current_prices = {
            'NVDA': 100.0,
            'TSLA': 200.0,
            'AAPL': 150.0,
            'MSFT': 300.0,
            'GOOGL': 2500.0
        }
    
    def simulate_trading_day(self):
        """Simulate a day of trading"""
        print("Starting simulated trading day...")
        
        # Run a trading session
        self.trading_system.run_trading_session()
        
        # Simulate some price movements
        for symbol in self.current_prices:
            # Random price movement
            self.current_prices[symbol] *= random.uniform(0.95, 1.05)
        
        print("Simulated trading day completed.")
    
    def get_status(self):
        """Get the status of the trading system"""
        return self.trading_system.get_status()

# Initialize the simulator
simulator = TradingSimulator()
print("Trading simulator initialized")