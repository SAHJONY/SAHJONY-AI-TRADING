# Enhanced trading strategy using NVIDIA NIM models

import os
from datetime import datetime
from openai import OpenAI
from strategy import TradingStrategy

class EnhancedTradingStrategy:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )
        self.base_strategy = TradingStrategy()
    
    def get_market_sentiment(self, symbol, news_data):
        """Get market sentiment for a symbol using NVIDIA NIM"""
        try:
            completion = self.client.chat.completions.create(
                model="meta/llama3-70b-instruct",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial sentiment analysis expert. Analyze the sentiment of the provided news and provide a sentiment score between -1 (very negative) and 1 (very positive) with a short explanation."
                    },
                    {
                        "role": "user",
                        "content": f"Analyze the sentiment for {symbol} based on the following news:\n{news_data}"
                    }
                ],
                temperature=0.2,
                top_p=0.7,
                max_tokens=1024,
            )
            
            response = completion.choices[0].message.content
            return response
        except Exception as e:
            print(f"Error getting sentiment: {e}")
            return "0.0:Neutral"
    
    def generate_trade_signal(self, symbol, current_price, market_data):
        """Generate a trade signal using market data and sentiment analysis"""
        # Get sentiment for the symbol
        sentiment = self.get_market_sentiment(symbol, market_data.get("news", ""))
        
        # Use the base strategy to generate a signal
        base_signal = self.base_strategy.generate_trade_signal(symbol, current_price)
        
        # Enhance the signal with sentiment analysis
        if base_signal:
            # Parse sentiment score (assuming format "score:explanation")
            sentiment_score = float(sentiment.split(":")[0])
            
            # Adjust signal based on sentiment
            if sentiment_score > 0.5:
                base_signal["action"] = "BUY"
                base_signal["confidence"] = min(1.0, base_signal["confidence"] * (1 + sentiment_score))
            elif sentiment_score < -0.5:
                base_signal["action"] = "SELL"
                base_signal["confidence"] = min(1.0, base_signal["confidence"] * (1 - sentiment_score))
            
            return base_signal
        
        return None

# Initialize the enhanced trading strategy
ets = EnhancedTradingStrategy("NVIDIA_API_KEY=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")
print("Enhanced trading strategy with NVIDIA NIM initialized")