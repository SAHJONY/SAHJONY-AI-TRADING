from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import subprocess
import sys
from pathlib import Path
import os
import aiofiles
from dotenv import set_key, find_dotenv

app = FastAPI()

# ---------------------------------------------------------------------------
# Static assets & template configuration
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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

# ---------------------------------------------------------------------------
# Owner Dashboard Endpoints
# ---------------------------------------------------------------------------

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request):
    """Render the simple owner dashboard HTML page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/owner/logs", response_class=PlainTextResponse)
async def owner_logs():
    """Return the tail of the recent bot log file.
    The log file is written to ``logs/bot.log`` by the application.
    If the file does not exist, a helpful message is returned.
    """
    log_path = Path(__file__).parent.parent / "logs" / "bot.log"
    if not log_path.is_file():
        return "Log file not found."
    async with aiofiles.open(log_path, "r") as f:
        content = await f.read()
    lines = content.strip().split("\n")[-500:]
    return "\n".join(lines)

@app.post("/owner/secrets")
async def owner_secrets(
    alpaca_api_key: str = Form(...),
    alpaca_api_secret: str = Form(...),
):
    """Persist Alpaca credentials to a ``.env`` file.
+    The function writes the received values to the project's root ``.env``
+    file using ``python-dotenv``'s ``set_key`` helper. Existing keys are
+    overwritten. The file is created if it does not exist.
    """
    env_path = find_dotenv(use_path=Path(__file__).parent.parent, raise_error_if_not_found=False)
    if not env_path:
        env_path = Path(__file__).parent.parent / ".env"
        env_path.touch(exist_ok=True)
    set_key(env_path, "ALPACA_API_KEY", alpaca_api_key)
    set_key(env_path, "ALPACA_API_SECRET", alpaca_api_secret)
    return {"msg": "Secrets saved to .env"}

@app.get("/owner/info", response_class=PlainTextResponse)
async def owner_info():
    """Return basic system information for the owner.
+    Includes OS, Python version, PID, uptime, and non‑secret environment variables.
+    """
    import platform, time, os, sys
    info = {
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "pid": os.getpid(),
        "uptime_seconds": time.time() - getattr(sys, "_start_time", time.time()),
        "env": {k: v for k, v in os.environ.items() if not k.startswith("ALPACA_")},
    }
    return json.dumps(info, indent=2)

