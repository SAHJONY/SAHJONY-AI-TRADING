import os
import json
import redis
from fastapi import FastAPI, HTTPException

app = FastAPI()

# Agent identifier – each concrete agent copies this folder and sets AGENT_NAME env var
AGENT_NAME = os.getenv("AGENT_NAME", "template")

# Initialise Redis client (same as core engine)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(redis_url)

@app.get("/health")
async def health():
    return {"status": "ok", "agent": AGENT_NAME}

@app.post("/signal")
async def receive_signal(payload: dict):
    """Receive core metrics, apply simple transformation, and publish.
    This placeholder just adds a naive confidence score derived from implied volatility.
    """
    try:
        iv = payload.get("implied_vol")
        confidence = (float(iv) * 10) if iv is not None else 0.0
        out = {
            "agent": AGENT_NAME,
            "signal": payload,
            "confidence": confidence,
        }
        redis_client.publish(f"agent_{AGENT_NAME}", json.dumps(out))
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
