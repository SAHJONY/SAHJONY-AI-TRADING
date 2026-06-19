from fastapi import FastAPI, HTTPException
import os
import json
import pandas as pd

from .helpers import (
    redis_client,
    iv_from_market_price,
    black_scholes_price,
    macro_gate_score,
    diff_signal,
)

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/compute")
async def compute(payload: dict):
    """Accept raw market snapshot, compute core metrics, and publish.
    Expected keys:
        spot, strike, expiry_days, risk_free, price, flag (c/p)
        Optional: macro (list of {date,value}), price_series (list of floats)
    """
    try:
        s = float(payload["spot"])
        k = float(payload["strike"])
        t = float(payload.get("expiry_days", 30)) / 365.0
        r = float(payload.get("risk_free", 0.02))
        market_price = float(payload.get("price", 0.0))
        flag = payload.get("flag", "c")

        iv = iv_from_market_price(s, k, t, r, market_price, flag)
        bs_price = black_scholes_price(s, k, t, r, iv, flag)

        macro_score = macro_gate_score(pd.DataFrame(payload.get("macro", [])))
        diff = diff_signal(pd.Series(payload.get("price_series", [])))

        result = {
            "bs_price": bs_price,
            "implied_vol": iv,
            "macro_score": macro_score,
            "price_diff": diff,
        }
        redis_client.publish("core_metrics", json.dumps(result))
        return result
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing key: {e.args[0]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
