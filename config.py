"""Configuration loader for the SAHJONY Capital trading bot.
It pulls required environment variables and defines risk limits.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    # Fallback to system env vars; ensure required vars are present.
    pass

# Required Alpaca credentials
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET")
ALPACA_PAPER_URL = os.getenv("ALPACA_PAPER_URL", "https://paper-api.alpaca.markets")

# Risk parameters (can be tweaked via env)
MAX_CAPITAL_ALLOCATION = float(os.getenv("MAX_CAPITAL_ALLOCATION", "0.5"))  # 50% of buying power
MAX_POSITION_PER_ASSET = float(os.getenv("MAX_POSITION_PER_ASSET", "0.1"))  # 10% per ticker

# Market schedule (Eastern Time)
MARKET_OPEN_HOUR = int(os.getenv("MARKET_OPEN_HOUR", "9"))
MARKET_OPEN_MINUTE = int(os.getenv("MARKET_OPEN_MINUTE", "30"))
MARKET_CLOSE_HOUR = int(os.getenv("MARKET_CLOSE_HOUR", "16"))
MARKET_CLOSE_MINUTE = int(os.getenv("MARKET_CLOSE_MINUTE", "0"))
