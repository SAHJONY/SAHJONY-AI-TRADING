import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseSettings

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI()

# ---------------------------------------------------------------------------
# Settings – environment variables (populate a .env file later)
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    ALPACA_KEY_ID: str = ""
    ALPACA_SECRET_KEY: str = ""
    POSTGRES_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/trading"
    REDIS_URL: str = "redis://redis:6379"

settings = Settings()

# ---------------------------------------------------------------------------
# Root page (optional placeholder)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    return """<html><body><h1>AI Trading Dashboard Backend</h1><p>WebSocket endpoint: <code>/ws/market</code></p></body></html>"""

# ---------------------------------------------------------------------------
# Connection manager for WebSocket clients
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# WebSocket endpoint – UI connects here to receive streamed JSON messages
# ---------------------------------------------------------------------------
@app.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; background tasks push data via manager.broadcast()
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ---------------------------------------------------------------------------
# Startup – launch background streaming tasks (Alpaca stocks, CCXT crypto)
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    # Import streaming helpers lazily to avoid circular imports.
    from alpaca_ws import start_alpaca_stream
    from ccxt_client import start_ccxt_stream
    # Fire‑and‑forget: tasks will push messages via manager.broadcast()
    asyncio.create_task(start_alpaca_stream(manager, settings))
    asyncio.create_task(start_ccxt_stream(manager))

# ---------------------------------------------------------------------------
# Shutdown – placeholder for cleanup (DB connections, etc.)
# ---------------------------------------------------------------------------
@app.on_event("shutdown")
async def shutdown_event():
    # Future cleanup logic goes here (close DB, Redis, etc.)
    pass
