from fastapi import FastAPI, Request
import json
import subprocess
import sys
from pathlib import Path

app = FastAPI()

@app.get("/healthz")
async def healthz():
    """Simple health check – returns 200 if the container is running."""
    return {"status": "ok"}

@app.get("/")
async def root(request: Request):
    """Execute the trading bot in dry‑run mode and return its output.
    This endpoint mirrors the previous Lambda‑style ``handler`` but uses a
    proper FastAPI ``app`` object that Vercel's Python runtime can detect.
    """
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--dry-run"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as e:
        return {"error": str(e)}
