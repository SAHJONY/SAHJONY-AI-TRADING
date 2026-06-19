import os
import json
import redis
import pandas as pd
import numpy as np
from scipy.stats import norm
from py_vollib.black_scholes import black_scholes as bs_price_fn
from py_vollib.black_scholes_merton import implied_volatility as iv_fn

# Helper functions -------------------------------------------------------

def iv_from_market_price(spot: float, strike: float, t: float, r: float, market_price: float, flag: str) -> float | None:
    """Calculate implied volatility from market price using py_vollib.
    Returns None if the price is out of bounds.
    """
    try:
        return iv_fn(flag, spot, strike, t, r, market_price)
    except Exception:
        return None

def black_scholes_price(spot: float, strike: float, t: float, r: float, iv: float | None, flag: str) -> float | None:
    if iv is None:
        return None
    return bs_price_fn(flag, spot, strike, t, r, iv)

def macro_gate_score(df: pd.DataFrame) -> float | None:
    if df.empty or "value" not in df.columns:
        return None
    # Simple average of macro indicator values, scaled to 0-1
    return float(df["value"].mean())

def diff_signal(series: pd.Series) -> float | None:
    if series.empty:
        return None
    diffs = series.diff().fillna(0)
    return float(diffs.iloc[-1])

# Initialise Redis client (singleton per process)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(redis_url)
