# Enhanced trading system with NVIDIA NIM integration

import os
import requests
from datetime import datetime
from openai import OpenAI
from trading_system import TradingSystem
from enhanced_strategy import EnhancedTradingStrategy
from nvidia_nim import MarketDataClient

class EnhancedTradingSystem:
    def __init__(self, nvidia_api_key):
        self.trading_system = TradingSystem()
        self.enhanced_strategy = EnhancedTradingStrategy(nvidia_api_key)
        self.market_data_client = MarketDataClient(nvidia_api_key)
        self.api_key = nvidia_api_key
    
    def get_market_sentiment(self, symbol, news_data):
        """Get market sentiment for a symbol using NVIDIA NIM"""
        return self.enhanced_strategy.get_market_sentiment(symbol, news_data)
    
    def get_enhanced_trade_signals(self, symbols):
        """Get enhanced trade signals for a list of symbols"""
        signals = {}
        for symbol in symbols:
            # Get market data
            market_data = self.market_data_client.get_market_data(symbol)
            current_price = market_data["price"]
            
            # Generate enhanced signal
            signal = self.enhanced_strategy.generate_trade_signal(symbol, current_price, market_data)
            if signal:
                signals[symbol] = signal
        
        return signals

# Initialize the enhanced trading system
ets = EnhancedTradingSystem("NVIDIA_API_KEY=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")