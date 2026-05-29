# ─────────────────────────────────────────────────────────────
# Market Data Simulator - Feed Generator
# Generates realistic simulated market data for testing
# ─────────────────────────────────────────────────────────────

import random
import time
import json
import os
import math
import threading
from datetime import datetime, timezone
from typing import Dict, List

# Configuration from environment
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:19092")
TOPIC = os.getenv("TOPIC", "market.data")
SYMBOLS = os.getenv("SYMBOLS", "AAPL,GOOGL,MSFT,AMZN,TSLA").split(",")
INTERVAL_MS = int(os.getenv("INTERVAL_MS", "100"))

class MarketSimulator:
    """Generates realistic market data with Brownian motion price dynamics"""

    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.base_prices: Dict[str, float] = {
            "AAPL": 180.0, "GOOGL": 140.0, "MSFT": 420.0,
            "AMZN": 185.0, "TSLA": 240.0, "NVDA": 900.0,
            "META": 510.0, "JPM": 195.0, "BTC-USD": 68000.0,
            "ETH-USD": 3500.0
        }
        self.prices: Dict[str, float] = {}
        self.volatility: Dict[str, float] = {}
        self.sequence: int = 0
        self.running = False

    def start(self):
        """Initialize prices and start simulation threads"""
        for sym in self.symbols:
            self.prices[sym] = self.base_prices.get(
                sym.strip(), random.uniform(50, 500)
            )
            self.volatility[sym] = self.prices[sym] * 0.002  # 0.2% vol

        self.running = True
        print(f"[SIMULATOR] Started: {len(self.symbols)} symbols, "
              f"interval={INTERVAL_MS}ms")
        print(f"[SIMULATOR] Symbols: {', '.join(self.symbols)}")

        # Run simulation loop
        try:
            self._loop()
        except KeyboardInterrupt:
            print("\n[SIMULATOR] Stopped")

    def _loop(self):
        """Main simulation loop"""
        while self.running:
            start = time.time()

            for symbol in self.symbols:
                self._generate_tick(symbol.strip())

            elapsed = (time.time() - start) * 1000
            sleep_time = max(0, INTERVAL_MS / 1000 - elapsed / 1000)
            time.sleep(sleep_time)

    def _generate_tick(self, symbol: str):
        """Generate a single market tick"""
        if symbol not in self.prices:
            return

        self.sequence += 1
        price = self.prices[symbol]
        vol = self.volatility[symbol]

        # Geometric Brownian Motion
        drift = 0.0  # No drift for simulation
        shock = random.gauss(0, 1) * vol * math.sqrt(1.0 / 252 / 390 / 60)
        new_price = price * math.exp(drift + shock)

        # Occasional larger moves (2% chance of 2σ event)
        if random.random() < 0.02:
            new_price = price * math.exp(drift + shock * 4)

        self.prices[symbol] = new_price
        spread = new_price * random.uniform(0.0001, 0.001)
        bid = round(new_price - spread / 2, 2)
        ask = round(new_price + spread / 2, 2)
        bid_size = round(random.uniform(100, 5000), 1)
        ask_size = round(random.uniform(100, 5000), 1)

        # Quote event
        quote = {
            "type": "quote",
            "symbol": symbol,
            "exchange": "SIM",
            "timestamp_ns": int(time.time() * 1_000_000_000),
            "bid_price": bid,
            "ask_price": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "sequence": self.sequence,
        }

        # 30% chance of also generating a trade
        if random.random() < 0.3:
            trade = {
                "type": "trade",
                "symbol": symbol,
                "exchange": "SIM",
                "timestamp_ns": int(time.time() * 1_000_000_000),
                "price": round(random.uniform(bid, ask), 2),
                "size": round(random.uniform(10, 1000), 1),
                "sequence": self.sequence + 1,
            }
            print(json.dumps(trade))

        self.sequence += 1
        print(json.dumps(quote))


if __name__ == "__main__":
    sim = MarketSimulator(SYMBOLS)
    sim.start()
