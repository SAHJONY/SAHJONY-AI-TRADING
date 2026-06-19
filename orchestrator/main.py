import os
import json
import asyncio
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# -------------------- Global singletons --------------------
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(redis_url)

# In‑memory cache of the latest signal per agent
latest_signals: dict[str, dict] = {}

# Pydantic model representing a trade order that downstream brokers can consume
class TradeOrder(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    qty: int
    confidence: float
    source_agent: str

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/order")
async def receive_order(order: TradeOrder):
    """Receive a trade order and forward it to a broker channel.
    In production this would invoke Alpaca/CCXT APIs; here we simply publish to Redis.
    """
    redis_client.publish("broker_orders", order.json())
    return {"received": order.dict()}

# ---------------------------------------------------------------------
# Background task: listen to all ``agent_*`` channels, keep the latest signal,
# and emit a simple trade order when confidence exceeds a threshold.
# ---------------------------------------------------------------------
async def agent_listener():
    pubsub = redis_client.pubsub()
    pubsub.psubscribe("agent_*")
    for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue
        channel = message["channel"].decode()
        payload = json.loads(message["data"].decode())
        latest_signals[channel] = payload
        conf = payload.get("confidence", 0)
        if conf and conf > 7:
            order = TradeOrder(
                symbol="AAPL",
                side="buy",
                qty=10,
                confidence=conf,
                source_agent=payload.get("agent", "unknown"),
            )
            redis_client.publish("trade_orders", order.json())

@app.on_event("startup")
async def startup_event():
    # Fire‑and‑forget background listener for the container lifetime
    asyncio.create_task(agent_listener())
